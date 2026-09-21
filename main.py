from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uvicorn

from api.handlers import router

PROJECT_ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Organic Remains", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def revalidate_pages(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store" if request.url.path == "/remains/draft" else "no-cache"
    return response


app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
