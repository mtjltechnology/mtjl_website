from contextlib import asynccontextmanager
from pathlib import Path

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


# As respostas HTML não declaram política de cache, então o navegador aplica
# heurística própria e pode continuar servindo uma página antiga por tempo
# indeterminado. Como é o HTML que carrega a versão do CSS (?v=N), uma página
# em cache também trava a folha de estilo na versão antiga — e a edição parece
# não ter surtido efeito. Em desenvolvimento isso só atrapalha; em produção o
# comportamento fica como está, sob controle do Nginx.
if settings.app_env != "production":
    @app.middleware("http")
    async def no_store_html(request, call_next):
        response = await call_next(request)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response

app.mount("/static/website", StaticFiles(directory="static/website"), name="website_static")

# Em produção o Nginx serve /static/brand e /static/booking direto do disco, então
# a aplicação não precisa montá-los. Localmente não há Nginx na frente: sem este
# mount as logos e screenshots respondem 404 e o site fica sem imagem nenhuma.
if settings.app_env != "production" and Path("static").is_dir():
    app.mount("/static", StaticFiles(directory="static"), name="all_static_dev")

app.include_router(router)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
