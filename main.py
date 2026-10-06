from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from api.remains_api import router as api_router
from api.remains_handlers import router
from core.config import PROJECT_ROOT
from db.session import engine


@asynccontextmanager
async def lifespan(app):
    yield
    await engine.dispose()


app = FastAPI(
    title="Radiocarbon Dating API",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def revalidate_pages(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/remains") else "no-cache"
    return response


app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
app.include_router(router)
app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
