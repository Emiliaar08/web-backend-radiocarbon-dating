import math
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from data.collections import CURRENT_USER_ID, icons, materials

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def get_published_materials():
    return [material for material in materials if material["status"] == "published"]


def get_draft_material():
    return next((material for material in materials if material["status"] == "draft"), None)


def get_material_by_id(material_id: int):
    for material in get_published_materials():
        if material["id"] == material_id:
            return material
    return None


def get_next_material(current_id: int):
    published_materials = get_published_materials()
    following = [item for item in published_materials if item["id"] > current_id]
    return min(following or published_materials, key=lambda item: item["id"], default=None)


def get_likes_count(material):
    return len(material["likes"])


def is_liked_by_current_user(material):
    return any(like["user_id"] == CURRENT_USER_ID for like in material["likes"])


def parse_mass_range(mass_text: str):
    clean_value = (
        mass_text.lower()
        .replace("мг", "")
        .replace(",", ".")
        .replace(" ", "")
    )

    if not re.fullmatch(r"\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?", clean_value):
        raise ValueError("Введите массу или диапазон положительных чисел")
    values = [float(value) for value in clean_value.split("-")]
    start, end = values[0], values[-1]
    if not all(math.isfinite(value) for value in values) or start > end:
        raise ValueError("Некорректный диапазон массы")
    return start, end


def material_matches_mass(material, mass_query: str):
    if not mass_query:
        return True

    try:
        material_min, material_max = parse_mass_range(material["mass"])
        query_min, query_max = parse_mass_range(mass_query)
    except ValueError:
        return False

    return material_min <= query_max and query_min <= material_max


def prepare_materials_for_template(source_materials):
    prepared_materials = []

    for material in source_materials:
        prepared_material = material.copy()
        prepared_material["likes_count"] = get_likes_count(material)
        prepared_material["liked"] = is_liked_by_current_user(material)
        prepared_material["unliked_count"] = get_likes_count(material) - int(prepared_material["liked"])
        prepared_materials.append(prepared_material)

    return prepared_materials


def page_context(active_page: str, **extra):
    return {
        "active_page": active_page,
        "icons": icons,
        "style_version": Path("static/css/style.css").stat().st_mtime_ns,
        **extra,
    }


@router.get("/", include_in_schema=False)
@router.get("/feed", include_in_schema=False)
@router.get("/feed/{material_id}")
def feed_page(
    request: Request,
    material_id: int | None = None,
    next: bool = False,
    expanded: bool = False,
):
    if material_id is None or next:
        material = get_next_material(material_id if material_id is not None else -1)
        if material is None:
            raise HTTPException(status_code=404, detail="Нет опубликованных материалов")
        return RedirectResponse(url=f"/feed/{material['id']}", status_code=303)

    material = get_material_by_id(material_id)

    if material is None:
        raise HTTPException(status_code=404, detail="Материал не найден")

    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context=page_context(
            "feed",
            material=material,
            likes_count=get_likes_count(material),
            liked=is_liked_by_current_user(material),
            unliked_count=get_likes_count(material) - int(is_liked_by_current_user(material)),
            expanded=expanded,
        ),
    )


@router.get("/add")
def add_page(request: Request):
    draft_material = get_draft_material()
    if draft_material is None:
        raise HTTPException(status_code=404, detail="Черновик не найден")
    return templates.TemplateResponse(
        request=request,
        name="add.html",
        context=page_context("add", draft_material=draft_material),
    )


@router.get("/grid")
def grid_page(request: Request, mass: str = "", sample_mass_filter: str = ""):
    mass_query = sample_mass_filter or mass
    filtered_materials = [
        material
        for material in get_published_materials()
        if material_matches_mass(material, mass_query)
    ]

    return templates.TemplateResponse(
        request=request,
        name="grid.html",
        context=page_context(
            "grid",
            materials=prepare_materials_for_template(filtered_materials),
            mass=mass_query,
        ),
    )
