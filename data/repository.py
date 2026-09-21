from datetime import datetime, timezone
from decimal import Decimal

import psycopg
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import CURRENT_USER_ID, settings
from models import Remains, RemainsLike


def remains_with_likes():
    likes = select(func.count(RemainsLike.id)).where(RemainsLike.remains_id == Remains.id).scalar_subquery()
    return select(Remains, likes.label("likes_count"))


async def get_published_remains(db: AsyncSession, carbon_min: Decimal):
    result = await db.execute(
        remains_with_likes().where(Remains.status == "published", Remains.carbon_14_pmc >= carbon_min).order_by(Remains.id)
    )
    return result.all()


async def get_remains_by_id(db: AsyncSession, remains_id: int):
    result = await db.execute(remains_with_likes().where(Remains.id == remains_id, Remains.status == "published"))
    return result.first()


async def get_next_remains_id(db: AsyncSession, current_id: int):
    following = await db.scalar(select(func.min(Remains.id)).where(Remains.status == "published", Remains.id > current_id))
    if following is not None:
        return following
    return await db.scalar(select(func.min(Remains.id)).where(Remains.status == "published"))


async def get_draft_remains(db: AsyncSession):
    return await db.scalar(select(Remains).where(Remains.creator_id == CURRENT_USER_ID, Remains.status == "draft"))


async def create_draft(db: AsyncSession, title: str):
    draft = Remains(title=title, status="draft", creator_id=CURRENT_USER_ID)
    db.add(draft)
    await db.commit()
    return draft


async def get_draft_for_publication(db: AsyncSession, remains_id: int):
    return await db.scalar(
        select(Remains).where(Remains.id == remains_id, Remains.creator_id == CURRENT_USER_ID, Remains.status == "draft").with_for_update()
    )


async def publish_draft(db: AsyncSession, draft: Remains, title: str, description: str, days: int, carbon: Decimal):
    if draft.carbon_14_pmc != carbon:
        draft.carbon_14_sample = None
        draft.carbon_14_source = None
    draft.title = title
    draft.description = description
    draft.analysis_time_days = days
    draft.carbon_14_pmc = carbon
    draft.status = "published"
    draft.published_at = datetime.now(timezone.utc)
    await db.commit()


async def delete_remains(remains_id: int):
    async with await psycopg.AsyncConnection.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        connect_timeout=5,
    ) as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "UPDATE remains SET status = %s WHERE id = %s AND status = %s RETURNING id",
                ("deleted", remains_id, "published"),
            )
            return await cursor.fetchone() is not None
