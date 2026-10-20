import hashlib
import hmac
import io
import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
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
    PublishRemainRequest,
    RemainResponse,
    ResearcherAuthRequest,
    ResearcherCreateRequest,
    ResearcherResponse,
    ResearcherSessionResponse,
)
from core.auth import (
    create_researcher_session,
    get_current_researcher,
    get_optional_researcher,
    revoke_researcher_session,
    set_session_cookie,
    clear_session_cookie,
)

router = APIRouter(prefix="/api")
Database = Annotated[AsyncSession, Depends(get_db)]
CurrentResearcher = Annotated[Researchers, Depends(get_current_researcher)]
OptionalResearcher = Annotated[Researchers | None, Depends(get_optional_researcher)]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v"}
MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_VIDEO_SIZE = 32 * 1024 * 1024


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_password: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = stored_password.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return hmac.compare_digest(actual, expected)


async def store_researcher(fields: ResearcherCreateRequest, db: AsyncSession) -> Researchers:
    researcher = Researchers(
        username=fields.username,
        full_name=fields.full_name,
        password=await run_in_threadpool(hash_password, fields.password.get_secret_value()),
    )
    db.add(researcher)
    await db.commit()
    await db.refresh(researcher)
    return researcher


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


async def create_draft_record(
    db: AsyncSession,
    researcher: Researchers,
    title: str,
    image_file: UploadFile | None,
    video_file: UploadFile | None,
    default_image_url: str | None = None,
    default_video_url: str | None = None,
) -> Remains:
    existing = await db.scalar(
        select(Remains.id).where(Remains.creator_id == researcher.id, Remains.status == "draft")
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="У пользователя уже есть черновик")
    image_name = None
    video_name = None
    if image_file is not None and image_file.filename:
        image_url, image_name = await upload_to_minio(image_file, "image")
    elif default_image_url:
        image_url = default_image_url
    else:
        raise HTTPException(status_code=422, detail="Изображение обязательно")
    try:
        if video_file is not None and video_file.filename:
            video_url, video_name = await upload_to_minio(video_file, "video")
        elif default_video_url:
            video_url = default_video_url
        else:
            raise HTTPException(status_code=422, detail="Видео обязательно")
    except Exception:
        if image_name:
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
        if image_name:
            await run_in_threadpool(remove_minio_file, image_name)
        if video_name:
            await run_in_threadpool(remove_minio_file, video_name)
        raise HTTPException(status_code=409, detail="Черновик уже создан") from error
    return draft


async def publish_draft_record(
    remain_id: int,
    researcher_id: int,
    fields: PublishRemainRequest,
    db: AsyncSession,
) -> Remains | None:
    draft = await db.scalar(
        select(Remains)
        .where(
            Remains.id == remain_id,
            Remains.creator_id == researcher_id,
            Remains.status == "draft",
        )
        .with_for_update()
    )
    if draft is None:
        return None
    for field_name in ("description", "analysis_time_days", "carbon_14_pmc"):
        stored_value = getattr(draft, field_name)
        if stored_value is not None and stored_value != "" and stored_value != getattr(fields, field_name):
            raise HTTPException(status_code=409, detail="Заполненные поля черновика нельзя изменять")
    draft.description = fields.description
    draft.analysis_time_days = fields.analysis_time_days
    draft.carbon_14_pmc = fields.carbon_14_pmc
    draft.status = "published"
    draft.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(draft)
    return draft


async def soft_delete_remain(remain_id: int, researcher_id: int, db: AsyncSession) -> bool:
    result = await db.execute(
        update(Remains)
        .where(
            Remains.id == remain_id,
            Remains.creator_id == researcher_id,
            Remains.status == "published",
        )
        .values(status="deleted")
        .returning(Remains.id)
    )
    if result.scalar_one_or_none() is None:
        return False
    await db.commit()
    return True


async def set_remain_like_record(remain_id: int, researcher_id: int, liked: int, db: AsyncSession) -> bool:
    remain = await db.scalar(
        select(Remains).where(Remains.id == remain_id, Remains.status == "published").with_for_update()
    )
    if remain is None:
        return False
    existing = await db.scalar(
        select(RemainsLikes).where(
            RemainsLikes.researcher_id == researcher_id,
            RemainsLikes.remains_id == remain_id,
        )
    )
    if liked == 1 and existing is None:
        db.add(RemainsLikes(researcher_id=researcher_id, remains_id=remain_id))
    elif liked == 0 and existing is not None:
        await db.delete(existing)
    await db.commit()
    return True


@router.get(
    "/remains",
    response_model=list[RemainResponse],
    tags=["Останки"],
    summary="Получить опубликованные останки",
    description="Публичный список с фильтрами по названию и содержанию C-14. Если передана cookie, в ответе также вычисляются признаки автора и лайка.",
)
async def list_remains(
    db: Database,
    researcher: OptionalResearcher,
    carbon_min: Decimal = Query(default=Decimal("0"), ge=0, le=200),
    carbon_max: Decimal | None = Query(default=None, ge=0, le=200),
    title: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=100),
):
    researcher_id = researcher.id if researcher else 0
    statement = remain_query(researcher_id).where(
        Remains.status == "published",
        Remains.carbon_14_pmc >= carbon_min,
    )
    if carbon_max is not None:
        statement = statement.where(Remains.carbon_14_pmc <= carbon_max)
    if title:
        statement = statement.where(Remains.title.ilike(f"%{title.strip()}%"))
    result = await db.execute(statement.order_by(Remains.id).limit(limit))
    return [serialize_remain(row, researcher_id) for row in result.all()]


@router.get(
    "/remains/feed",
    response_model=RemainResponse,
    tags=["Останки"],
    summary="Получить останок для ленты",
    description="Публично возвращает первую опубликованную запись, запись по ID либо следующую запись при next=true.",
)
async def get_remains_feed(
    db: Database,
    researcher: OptionalResearcher,
    remains_id: int | None = Query(default=None, gt=0),
    next: bool = False,
):
    researcher_id = researcher.id if researcher else 0
    if remains_id is not None and not next:
        row = await get_published_row(db, remains_id, researcher_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Останки не найдены или не опубликованы")
        return serialize_remain(row, researcher_id)
    statement = remain_query(researcher_id).where(Remains.status == "published")
    if remains_id is not None and next:
        statement = statement.where(Remains.id > remains_id)
    result = await db.execute(statement.order_by(Remains.id).limit(1))
    row = result.first()
    if row is None and remains_id is not None and next:
        result = await db.execute(
            remain_query(researcher_id).where(Remains.status == "published").order_by(Remains.id).limit(1)
        )
        row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Пока нет опубликованных останков")
    return serialize_remain(row, researcher_id)


@router.get(
    "/remains/draft",
    response_model=RemainResponse,
    tags=["Останки"],
    summary="Получить свой черновик",
    description="Требует авторизации; возвращается черновик текущего исследователя без передачи его ID.",
)
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
    summary="Создать черновик с фото и видео",
    description="Требует авторизации. Принимает multipart/form-data с названием и файлами; медиа сохраняются в MinIO, создатель берётся из сессии.",
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
    draft = await create_draft_record(db, researcher, title, image_file, video_file)
    return serialize_remain((draft, 0, 0), researcher.id)


@router.put(
    "/remains/{remain_id}/publish",
    response_model=RemainResponse,
    tags=["Останки"],
    summary="Опубликовать свой черновик",
    description="Требует авторизации владельца черновика. Передаются описание, время анализа и содержание C-14; служебные поля задаёт сервер.",
)
async def publish_remains(
    remain_id: int,
    fields: PublishRemainRequest,
    db: Database,
    researcher: CurrentResearcher,
):
    draft = await publish_draft_record(remain_id, researcher.id, fields, db)
    if draft is None:
        raise HTTPException(status_code=404, detail="Черновик не найден")
    return serialize_remain((draft, 0, 0), researcher.id)


@router.post(
    "/remains/{remain_id}/likes",
    response_model=RemainResponse,
    tags=["Останки"],
    summary="Поставить или снять лайк",
    description="Требует авторизации. liked=1 ставит лайк, liked=0 снимает его для текущего исследователя.",
)
async def set_remain_like(
    remain_id: int,
    fields: LikeRequest,
    db: Database,
    researcher: CurrentResearcher,
):
    if not await set_remain_like_record(remain_id, researcher.id, fields.liked, db):
        raise HTTPException(status_code=404, detail="Опубликованные останки не найдены")
    row = await get_published_row(db, remain_id, researcher.id)
    return serialize_remain(row, researcher.id)


@router.delete(
    "/remains/{remain_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Останки"],
    summary="Логически удалить свой останок",
    description="Требует авторизации владельца опубликованной записи. Физического удаления строки не происходит.",
)
async def delete_remain(remain_id: int, db: Database, researcher: CurrentResearcher):
    if not await soft_delete_remain(remain_id, researcher.id, db):
        raise HTTPException(status_code=404, detail="Опубликованные останки пользователя не найдены")


@router.post(
    "/researchers",
    response_model=ResearcherResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Исследователи"],
    summary="Зарегистрировать исследователя",
    description="Создаёт пользователя. Пароль сохраняется в виде PBKDF2-хеша; после регистрации выполните аутентификацию.",
)
async def register_researcher(fields: ResearcherCreateRequest, db: Database):
    try:
        researcher = await store_researcher(fields, db)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Исследователь с таким username уже существует") from error
    return researcher


@router.post(
    "/researchers/auth",
    response_model=ResearcherSessionResponse,
    tags=["Исследователи"],
    summary="Аутентифицировать исследователя",
    description="Проверяет username и пароль, создаёт Redis-сессию и устанавливает HttpOnly cookie.",
)
async def authenticate_researcher(
    fields: ResearcherAuthRequest,
    request: Request,
    response: Response,
    db: Database,
):
    researcher = await db.scalar(select(Researchers).where(Researchers.username == fields.username.strip()))
    password = fields.password.get_secret_value()
    valid_password = (
        await run_in_threadpool(verify_password, password, researcher.password)
        if researcher is not None
        else False
    )
    if not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
            headers={"WWW-Authenticate": "Cookie"},
        )
    await revoke_researcher_session(request, request.cookies.get(settings.SESSION_COOKIE_NAME))
    token = await create_researcher_session(request, researcher)
    set_session_cookie(response, token)
    return ResearcherSessionResponse(
        id=researcher.id,
        username=researcher.username,
        full_name=researcher.full_name,
        message="Аутентификация выполнена",
    )


@router.post(
    "/researchers/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Исследователи"],
    summary="Завершить сессию",
    description="Удаляет Redis-сессию и очищает cookie браузера.",
)
async def logout_researcher(request: Request, response: Response):
    await revoke_researcher_session(request, request.cookies.get(settings.SESSION_COOKIE_NAME))
    clear_session_cookie(response)
