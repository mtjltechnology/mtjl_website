from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import settings
from db import create_db_and_tables
from limiter import limiter
from router import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db_and_tables()
    yield


_docs = None if settings.app_env == "production" else "/docs"
_redoc = None if settings.app_env == "production" else "/redoc"
_openapi = None if settings.app_env == "production" else "/openapi.json"
app = FastAPI(lifespan=lifespan, docs_url=_docs, redoc_url=_redoc, openapi_url=_openapi)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static/website", StaticFiles(directory="static/website"), name="website_static")

app.include_router(router)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
