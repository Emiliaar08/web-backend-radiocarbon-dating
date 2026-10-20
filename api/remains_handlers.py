from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, StringConstraints, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.remains_api import (
    CurrentResearcher,
    create_draft_record,
    publish_draft_record,
    remain_query,
    set_remain_like_record,
    soft_delete_remain,
)
from api.remains_schemas import PublishRemainRequest
from core.config import PROJECT_ROOT, settings
from db.session import get_db
from models.remains import Remains

router = APIRouter(prefix="/remains")
templates = Jinja2Templates(directory=PROJECT_ROOT / "templates")
Database = Annotated[AsyncSession, Depends(get_db)]
RemainsTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
DEFAULT_DRAFT_TITLE = "Дерево"
DEFAULT_DRAFT_IMAGE = "/static/remains/wood.jpg"
DEFAULT_DRAFT_VIDEO = "/static/remains/wood-video.mp4"
ICONS = {
    "carbon": f"{settings.MINIO_URL}/flask.png",
    "analysis_time": f"{settings.MINIO_URL}/watch.png",
    "folder": f"{settings.MINIO_URL}/folder.png.webp",
}


class DraftFields(BaseModel):
    title: RemainsTitle


def page_context(active_page: str, **extra):
    return {
        "active_page": active_page,
        "icons": ICONS,
        "style_version": (PROJECT_ROOT / "static/css/remains.css").stat().st_mtime_ns,
        **extra,
    }


def remain_values(remain, likes_count=0, is_liked=0, researcher_id=0):
    image_url = remain.image_url
    video_url = remain.video_url
    if remain.status == "draft":
        if image_url == f"{settings.MINIO_URL}/wood.jpg":
            image_url = DEFAULT_DRAFT_IMAGE
        if video_url == f"{settings.MINIO_URL}/wood-video.mp4":
            video_url = DEFAULT_DRAFT_VIDEO
    return {
        "id": remain.id,
        "title": remain.title,
        "description": remain.description or "",
        "analysis_time_days": remain.analysis_time_days,
        "carbon_14_pmc": remain.carbon_14_pmc,
        "image": image_url,
        "video": video_url,
        "image_url": image_url,
        "video_url": video_url,
        "likes_count": likes_count,
        "is_liked": is_liked,
        "is_mine": researcher_id > 0 and remain.creator_id == researcher_id,
    }


def remains_with_likes(researcher_id=0):
    return remain_query(researcher_id)


async def get_published_remains(db, carbon_min, researcher_id):
    result = await db.execute(
        remains_with_likes(researcher_id)
        .where(Remains.status == "published", Remains.carbon_14_pmc >= carbon_min)
        .order_by(Remains.id)
    )
    return result.all()


async def get_remain_by_id(db, remains_id, researcher_id):
    result = await db.execute(
        remains_with_likes(researcher_id).where(Remains.id == remains_id, Remains.status == "published")
    )
    return result.first()


async def get_next_remain_id(db, current_id):
    following = await db.scalar(
        select(func.min(Remains.id)).where(Remains.status == "published", Remains.id > current_id)
    )
    if following is not None:
        return following
    return await db.scalar(select(func.min(Remains.id)).where(Remains.status == "published"))


async def get_draft_remain(db, researcher_id):
    return await db.scalar(
        select(Remains).where(
            Remains.creator_id == researcher_id,
            Remains.status == "draft",
        )
    )


async def draft_response(request: Request, draft, researcher_id, values=None, errors=None, status_code=200):
    if draft is not None:
        draft_values = remain_values(draft, researcher_id=researcher_id)
    else:
        draft_values = {
            "title": DEFAULT_DRAFT_TITLE,
            "description": "",
            "analysis_time_days": "",
            "carbon_14_pmc": "",
            "image": DEFAULT_DRAFT_IMAGE,
            "video": DEFAULT_DRAFT_VIDEO,
            "image_url": DEFAULT_DRAFT_IMAGE,
            "video_url": DEFAULT_DRAFT_VIDEO,
        }
    if values:
        draft_values.update(values)
    return templates.TemplateResponse(
        request=request,
        name="remains_add.html",
        context=page_context(
            "draft",
            draft_remains=draft_values,
            draft_id=draft.id if draft else None,
            draft_locked_fields={
                "description": bool(draft and draft.description),
                "analysis_time_days": draft is not None and draft.analysis_time_days is not None,
                "carbon_14_pmc": draft is not None and draft.carbon_14_pmc is not None,
            },
            errors=errors or {},
        ),
        status_code=status_code,
    )


def form_errors(error: ValidationError):
    messages = {
        "title": "Введите название от 1 до 120 символов.",
        "description": "Введите описание от 2 до 2000 символов.",
        "analysis_time_days": "Введите целое число от 1 до 36500.",
        "carbon_14_pmc": "Введите число от 0 до 200, не более трёх знаков после запятой.",
    }
    return {
        str(item["loc"][0]): messages.get(str(item["loc"][0]), "Проверьте введённые данные.")
        for item in error.errors()
    }


@router.get("/feed")
async def remains_feed(
    request: Request,
    db: Database,
    researcher: CurrentResearcher,
    remains_id: int | None = None,
    next: bool = False,
    expanded: bool = False,
):
    researcher_id = researcher.id
    row = await get_remain_by_id(db, remains_id, researcher_id) if remains_id is not None else None
    if remains_id is not None and row is None:
        raise HTTPException(status_code=404, detail="Останки не найдены или не опубликованы")
    if remains_id is None or next:
        following = await get_next_remain_id(db, remains_id if remains_id is not None else -1)
        if following is None:
            raise HTTPException(status_code=404, detail="Пока нет опубликованных останков")
        return RedirectResponse(url=f"/remains/feed?remains_id={following}", status_code=303)
    item = remain_values(*row, researcher_id=researcher_id)
    return templates.TemplateResponse(
        request=request,
        name="remains_feed.html",
        context=page_context("feed", remains_item=item, expanded=expanded),
    )


@router.get("/draft")
async def remains_draft(request: Request, db: Database, researcher: CurrentResearcher):
    return await draft_response(request, await get_draft_remain(db, researcher.id), researcher.id)


@router.get("")
async def remains_grid(
    request: Request,
    db: Database,
    researcher: CurrentResearcher,
    carbon_min: Decimal = Query(default=Decimal(0), ge=0, le=200),
):
    researcher_id = researcher.id
    rows = await get_published_remains(db, carbon_min, researcher_id)
    return templates.TemplateResponse(
        request=request,
        name="remains_grid.html",
        context=page_context(
            "grid",
            remains=[remain_values(*row, researcher_id=researcher_id) for row in rows],
            carbon_min=carbon_min,
        ),
    )


@router.post("/draft")
async def create_remains(
    request: Request,
    db: Database,
    researcher: CurrentResearcher,
    title: str = Form(DEFAULT_DRAFT_TITLE),
    image_file: UploadFile | None = File(default=None),
    video_file: UploadFile | None = File(default=None),
):
    if await get_draft_remain(db, researcher.id) is not None:
        return RedirectResponse(url="/remains/draft", status_code=303)
    try:
        fields = DraftFields(title=title)
    except ValidationError as error:
        return await draft_response(request, None, researcher.id, {"title": title}, form_errors(error), 422)
    try:
        await create_draft_record(
            db,
            researcher,
            fields.title,
            image_file,
            video_file,
            default_image_url=DEFAULT_DRAFT_IMAGE,
            default_video_url=DEFAULT_DRAFT_VIDEO,
        )
    except HTTPException as error:
        if error.status_code == 409:
            return RedirectResponse(url="/remains/draft", status_code=303)
        return await draft_response(
            request,
            None,
            researcher.id,
            {"title": fields.title},
            {"media": error.detail},
            error.status_code,
        )
    return RedirectResponse(url="/remains/draft", status_code=303)


@router.post("/{remains_id}/publish")
async def publish_remains(
    request: Request,
    remains_id: int,
    db: Database,
    researcher: CurrentResearcher,
    description: str = Form(""),
    analysis_time_days: str = Form(""),
    carbon_14_pmc: str = Form(""),
):
    draft = await db.scalar(
        select(Remains).where(
            Remains.id == remains_id,
            Remains.creator_id == researcher.id,
            Remains.status == "draft",
        )
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Черновик не найден или уже опубликован")
    values = {
        "description": description,
        "analysis_time_days": analysis_time_days,
        "carbon_14_pmc": carbon_14_pmc,
    }
    try:
        fields = PublishRemainRequest(**values)
    except ValidationError as error:
        return await draft_response(request, draft, researcher.id, values, form_errors(error), 422)
    published = await publish_draft_record(remains_id, researcher.id, fields, db)
    if published is None:
        raise HTTPException(status_code=404, detail="Черновик не найден или уже опубликован")
    return RedirectResponse(url=f"/remains/feed?remains_id={published.id}", status_code=303)


@router.post("/{remains_id}/delete")
async def delete_remains(
    remains_id: int,
    db: Database,
    researcher: CurrentResearcher,
    carbon_min: Decimal = Form(default=Decimal(0), ge=0, le=200),
):
    if not await soft_delete_remain(remains_id, researcher.id, db):
        raise HTTPException(status_code=404, detail="Опубликованные останки не найдены")
    return RedirectResponse(url=f"/remains?carbon_min={carbon_min:g}", status_code=303)


@router.post("/{remains_id}/likes")
async def like_remains(
    remains_id: int,
    db: Database,
    researcher: CurrentResearcher,
    liked: int = Form(ge=0, le=1),
    view: Literal["feed", "grid"] = Form("feed"),
    carbon_min: Decimal = Form(default=Decimal(0), ge=0, le=200),
    expanded: bool = Form(False),
):
    if not await set_remain_like_record(remains_id, researcher.id, liked, db):
        raise HTTPException(status_code=404, detail="Опубликованные останки не найдены")
    if view == "grid":
        return RedirectResponse(url=f"/remains?carbon_min={carbon_min:g}", status_code=303)
    return RedirectResponse(
        url=f"/remains/feed?remains_id={remains_id}&expanded={'true' if expanded else 'false'}",
        status_code=303,
    )
