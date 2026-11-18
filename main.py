from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from db import create_db_and_tables
from limiter import limiter
from router import is_larclinica_host, larclinica_host_redirect_target, router, templates


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

_404_TEXT = {
    "pt": {"title": "Página não encontrada", "text": "O link está quebrado ou a página mudou de endereço.", "home": "Voltar ao início", "contact": "Fale com a gente"},
    "en": {"title": "Page not found", "text": "The link is broken or the page has moved.", "home": "Back to home", "contact": "Contact us"},
    "es": {"title": "Página no encontrada", "text": "El enlace está roto o la página cambió de dirección.", "home": "Volver al inicio", "contact": "Contáctanos"},
}


@app.exception_handler(StarletteHTTPException)
async def not_found_page(request: Request, exc: StarletteHTTPException):
    # Só navegador recebe a página; API, imagem e fetch seguem com o JSON padrão.
    if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
        lang = request.url.path.split("/")[1] if request.url.path[:4] in ("/en/", "/es/") or request.url.path in ("/en", "/es") else "pt"
        lang = lang if lang in ("en", "es") else "pt"
        home = "/" if lang == "pt" else f"/{lang}"
        return templates.TemplateResponse("404.html", {"request": request, "lang": lang, "t": _404_TEXT[lang], "home": home}, status_code=404)
    return await http_exception_handler(request, exc)


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


_LARCLINICA_FAVICON = Path("static/brand/larclinica-favicon.ico")


@app.get("/favicon.ico", include_in_schema=False)
def favicon(request: Request) -> Response:
    # O <link rel="icon"> da página já aponta o arquivo certo, mas o Google (e
    # browser antigo) busca /favicon.ico direto na raiz do domínio ao montar o
    # resultado de busca. Um 204 ali faz o resultado sair sem ícone.
    if is_larclinica_host(request) and _LARCLINICA_FAVICON.is_file():
        return FileResponse(_LARCLINICA_FAVICON, media_type="image/x-icon")
    return Response(status_code=204)
