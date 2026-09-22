from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, StringConstraints, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import PROJECT_ROOT, settings
from db.session import get_db
from models.remains_likes import RemainsLikes
from models.remains import Remains

router = APIRouter(prefix="/remains")
templates = Jinja2Templates(directory=PROJECT_ROOT / "templates")
Database = Annotated[AsyncSession, Depends(get_db)]
RemainsTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
DEFAULT_DRAFT_IMAGE = f"{settings.MINIO_URL}/wood.jpg"
DEFAULT_DRAFT_VIDEO = f"{settings.MINIO_URL}/wood-video.mp4"
ICONS = {
    "carbon": f"{settings.MINIO_URL}/flask.png",
    "analysis_time": f"{settings.MINIO_URL}/watch.png",
}


class DraftFields(BaseModel):
    title: RemainsTitle


class PublicationFields(DraftFields):
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    analysis_time_days: int = Field(gt=0, le=36500)
    carbon_14_pmc: Decimal = Field(ge=0, le=200, max_digits=7, decimal_places=3)


def page_context(active_page: str, **extra):
    return {
        "active_page": active_page,
        "icons": ICONS,
        "style_version": (PROJECT_ROOT / "static/css/style.css").stat().st_mtime_ns,
        **extra,
    }


def remain_values(remain, likes_count=0):
    return {
        "id": remain.id,
        "title": remain.title,
        "description": remain.description or "",
        "analysis_time_days": remain.analysis_time_days,
        "carbon_14_pmc": remain.carbon_14_pmc,
        "image": remain.image_url,
        "video": remain.video_url,
        "image_url": remain.image_url,
        "video_url": remain.video_url,
        "likes_count": likes_count,
    }


def remains_with_likes():
    likes = select(func.count(RemainsLikes.id)).where(RemainsLikes.remains_id == Remains.id).scalar_subquery()
    return select(Remains, likes.label("likes_count"))


async def get_published_remains(db, carbon_min):
    result = await db.execute(
        remains_with_likes().where(Remains.status == "published", Remains.carbon_14_pmc >= carbon_min).order_by(Remains.id)
    )
    return result.all()


async def get_remain_by_id(db, remains_id):
    result = await db.execute(remains_with_likes().where(Remains.id == remains_id, Remains.status == "published"))
    return result.first()


async def get_next_remain_id(db, current_id):
    following = await db.scalar(select(func.min(Remains.id)).where(Remains.status == "published", Remains.id > current_id))
    if following is not None:
        return following
    return await db.scalar(select(func.min(Remains.id)).where(Remains.status == "published"))


async def get_draft_remain(db):
    return await db.scalar(select(Remains).where(Remains.creator_id == 999, Remains.status == "draft"))


async def create_draft(db, title):
    draft = Remains(
        title=title,
        status="draft",
        image_url=DEFAULT_DRAFT_IMAGE,
        video_url=DEFAULT_DRAFT_VIDEO,
        creator_id=999,
    )
    db.add(draft)
    await db.commit()
    return draft


async def publish_draft(db, draft, fields):
    draft.title = fields.title
    draft.description = fields.description
    draft.analysis_time_days = fields.analysis_time_days
    draft.carbon_14_pmc = fields.carbon_14_pmc
    draft.status = "published"
    draft.published_at = datetime.now(timezone.utc)
    await db.commit()


async def delete_remain(remains_id):
    async with await psycopg.AsyncConnection.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
    ) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "UPDATE remains SET status = %s WHERE id = %s AND status = %s RETURNING id",
                ("deleted", remains_id, "published"),
            )
            return await cursor.fetchone() is not None


async def draft_response(request: Request, draft, values=None, errors=None, status_code=200):
    if draft is not None:
        draft_values = remain_values(draft)
    else:
        draft_values = {
            "title": "", "description": "", "analysis_time_days": "", "carbon_14_pmc": "",
            "image": DEFAULT_DRAFT_IMAGE, "video": DEFAULT_DRAFT_VIDEO,
            "image_url": DEFAULT_DRAFT_IMAGE, "video_url": DEFAULT_DRAFT_VIDEO,
        }
    if values:
        draft_values.update(values)
    return templates.TemplateResponse(
        request=request,
        name="add.html",
        context=page_context("draft", draft_remains=draft_values, draft_id=draft.id if draft else None, errors=errors or {}),
        status_code=status_code,
    )


def form_errors(error: ValidationError):
    messages = {
        "title": "Введите название от 1 до 120 символов.",
        "description": "Введите описание от 1 до 2000 символов.",
        "analysis_time_days": "Введите целое число от 1 до 36500.",
        "carbon_14_pmc": "Введите число от 0 до 200, не более трёх знаков после запятой.",
    }
    return {item["loc"][0]: messages[item["loc"][0]] for item in error.errors()}


@router.get("/feed")
async def remains_feed(request: Request, db: Database, remains_id: int | None = None, next: bool = False, expanded: bool = False):
    row = await get_remain_by_id(db, remains_id) if remains_id is not None else None
    if remains_id is not None and row is None:
        raise HTTPException(status_code=404, detail="Останки не найдены или не опубликованы")
    if remains_id is None or next:
        following = await get_next_remain_id(db, remains_id if remains_id is not None else -1)
        if following is None:
            raise HTTPException(status_code=404, detail="Пока нет опубликованных останков")
        return RedirectResponse(url=f"/remains/feed?remains_id={following}", status_code=303)
    item = remain_values(*row)
    return templates.TemplateResponse(
        request=request, name="feed.html", context=page_context("feed", remains_item=item, expanded=expanded)
    )


@router.get("/draft")
async def remains_draft(request: Request, db: Database):
    return await draft_response(request, await get_draft_remain(db))


@router.get("")
async def remains_grid(request: Request, db: Database, carbon_min: Decimal = Query(default=Decimal(0), ge=0, le=200)):
    rows = await get_published_remains(db, carbon_min)
    return templates.TemplateResponse(
        request=request,
        name="grid.html",
        context=page_context("grid", remains=[remain_values(*row) for row in rows], carbon_min=carbon_min),
    )


@router.post("/draft")
async def create_remains(request: Request, db: Database, title: str = Form("")):
    if await get_draft_remain(db) is not None:
        return RedirectResponse(url="/remains/draft", status_code=303)
    try:
        fields = DraftFields(title=title)
    except ValidationError as error:
        return await draft_response(request, None, {"title": title}, form_errors(error), 422)
    try:
        await create_draft(db, fields.title)
    except IntegrityError as error:
        await db.rollback()
        if await get_draft_remain(db) is None:
            raise error
    return RedirectResponse(url="/remains/draft", status_code=303)


@router.post("/{remains_id}/publish")
async def publish_remains(
    request: Request,
    remains_id: int,
    db: Database,
    title: str = Form(""),
    description: str = Form(""),
    analysis_time_days: str = Form(""),
    carbon_14_pmc: str = Form(""),
):
    draft = await db.scalar(
        select(Remains).where(Remains.id == remains_id, Remains.creator_id == 999, Remains.status == "draft").with_for_update()
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Черновик не найден или уже опубликован")
    values = {"title": title, "description": description, "analysis_time_days": analysis_time_days, "carbon_14_pmc": carbon_14_pmc}
    try:
        fields = PublicationFields(**values)
    except ValidationError as error:
        return await draft_response(request, draft, values, form_errors(error), 422)
    await publish_draft(db, draft, fields)
    return RedirectResponse(url=f"/remains/feed?remains_id={draft.id}", status_code=303)


@router.post("/{remains_id}/delete")
async def delete_remains(remains_id: int, carbon_min: Decimal = Form(default=Decimal(0), ge=0, le=200)):
    if not await delete_remain(remains_id):
        raise HTTPException(status_code=404, detail="Опубликованные останки не найдены")
    return RedirectResponse(url=f"/remains?carbon_min={carbon_min:g}", status_code=303)
