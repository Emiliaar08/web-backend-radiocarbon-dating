import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, Security, status
from fastapi.security import APIKeyCookie
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.session import get_db
from models.researchers import Researchers

SessionCookie = APIKeyCookie(
    name=settings.SESSION_COOKIE_NAME,
    scheme_name="SessionCookie",
    auto_error=False,
)
Database = Annotated[AsyncSession, Depends(get_db)]


def session_key(token: str) -> str:
    return f"radiocarbon:session:{token}"


async def researcher_for_session(token: str | None, request: Request, db: AsyncSession) -> Researchers | None:
    if not token:
        return None
    redis = request.app.state.redis
    session = await redis.hgetall(session_key(token))
    researcher_id = session.get("researcher_id")
    if not researcher_id:
        return None
    return await db.scalar(select(Researchers).where(Researchers.id == int(researcher_id)))


async def get_optional_researcher(request: Request, db: Database) -> Researchers | None:
    return await researcher_for_session(request.cookies.get(settings.SESSION_COOKIE_NAME), request, db)


async def get_current_researcher(
    request: Request,
    db: Database,
    token: Annotated[str | None, Security(SessionCookie)],
) -> Researchers:
    researcher = await researcher_for_session(token, request, db)
    if researcher is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return researcher


async def create_researcher_session(request: Request, researcher: Researchers) -> str:
    token = secrets.token_urlsafe(32)
    redis = request.app.state.redis
    key = session_key(token)
    await redis.hset(
        key,
        mapping={"researcher_id": str(researcher.id), "username": researcher.username},
    )
    await redis.expire(key, settings.SESSION_TTL_SECONDS)
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


async def revoke_researcher_session(request: Request, token: str | None) -> None:
    if token:
        await request.app.state.redis.delete(session_key(token))


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
    )
