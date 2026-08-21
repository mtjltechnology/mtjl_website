from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import settings
from db import create_db_and_tables
from limiter import limiter
from router import larclinica_host_redirect_target, router


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


# larclinicahealth.com e mtjltechnology.com são servidos pelo mesmo uvicorn, então
# sem este guarda toda página do site institucional responderia 200 nos dois
# domínios: conteúdo duplicado no índice, com o domínio errado ganhando a URL.
# O domínio do LarClínica só entrega a própria raiz, o POST do formulário, os
# arquivos estáticos, o robots e o sitemap; o resto volta 301 pro institucional.
# O mesmo guarda leva o domínio sem www para o host canônico, que é o do canonical
# declarado na página.
@app.middleware("http")
async def larclinica_domain_guard(request, call_next):
    target = larclinica_host_redirect_target(request)
    if target is not None:
        query = request.url.query
        if query:
            target = f"{target}?{query}"
        return RedirectResponse(target, status_code=301)
    return await call_next(request)


app.mount("/static/website", StaticFiles(directory="static/website"), name="website_static")

# Os assets de marca passam a ser servidos por esta aplicação, em qualquer ambiente.
# Antes o Nginx mandava /static/ inteiro para o app do produto, que não tinha os
# ícones do PedeMarket, do PilotQA nem do LarClínica: as imagens respondiam 404 em
# produção. O site é dono da própria identidade visual, então serve os próprios
# arquivos, e mantém aqui um superconjunto do que o produto também referencia.
if Path("static/brand").is_dir():
    app.mount("/static/brand", StaticFiles(directory="static/brand"), name="brand_static")

# /static/booking segue com o Nginx apontando para o app do produto, que é dono
# das capturas de tela. Localmente não há Nginx na frente, então o mount abaixo
# cobre isso e qualquer outra pasta de static durante o desenvolvimento.
if settings.app_env != "production" and Path("static").is_dir():
    app.mount("/static", StaticFiles(directory="static"), name="all_static_dev")

app.include_router(router)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
