import hashlib
import io
import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from minio import Minio
from minio.error import S3Error
from sqlalchemy import case, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from core.config import settings
from db.session import get_db
from models.remains import Remains
from models.remains_likes import RemainsLikes
from models.researchers import Researchers
from api.remains_schemas import (
    LikeRequest,
    MessageResponse,
    PublishRemainRequest,
    RemainResponse,
    ResearcherAuthRequest,
    ResearcherCreateRequest,
    ResearcherResponse,
)

router = APIRouter(prefix="/api")
Database = Annotated[AsyncSession, Depends(get_db)]
CURRENT_RESEARCHER_ID = 1
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v"}
MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_VIDEO_SIZE = 32 * 1024 * 1024


def current_researcher_id() -> int:
    return CURRENT_RESEARCHER_ID


async def get_current_researcher(db: Database) -> Researchers:
    researcher = await db.get(Researchers, current_researcher_id())
    if researcher is None:
        raise HTTPException(status_code=503, detail="Фиксированный пользователь API отсутствует в БД")
    return researcher


CurrentResearcher = Annotated[Researchers, Depends(get_current_researcher)]


@lru_cache(maxsize=1)
def minio_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_SSL,
    )


def ensure_minio_bucket() -> None:
    client = minio_client()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        try:
            client.make_bucket(settings.MINIO_BUCKET)
        except S3Error as error:
            if error.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                raise
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{settings.MINIO_BUCKET}/*"],
                }
            ],
        }
        client.set_bucket_policy(settings.MINIO_BUCKET, json.dumps(policy))


def store_minio_file(object_name: str, contents: bytes, content_type: str) -> None:
    ensure_minio_bucket()
    minio_client().put_object(
        settings.MINIO_BUCKET,
        object_name,
        io.BytesIO(contents),
        len(contents),
        content_type=content_type,
    )


def remove_minio_file(object_name: str) -> None:
    minio_client().remove_object(settings.MINIO_BUCKET, object_name)


async def upload_to_minio(upload: UploadFile, kind: str) -> tuple[str, str]:
    extension = Path(upload.filename or "").suffix.lower()
    allowed_extensions = IMAGE_EXTENSIONS if kind == "image" else VIDEO_EXTENSIONS
    max_size = MAX_IMAGE_SIZE if kind == "image" else MAX_VIDEO_SIZE
    if extension not in allowed_extensions:
        raise HTTPException(status_code=422, detail=f"Неподдерживаемый формат {kind}")
    if kind == "image" and not (upload.content_type or "").startswith("image/"):
        raise HTTPException(status_code=422, detail="Для поля изображения нужен файл изображения")
    if kind == "video" and not (upload.content_type or "").startswith("video/"):
        raise HTTPException(status_code=422, detail="Для поля видео нужен видеофайл")
    contents = await upload.read(max_size + 1)
    if not contents:
        raise HTTPException(status_code=422, detail=f"Файл {kind} пуст")
    if len(contents) > max_size:
        raise HTTPException(status_code=413, detail=f"Файл {kind} превышает допустимый размер")
    object_name = f"remains-{uuid4().hex}{extension}"
    try:
        await run_in_threadpool(store_minio_file, object_name, contents, upload.content_type or "application/octet-stream")
    except Exception as error:
        raise HTTPException(status_code=503, detail="Не удалось сохранить файл в MinIO") from error
    return f"{settings.MINIO_URL.rstrip('/')}/{object_name}", object_name


def remain_query(researcher_id: int):
    likes_count = (
        select(func.count(RemainsLikes.id))
        .where(RemainsLikes.remains_id == Remains.id)
        .correlate(Remains)
        .scalar_subquery()
    )
    liked = exists(
        select(RemainsLikes.id).where(
            RemainsLikes.remains_id == Remains.id,
            RemainsLikes.researcher_id == researcher_id,
        )
    )
    return select(
        Remains,
        likes_count.label("likes_count"),
        case((liked, 1), else_=0).label("is_liked"),
    )


def serialize_remain(row, researcher_id: int) -> RemainResponse:
    remain, likes_count, is_liked = row
    return RemainResponse(
        id=remain.id,
        title=remain.title,
        description=remain.description,
        status=remain.status,
        image_url=remain.image_url,
        video_url=remain.video_url,
        analysis_time_days=remain.analysis_time_days,
        carbon_14_pmc=remain.carbon_14_pmc,
        created_at=remain.created_at,
        published_at=remain.published_at,
        likes_count=likes_count,
        is_liked=is_liked,
        is_mine=int(remain.creator_id == researcher_id),
    )


async def get_published_row(db: AsyncSession, remain_id: int, researcher_id: int):
    result = await db.execute(
        remain_query(researcher_id).where(Remains.id == remain_id, Remains.status == "published")
    )
    return result.first()


@router.get("/remains", response_model=list[RemainResponse], tags=["Останки"])
async def list_remains(
    db: Database,
    researcher: CurrentResearcher,
    carbon_min: Decimal = Query(default=Decimal("0"), ge=0, le=200),
    carbon_max: Decimal | None = Query(default=None, ge=0, le=200),
    title: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=100),
):
    statement = remain_query(researcher.id).where(
        Remains.status == "published",
        Remains.carbon_14_pmc >= carbon_min,
    )
    if carbon_max is not None:
        statement = statement.where(Remains.carbon_14_pmc <= carbon_max)
    if title:
        statement = statement.where(Remains.title.ilike(f"%{title.strip()}%"))
    result = await db.execute(statement.order_by(Remains.id).limit(limit))
    return [serialize_remain(row, researcher.id) for row in result.all()]


@router.get("/remains/feed", response_model=RemainResponse, tags=["Останки"])
async def get_remains_feed(
    db: Database,
    researcher: CurrentResearcher,
    remains_id: int | None = Query(default=None, gt=0),
    next: bool = False,
):
    if remains_id is not None and not next:
        row = await get_published_row(db, remains_id, researcher.id)
        if row is None:
            raise HTTPException(status_code=404, detail="Останки не найдены или не опубликованы")
        return serialize_remain(row, researcher.id)
    statement = remain_query(researcher.id).where(Remains.status == "published")
    if remains_id is not None and next:
        statement = statement.where(Remains.id > remains_id)
    result = await db.execute(statement.order_by(Remains.id).limit(1))
    row = result.first()
    if row is None and remains_id is not None and next:
        result = await db.execute(
            remain_query(researcher.id).where(Remains.status == "published").order_by(Remains.id).limit(1)
        )
        row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Пока нет опубликованных останков")
    return serialize_remain(row, researcher.id)


@router.get("/remains/draft", response_model=RemainResponse, tags=["Останки"])
async def get_remains_draft(db: Database, researcher: CurrentResearcher):
    result = await db.execute(
        remain_query(researcher.id).where(
            Remains.creator_id == researcher.id,
            Remains.status == "draft",
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Черновик не найден")
    return serialize_remain(row, researcher.id)


@router.post(
    "/remains/draft",
    response_model=RemainResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Останки"],
)
async def create_remains_draft(
    db: Database,
    researcher: CurrentResearcher,
    title: Annotated[str, Form(min_length=1, max_length=120)],
    image_file: Annotated[UploadFile, File()],
    video_file: Annotated[UploadFile, File()],
):
    if not title.strip():
        raise HTTPException(status_code=422, detail="Название останков не может быть пустым")
    existing = await db.scalar(
        select(Remains.id).where(Remains.creator_id == researcher.id, Remains.status == "draft")
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="У пользователя уже есть черновик")
    image_url, image_name = await upload_to_minio(image_file, "image")
    try:
        video_url, video_name = await upload_to_minio(video_file, "video")
    except Exception:
        await run_in_threadpool(remove_minio_file, image_name)
        raise
    draft = Remains(
        title=title.strip(),
        status="draft",
        image_url=image_url,
        video_url=video_url,
        creator_id=researcher.id,
    )
    db.add(draft)
    try:
        await db.commit()
        await db.refresh(draft)
    except IntegrityError as error:
        await db.rollback()
        await run_in_threadpool(remove_minio_file, image_name)
        await run_in_threadpool(remove_minio_file, video_name)
        raise HTTPException(status_code=409, detail="Черновик уже создан") from error
    return serialize_remain((draft, 0, 0), researcher.id)


@router.get("/remains/{remain_id}", response_model=RemainResponse, tags=["Останки"])
async def get_remain(remain_id: int, db: Database, researcher: CurrentResearcher):
    row = await get_published_row(db, remain_id, researcher.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Останки не найдены или не опубликованы")
    return serialize_remain(row, researcher.id)


@router.put("/remains/{remain_id}/publish", response_model=RemainResponse, tags=["Останки"])
async def publish_remains(
    remain_id: int,
    fields: PublishRemainRequest,
    db: Database,
    researcher: CurrentResearcher,
):
    draft = await db.scalar(
        select(Remains)
        .where(
            Remains.id == remain_id,
            Remains.creator_id == researcher.id,
            Remains.status == "draft",
        )
        .with_for_update()
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Черновик не найден")
    draft.description = fields.description
    draft.analysis_time_days = fields.analysis_time_days
    draft.carbon_14_pmc = fields.carbon_14_pmc
    draft.status = "published"
    draft.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(draft)
    return serialize_remain((draft, 0, 0), researcher.id)


@router.post("/remains/{remain_id}/likes", response_model=RemainResponse, tags=["Останки"])
async def set_remain_like(
    remain_id: int,
    fields: LikeRequest,
    db: Database,
    researcher: CurrentResearcher,
):
    remain = await db.scalar(
        select(Remains).where(Remains.id == remain_id, Remains.status == "published")
    )
    if remain is None:
        raise HTTPException(status_code=404, detail="Опубликованные останки не найдены")
    existing = await db.scalar(
        select(RemainsLikes).where(
            RemainsLikes.researcher_id == researcher.id,
            RemainsLikes.remains_id == remain_id,
        )
    )
    if fields.liked == 1 and existing is None:
        db.add(RemainsLikes(researcher_id=researcher.id, remains_id=remain_id))
    elif fields.liked == 0 and existing is not None:
        await db.delete(existing)
    await db.commit()
    row = await get_published_row(db, remain_id, researcher.id)
    return serialize_remain(row, researcher.id)


@router.delete("/remains/{remain_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Останки"])
async def delete_remain(remain_id: int, db: Database, researcher: CurrentResearcher):
    result = await db.execute(
        update(Remains)
        .where(
            Remains.id == remain_id,
            Remains.creator_id == researcher.id,
            Remains.status == "published",
        )
        .values(status="deleted")
        .returning(Remains.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Опубликованные останки пользователя не найдены")
    await db.commit()


@router.post(
    "/researchers",
    response_model=ResearcherResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Исследователи"],
)
async def register_researcher(fields: ResearcherCreateRequest, db: Database):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", fields.password.get_secret_value().encode(), salt, 310000)
    password_hash = f"pbkdf2_sha256${salt.hex()}${digest.hex()}"
    researcher = Researchers(
        username=fields.username,
        full_name=fields.full_name,
        password=password_hash,
    )
    db.add(researcher)
    try:
        await db.commit()
        await db.refresh(researcher)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Исследователь с таким username уже существует") from error
    return researcher


@router.post("/researchers/auth", response_model=MessageResponse, tags=["Исследователи"])
async def authenticate_researcher(fields: ResearcherAuthRequest):
    return MessageResponse(message="Аутентификация будет реализована в лабораторной работе 4", implemented=False)


@router.post("/researchers/logout", response_model=MessageResponse, tags=["Исследователи"])
async def logout_researcher():
    return MessageResponse(message="Деавторизация будет реализована в лабораторной работе 4", implemented=False)
