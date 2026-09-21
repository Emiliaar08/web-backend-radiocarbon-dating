from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
import uvicorn

from api.handlers import page_context, router, templates
from core.config import PROJECT_ROOT
from db.session import engine


@asynccontextmanager
async def lifespan(app):
    yield
    await engine.dispose()


app = FastAPI(title="Organic Remains", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def revalidate_pages(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/remains") else "no-cache"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, error):
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context=page_context("grid", status_code=error.status_code, detail=error.detail),
        status_code=error.status_code,
        headers=error.headers,
    )


app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
