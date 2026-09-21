from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from data.collections import CURRENT_USER_ID, icons, remains

PROJECT_ROOT = Path(__file__).resolve().parent.parent
router = APIRouter(prefix="/remains")
templates = Jinja2Templates(directory=PROJECT_ROOT / "templates")


def get_published_remains():
    return [item for item in remains if item["status"] == "published"]


def get_draft_remains():
    return next((item for item in remains if item["status"] == "draft"), None)


def get_remains_by_id(remains_id: int):
    return next((item for item in get_published_remains() if item["id"] == remains_id), None)


def get_next_remains(current_id: int):
    published_remains = get_published_remains()
    following = [item for item in published_remains if item["id"] > current_id]
    return min(following or published_remains, key=lambda item: item["id"], default=None)


def get_likes_count(remains_item):
    return len(remains_item["likes"])


def is_liked_by_current_user(remains_item):
    return any(like["user_id"] == CURRENT_USER_ID for like in remains_item["likes"])


def prepare_remains_for_template(source_remains):
    prepared_remains = []
    for item in source_remains:
        prepared = item.copy()
        prepared["likes_count"] = get_likes_count(item)
        prepared["liked"] = is_liked_by_current_user(item)
        prepared["unliked_count"] = prepared["likes_count"] - int(prepared["liked"])
        prepared_remains.append(prepared)
    return prepared_remains


def page_context(active_page: str, **extra):
    return {
        "active_page": active_page,
        "icons": icons,
        "style_version": (PROJECT_ROOT / "static/css/style.css").stat().st_mtime_ns,
        **extra,
    }


@router.get("/feed")
def remains_feed(
    request: Request,
    remains_id: int | None = None,
    next: bool = False,
    expanded: bool = False,
):
    if remains_id is not None and get_remains_by_id(remains_id) is None:
        raise HTTPException(status_code=404, detail="Останки не найдены")
    if remains_id is None or next:
        item = get_next_remains(remains_id if remains_id is not None else -1)
        if item is None:
            raise HTTPException(status_code=404, detail="Нет опубликованных останков")
        return RedirectResponse(url=f"/remains/feed?remains_id={item['id']}", status_code=303)
    item = prepare_remains_for_template([get_remains_by_id(remains_id)])[0]
    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context=page_context("feed", remains_item=item, expanded=expanded),
    )


@router.get("/draft")
def remains_draft(request: Request):
    draft_remains = get_draft_remains()
    if draft_remains is None:
        raise HTTPException(status_code=404, detail="Черновик не найден")
    return templates.TemplateResponse(
        request=request,
        name="add.html",
        context=page_context("draft", draft_remains=draft_remains),
    )


@router.get("")
def remains_grid(request: Request, carbon_min: float = Query(default=0, ge=0, le=200)):
    filtered_remains = [
        item for item in get_published_remains() if item["carbon_14_pmc"] >= carbon_min
    ]
    return templates.TemplateResponse(
        request=request,
        name="grid.html",
        context=page_context(
            "grid", remains=prepare_remains_for_template(filtered_remains), carbon_min=carbon_min
        ),
    )
