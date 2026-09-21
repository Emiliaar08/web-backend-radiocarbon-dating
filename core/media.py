import asyncio
from urllib.parse import unquote, urlsplit

import httpx

from core.config import settings

DEFAULT_IMAGE = "/static/images/default.jpg"
DEFAULT_VIDEO = "/static/videos/default.mp4"
ICONS = {
    "carbon": "/static/icons/flask.png",
    "analysis_time": "/static/icons/watch.png",
    "folder": "/static/icons/folder.webp",
}


async def available_media(client: httpx.AsyncClient, url: str | None, kind: str):
    fallback = DEFAULT_IMAGE if kind == "image" else DEFAULT_VIDEO
    if not url:
        return fallback
    try:
        base = urlsplit(settings.MINIO_URL)
        address = urlsplit(url)
    except ValueError:
        return fallback
    path = unquote(address.path)
    if (
        address.scheme != base.scheme
        or address.netloc != base.netloc
        or not path.startswith(base.path.rstrip("/") + "/")
        or ".." in path.split("/")
        or address.query
        or address.fragment
    ):
        return fallback
    try:
        response = await client.head(url)
        content_type = response.headers.get("content-type", "").split(";")[0]
        if response.status_code == 200 and (content_type.startswith(kind + "/") or content_type == "application/octet-stream"):
            return url
    except httpx.HTTPError:
        pass
    return fallback


async def prepare_remains(rows):
    async with httpx.AsyncClient(timeout=1.5, follow_redirects=False, trust_env=False) as client:
        async def prepare(row):
            item, likes_count = row
            image, video = await asyncio.gather(
                available_media(client, item.image_url, "image"),
                available_media(client, item.video_url, "video"),
            )
            return {
                "id": item.id,
                "title": item.title,
                "description": item.description or "",
                "analysis_time_days": item.analysis_time_days,
                "carbon_14_pmc": item.carbon_14_pmc,
                "carbon_14_sample": item.carbon_14_sample,
                "image": image,
                "video": video,
                "image_url": item.image_url or "",
                "video_url": item.video_url or "",
                "likes_count": likes_count,
            }

        return await asyncio.gather(*(prepare(row) for row in rows))
