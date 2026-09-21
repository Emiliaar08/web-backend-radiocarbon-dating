from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, StringConstraints, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import PROJECT_ROOT
from core.media import DEFAULT_IMAGE, DEFAULT_VIDEO, ICONS, prepare_remains
from data import repository
from db.session import get_db

router = APIRouter(prefix="/remains")
templates = Jinja2Templates(directory=PROJECT_ROOT / "templates")
Database = Annotated[AsyncSession, Depends(get_db)]
RemainsTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


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


async def draft_response(request: Request, draft, values=None, errors=None, status_code=200):
    if draft is not None:
        draft_values = (await prepare_remains([(draft, 0)]))[0]
    else:
        draft_values = {
            "title": "", "description": "", "analysis_time_days": "", "carbon_14_pmc": "",
            "image": DEFAULT_IMAGE, "video": DEFAULT_VIDEO, "image_url": "", "video_url": "",
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
    row = await repository.get_remains_by_id(db, remains_id) if remains_id is not None else None
    if remains_id is not None and row is None:
        raise HTTPException(status_code=404, detail="Останки не найдены или не опубликованы")
    if remains_id is None or next:
        following = await repository.get_next_remains_id(db, remains_id if remains_id is not None else -1)
        if following is None:
            raise HTTPException(status_code=404, detail="Пока нет опубликованных останков")
        return RedirectResponse(url=f"/remains/feed?remains_id={following}", status_code=303)
    item = (await prepare_remains([row]))[0]
    return templates.TemplateResponse(
        request=request, name="feed.html", context=page_context("feed", remains_item=item, expanded=expanded)
    )


@router.get("/draft")
async def remains_draft(request: Request, db: Database):
    return await draft_response(request, await repository.get_draft_remains(db))


@router.get("")
async def remains_grid(request: Request, db: Database, carbon_min: Decimal = Query(default=Decimal(0), ge=0, le=200)):
    rows = await repository.get_published_remains(db, carbon_min)
    return templates.TemplateResponse(
        request=request,
        name="grid.html",
        context=page_context("grid", remains=await prepare_remains(rows), carbon_min=carbon_min),
    )


@router.post("/draft")
async def create_remains(request: Request, db: Database, title: str = Form("")):
    if await repository.get_draft_remains(db) is not None:
        return RedirectResponse(url="/remains/draft", status_code=303)
    try:
        fields = DraftFields(title=title)
    except ValidationError as error:
        return await draft_response(request, None, {"title": title}, form_errors(error), 422)
    try:
        await repository.create_draft(db, fields.title)
    except IntegrityError as error:
        await db.rollback()
        if await repository.get_draft_remains(db) is None:
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
    draft = await repository.get_draft_for_publication(db, remains_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Черновик не найден или уже опубликован")
    values = {"title": title, "description": description, "analysis_time_days": analysis_time_days, "carbon_14_pmc": carbon_14_pmc}
    try:
        fields = PublicationFields(**values)
    except ValidationError as error:
        return await draft_response(request, draft, values, form_errors(error), 422)
    await repository.publish_draft(db, draft, fields.title, fields.description, fields.analysis_time_days, fields.carbon_14_pmc)
    return RedirectResponse(url=f"/remains/feed?remains_id={draft.id}", status_code=303)


@router.post("/{remains_id}/delete")
async def delete_remains(remains_id: int, carbon_min: Decimal = Form(default=Decimal(0), ge=0, le=200)):
    if not await repository.delete_remains(remains_id):
        raise HTTPException(status_code=404, detail="Опубликованные останки не найдены")
    return RedirectResponse(url=f"/remains?carbon_min={carbon_min:g}", status_code=303)
