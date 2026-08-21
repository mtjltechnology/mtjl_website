import re
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from config import settings
from db import get_session
from limiter import limiter
from models import PilotQASubscriber
from services.asaas import PLANS, create_customer, create_subscription, get_subscription_payment_link, update_customer
from services.email import LARCLINICA_CONTACT_TO, send_contact_email, send_pilotqa_contact_email, send_pilotqa_token_email
from services.token import generate_pilotqa_token

router = APIRouter()

templates = Jinja2Templates(directory="templates", auto_reload=settings.app_env != "production")


def _to_brt(dt):
    if dt is None:
        return dt
    return dt + timedelta(hours=-3)


templates.env.filters["brt"] = _to_brt


SITE_BASE_URL = "https://mtjltechnology.com"

# O LarClínica saiu de mtjltechnology.com/larclinica e passou a ter domínio próprio.
# A página institucional continua sendo servida por esta aplicação: o Nginx tem um
# vhost para larclinicahealth.com apontando para o mesmo uvicorn, e as rotas abaixo
# decidem o que entregar pelo cabeçalho Host. O caminho antigo virou 301 permanente.
LARCLINICA_CANONICAL_HOST = "www.larclinicahealth.com"
LARCLINICA_BASE_URL = f"https://{LARCLINICA_CANONICAL_HOST}"
LARCLINICA_HOSTS = frozenset({"larclinicahealth.com", LARCLINICA_CANONICAL_HOST})

# Só estes caminhos existem no domínio do LarClínica. Qualquer outro é página do
# site institucional: sem o 301 de volta para mtjltechnology.com o mesmo HTML
# responderia 200 nos dois domínios, o que é conteúdo duplicado no índice.
_LARCLINICA_ALLOWED_PATHS = frozenset({
    "/",
    "/larclinica",
    "/larclinica_contact",
    "/robots.txt",
    "/sitemap.xml",
    "/favicon.ico",
})
_LARCLINICA_ALLOWED_PREFIXES = ("/static/",)

_SITEMAP_PAGES = [
    {"slug": "", "en": "/en", "es": "/es"},
    {"slug": "relatify-beauty", "en": "/en/relatify-beauty", "es": "/es/relatify-beauty"},
    {"slug": "testes-de-software", "en": "/en/software-testing", "es": "/es/pruebas-de-software"},
    # O PedeMarket não tem tradução real: en/es=None evita declarar hreflang
    # alternado apontando pra a própria URL em pt (sitemap_xml só emite o bloco
    # de alternates quando existe mais de uma variante). O LarClínica saiu daqui
    # porque mora em larclinicahealth.com, que tem sitemap próprio.
    {"slug": "pedemarket", "en": None, "es": None},
    {"slug": "pilotqa-ai", "en": "/en/pilotqa-ai", "es": "/es/pilotqa-ai"},
    {"slug": "desenvolvimento-de-software", "en": "/en/software-development", "es": "/es/desarrollo-de-software"},
    {"slug": "inteligencia-artificial", "en": "/en/artificial-intelligence", "es": "/es/inteligencia-artificial"},
]


# ── Bloqueio de e-mails de teste/descartáveis ───────────────────────────────────
# Mesma lista de booking/routers/auth.py::_is_blocked_email no repo do produto —
# duplicada aqui porque os dois serviços não compartilham módulos Python.

_BLOCKED_EMAIL_DOMAINS = {
    "teste.com", "test.com", "testing.com", "testando.com",
    "example.com", "example.org", "example.net",
    "qa.com", "dev.com", "fake.com", "dummy.com",
    "lixo.com", "temp.com", "noreply.com",
    "mailtest.com", "emailtest.com",
}

_BLOCKED_EMAIL_LOCAL_PATTERN = re.compile(
    r"^(teste|test|testing|testando|qa|dummy|fake|lixo|temp|noreply|abc123|xxx|asdf|qwerty)\d*$",
    re.IGNORECASE,
)


def _is_blocked_email(email: str) -> bool:
    email = email.strip().lower()
    if "@" not in email:
        return False
    local, domain = email.rsplit("@", 1)
    if domain in _BLOCKED_EMAIL_DOMAINS:
        return True
    if _BLOCKED_EMAIL_LOCAL_PATTERN.match(local):
        return True
    return False


def _client_ip(request: Request):
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or None
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip() or None
    return request.client.host if request.client else None


def _request_host(request: Request) -> str:
    return (request.headers.get("host") or "").split(":", 1)[0].strip().lower()


def is_larclinica_host(request: Request) -> bool:
    return _request_host(request) in LARCLINICA_HOSTS


def larclinica_host_redirect_target(request: Request) -> str | None:
    """Para onde redirecionar uma requisição feita no domínio do LarClínica, ou
    None quando ela deve ser servida como está.

    Duas situações geram redirecionamento: o domínio sem www, que precisa cair no
    host canônico (www), e qualquer caminho que seja página do site institucional,
    que volta para mtjltechnology.com."""
    if not is_larclinica_host(request):
        return None
    path = request.url.path
    if _request_host(request) != LARCLINICA_CANONICAL_HOST:
        return LARCLINICA_BASE_URL + path
    if path in _LARCLINICA_ALLOWED_PATHS or path.startswith(_LARCLINICA_ALLOWED_PREFIXES):
        return None
    return SITE_BASE_URL + path


def _redirect_preserving_query(request: Request, target: str, status_code: int = 301):
    query = request.url.query
    if query:
        target = f"{target}?{query}"
    return RedirectResponse(target, status_code=status_code)


def _sitemap_xml_document(url_entries: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        f"{url_entries}\n"
        "</urlset>"
    )


@router.get("/sitemap.xml")
def sitemap_xml(request: Request):
    lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url_entries = []

    # O domínio do LarClínica tem uma página só, a raiz, e nenhuma variante de
    # idioma: o sitemap dele não passa por _SITEMAP_PAGES, que é do institucional.
    if is_larclinica_host(request):
        loc = escape(LARCLINICA_BASE_URL + "/")
        body = f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>"
        return Response(content=_sitemap_xml_document(body), media_type="application/xml")

    for page in _SITEMAP_PAGES:
        pt_path = f"/{page['slug']}" if page["slug"] else "/"
        variants = {"pt-BR": pt_path}
        if page["en"]:
            variants["en"] = page["en"]
        if page["es"]:
            variants["es"] = page["es"]

        # Só declara alternates de hreflang quando existe mais de uma variante
        # de idioma de verdade — evita apontar en/es pra a própria URL pt.
        alternates = ""
        if len(variants) > 1:
            alternates = "\n".join(
                f'    <xhtml:link rel="alternate" hreflang="{alt_lang}" href="{escape(SITE_BASE_URL + alt_path)}" />'
                for alt_lang, alt_path in variants.items()
            )
            alternates += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{escape(SITE_BASE_URL + pt_path)}" />'

        for path in variants.values():
            loc = SITE_BASE_URL + path
            block = f"  <url>\n    <loc>{escape(loc)}</loc>\n"
            if alternates:
                block += f"{alternates}\n"
            block += f"    <lastmod>{lastmod}</lastmod>\n  </url>"
            url_entries.append(block)

    return Response(content=_sitemap_xml_document("\n".join(url_entries)), media_type="application/xml")


@router.get("/robots.txt")
def robots_txt(request: Request):
    base = LARCLINICA_BASE_URL if is_larclinica_host(request) else SITE_BASE_URL
    body = "User-agent: *\nAllow: /\n\nSitemap: " + base + "/sitemap.xml\n"
    return Response(content=body, media_type="text/plain")


@router.get("/", response_class=HTMLResponse)
def home(request: Request, sent: bool = False, pq_sent: bool = False):
    # A raiz de larclinicahealth.com é a página do LarClínica, não a home do
    # institucional: mesma aplicação, template escolhido pelo Host.
    if is_larclinica_host(request):
        return templates.TemplateResponse("larclinica.html", {
            "request": request,
            "sent": sent,
            "google_site_verification": settings.larclinica_google_site_verification,
        })
    return templates.TemplateResponse("home.html", {"request": request, "sent": sent, "pq_sent": pq_sent})


@router.get("/en", response_class=HTMLResponse)
def home_en(request: Request, sent: bool = False, pq_sent: bool = False):
    return templates.TemplateResponse("home_en.html", {"request": request, "sent": sent, "pq_sent": pq_sent})


@router.get("/es", response_class=HTMLResponse)
def home_es(request: Request, sent: bool = False, pq_sent: bool = False):
    return templates.TemplateResponse("home_es.html", {"request": request, "sent": sent, "pq_sent": pq_sent})


@router.get("/pilotqa-ai", response_class=HTMLResponse)
def pilotqa(request: Request, pq_sent: bool = False):
    return templates.TemplateResponse("pilotqa.html", {"request": request, "pq_sent": pq_sent})


@router.get("/pilotqa_ai")
def pilotqa_legacy(request: Request):
    return _redirect_preserving_query(request, "/pilotqa-ai")


@router.get("/en/pilotqa-ai", response_class=HTMLResponse)
def pilotqa_en(request: Request, pq_sent: bool = False):
    return templates.TemplateResponse("pilotqa_en.html", {"request": request, "pq_sent": pq_sent})


@router.get("/en/pilotqa_ai")
def pilotqa_en_legacy(request: Request):
    return _redirect_preserving_query(request, "/en/pilotqa-ai")


@router.get("/es/pilotqa-ai", response_class=HTMLResponse)
def pilotqa_es(request: Request, pq_sent: bool = False):
    return templates.TemplateResponse("pilotqa_es.html", {"request": request, "pq_sent": pq_sent})


@router.get("/es/pilotqa_ai")
def pilotqa_es_legacy(request: Request):
    return _redirect_preserving_query(request, "/es/pilotqa-ai")


@router.get("/larclinica")
def larclinica_legacy(request: Request):
    """Endereço aposentado. O conteúdo mora na raiz de larclinicahealth.com."""
    return _redirect_preserving_query(request, LARCLINICA_BASE_URL + "/")


@router.post("/larclinica_contact")
@limiter.limit("5/minute")
def larclinica_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    organization: str = Form(default=""),
    message: str = Form(...),
    lang: str = Form(default="pt"),
):
    # O formulário vive na raiz do domínio do LarClínica. Um POST vindo de outro
    # host (página antiga em cache, por exemplo) volta para lá pela URL absoluta.
    redirect_url = "/?sent=1" if is_larclinica_host(request) else f"{LARCLINICA_BASE_URL}/?sent=1"
    if _is_blocked_email(email):
        return RedirectResponse(redirect_url, status_code=303)
    org_line = f"Organização/Operadora: {organization}\n\n" if organization else ""
    send_contact_email(name, email, f"[LarClínica] {org_line}{message}", to=LARCLINICA_CONTACT_TO)
    return RedirectResponse(redirect_url, status_code=303)


@router.get("/pedemarket", response_class=HTMLResponse)
def pedemarket(request: Request, sent: bool = False):
    return templates.TemplateResponse("pedemarket.html", {"request": request, "sent": sent})


@router.post("/pedemarket_contact")
@limiter.limit("5/minute")
def pedemarket_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    organization: str = Form(default=""),
    message: str = Form(...),
    lang: str = Form(default="pt"),
):
    redirect_url = "/pedemarket?sent=1"
    if _is_blocked_email(email):
        return RedirectResponse(redirect_url, status_code=303)
    org_line = f"Mercado: {organization}\n\n" if organization else ""
    send_contact_email(name, email, f"[PedeMarket] {org_line}{message}")
    return RedirectResponse(redirect_url, status_code=303)


@router.get("/desenvolvimento-de-software", response_class=HTMLResponse)
def desenvolvimento(request: Request, sent: bool = False):
    return templates.TemplateResponse("desenvolvimento.html", {"request": request, "sent": sent})


@router.post("/desenvolvimento_contact")
@limiter.limit("5/minute")
def desenvolvimento_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    organization: str = Form(default=""),
    message: str = Form(...),
    lang: str = Form(default="pt"),
):
    redirect_url = "/desenvolvimento-de-software?sent=1"
    if lang == "en":
        redirect_url = "/en/software-development?sent=1"
    elif lang == "es":
        redirect_url = "/es/desarrollo-de-software?sent=1"
    if _is_blocked_email(email):
        return RedirectResponse(redirect_url, status_code=303)
    org_line = f"Empresa: {organization}\n\n" if organization else ""
    send_contact_email(name, email, f"[Desenvolvimento] {org_line}{message}")
    return RedirectResponse(redirect_url, status_code=303)


@router.get("/inteligencia-artificial", response_class=HTMLResponse)
def inteligencia_artificial(request: Request, sent: bool = False):
    return templates.TemplateResponse("inteligencia_artificial.html", {"request": request, "sent": sent})


@router.post("/inteligencia_artificial_contact")
@limiter.limit("5/minute")
def inteligencia_artificial_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    organization: str = Form(default=""),
    message: str = Form(...),
    lang: str = Form(default="pt"),
):
    redirect_url = "/inteligencia-artificial?sent=1"
    if lang == "en":
        redirect_url = "/en/artificial-intelligence?sent=1"
    elif lang == "es":
        redirect_url = "/es/inteligencia-artificial?sent=1"
    if _is_blocked_email(email):
        return RedirectResponse(redirect_url, status_code=303)
    org_line = f"Empresa: {organization}\n\n" if organization else ""
    send_contact_email(name, email, f"[Inteligência Artificial] {org_line}{message}")
    return RedirectResponse(redirect_url, status_code=303)


@router.get("/en/software-development", response_class=HTMLResponse)
def desenvolvimento_en(request: Request, sent: bool = False):
    return templates.TemplateResponse("desenvolvimento_en.html", {"request": request, "sent": sent})


@router.get("/en/artificial-intelligence", response_class=HTMLResponse)
def inteligencia_artificial_en(request: Request, sent: bool = False):
    return templates.TemplateResponse("inteligencia_artificial_en.html", {"request": request, "sent": sent})


@router.get("/es/desarrollo-de-software", response_class=HTMLResponse)
def desenvolvimento_es(request: Request, sent: bool = False):
    return templates.TemplateResponse("desenvolvimento_es.html", {"request": request, "sent": sent})


@router.get("/es/inteligencia-artificial", response_class=HTMLResponse)
def inteligencia_artificial_es(request: Request, sent: bool = False):
    return templates.TemplateResponse("inteligencia_artificial_es.html", {"request": request, "sent": sent})


@router.get("/testes-de-software", response_class=HTMLResponse)
def testes_software(request: Request, sent: bool = False):
    return templates.TemplateResponse("testes_software.html", {"request": request, "sent": sent})


@router.get("/qualityassurance")
def testes_software_legacy(request: Request):
    return _redirect_preserving_query(request, "/testes-de-software")


@router.get("/en/software-testing", response_class=HTMLResponse)
def testes_software_en(request: Request, sent: bool = False):
    return templates.TemplateResponse("testes_software_en.html", {"request": request, "sent": sent})


@router.get("/en/qualityassurance")
def testes_software_en_legacy(request: Request):
    return _redirect_preserving_query(request, "/en/software-testing")


@router.get("/es/pruebas-de-software", response_class=HTMLResponse)
def testes_software_es(request: Request, sent: bool = False):
    return templates.TemplateResponse("testes_software_es.html", {"request": request, "sent": sent})


@router.get("/es/qualityassurance")
def testes_software_es_legacy(request: Request):
    return _redirect_preserving_query(request, "/es/pruebas-de-software")


_BB_ERRORS = {
    "email": "Este e-mail já possui uma conta cadastrada. Acesse o sistema ou recupere sua senha.",
    "phone": "Este telefone já está associado a outra conta. Verifique o número ou entre em contato.",
    "terms": "Você precisa aceitar os Termos de Serviço para continuar.",
    "invalid_email": "Este endereço de e-mail não é permitido. Use um e-mail profissional válido.",
    "security": "Verificação de segurança falhou. Tente novamente.",
    "invalid_plan": "Plano inválido.",
    "unavailable": "Não foi possível concluir o cadastro agora. Tente novamente em instantes.",
}

_BB_ERRORS_EN = {
    "email": "This email already has an account registered. Log in or recover your password.",
    "phone": "This phone number is already associated with another account. Check the number or contact us.",
    "terms": "You need to accept the Terms of Service to continue.",
    "invalid_email": "This email address is not allowed. Please use a valid professional email.",
    "security": "Security verification failed. Please try again.",
    "invalid_plan": "Invalid plan.",
    "unavailable": "We couldn't complete the signup right now. Please try again shortly.",
}

_BB_ERRORS_ES = {
    "email": "Este correo electrónico ya tiene una cuenta registrada. Accede al sistema o recupera tu contraseña.",
    "phone": "Este teléfono ya está asociado a otra cuenta. Verifica el número o contáctanos.",
    "terms": "Debes aceptar los Términos de Servicio para continuar.",
    "invalid_email": "Este correo electrónico no está permitido. Usa un correo profesional válido.",
    "security": "La verificación de seguridad falló. Inténtalo de nuevo.",
    "invalid_plan": "Plan inválido.",
    "unavailable": "No pudimos completar el registro ahora. Inténtalo de nuevo en unos instantes.",
}

@router.get("/relatify-beauty", response_class=HTMLResponse)
def booking_beauty(request: Request, bb_sent: bool = False, bb_subscribed: bool = False, bb_error: str = ""):
    return templates.TemplateResponse("booking_beauty.html", {
        "request": request,
        "bb_sent": bb_sent,
        "bb_subscribed": bb_subscribed,
        "bb_error": _BB_ERRORS.get(bb_error, ""),
    })


@router.get("/relatify_beauty")
def booking_beauty_slug_legacy(request: Request):
    return _redirect_preserving_query(request, "/relatify-beauty")


@router.get("/en/relatify-beauty", response_class=HTMLResponse)
def booking_beauty_en(request: Request, bb_sent: bool = False, bb_subscribed: bool = False, bb_error: str = ""):
    return templates.TemplateResponse("booking_beauty_en.html", {
        "request": request,
        "bb_sent": bb_sent,
        "bb_subscribed": bb_subscribed,
        "bb_error": _BB_ERRORS_EN.get(bb_error, ""),
    })


@router.get("/en/relatify_beauty")
def booking_beauty_en_slug_legacy(request: Request):
    return _redirect_preserving_query(request, "/en/relatify-beauty")


@router.get("/es/relatify-beauty", response_class=HTMLResponse)
def booking_beauty_es(request: Request, bb_sent: bool = False, bb_subscribed: bool = False, bb_error: str = ""):
    return templates.TemplateResponse("booking_beauty_es.html", {
        "request": request,
        "bb_sent": bb_sent,
        "bb_subscribed": bb_subscribed,
        "bb_error": _BB_ERRORS_ES.get(bb_error, ""),
    })


@router.get("/es/relatify_beauty")
def booking_beauty_es_slug_legacy(request: Request):
    return _redirect_preserving_query(request, "/es/relatify-beauty")


# ── Rename do produto: BookingAI Beauty → RelatifyAI Beauty ────────────────────
# A URL /booking_beauty circulou em anúncios, links externos e no índice do Google.
# 301 (permanente) preserva o ranking acumulado e transfere para a URL nova.
# Não cobre /booking_beauty/login nem /booking_beauty/termos: essas rotas são do
# app do produto, roteadas pelo Nginx, e não passam por este serviço.

def _redirect_legacy_bb(request: Request, prefix: str = ""):
    return _redirect_preserving_query(request, f"{prefix}/relatify-beauty")


@router.get("/booking_beauty")
def booking_beauty_legacy(request: Request):
    return _redirect_legacy_bb(request)


@router.get("/en/booking_beauty")
def booking_beauty_legacy_en(request: Request):
    return _redirect_legacy_bb(request, "/en")


@router.get("/es/booking_beauty")
def booking_beauty_legacy_es(request: Request):
    return _redirect_legacy_bb(request, "/es")


@router.post("/contact")
@limiter.limit("5/minute")
def contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...),
    lang: str = Form(default="pt"),
):
    prefix = f"/{lang}" if lang in ("en", "es") else ""
    redirect_url = f"{prefix}/?sent=1" if prefix else "/?sent=1"
    # E-mails de domínios de teste/descartáveis: fingimos sucesso sem enviar
    if _is_blocked_email(email):
        return RedirectResponse(redirect_url, status_code=303)
    send_contact_email(name, email, message)
    return RedirectResponse(redirect_url, status_code=303)


BB_PLANS = {"bb_starter", "bb_pro"}


@router.post("/relatify_beauty/subscribe")
@limiter.limit("5/minute")
async def booking_beauty_subscribe(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    plan: str = Form(...),
    phone: str = Form(default=""),
    accept_terms: str | None = Form(default=None),
    lang: str = Form(default="pt"),
    website: str = Form(default=""),
    recaptcha_token: str = Form(default=""),
):
    prefix = f"/{lang}" if lang in ("en", "es") else ""

    if plan not in BB_PLANS:
        raise HTTPException(status_code=400, detail="Plano inválido.")

    # Honeypot: campo invisível para humanos, só bots preenchem.
    # Fingimos sucesso para não ensinar o bot a identificar o bloqueio.
    if website:
        return RedirectResponse(f"{prefix}/relatify-beauty?bb_subscribed=1", status_code=303)

    payload = {
        "name": name,
        "email": email,
        "plan": plan,
        "phone": phone,
        "accept_terms": bool(accept_terms),
        "recaptcha_token": recaptcha_token,
        "terms_ip": _client_ip(request),
        "terms_user_agent": (request.headers.get("user-agent") or "")[:512] or None,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{settings.booking_internal_url}/internal/booking-beauty/trial-signup",
                json=payload,
                headers={"X-Master-Key": settings.booking_master_api_key},
            )
        result = r.json()
    except Exception:
        return RedirectResponse(f"{prefix}/relatify-beauty?bb_error=unavailable&plan={plan}", status_code=303)

    if not result.get("ok"):
        error = result.get("error", "unavailable")
        return RedirectResponse(f"{prefix}/relatify-beauty?bb_error={error}&plan={plan}", status_code=303)

    return RedirectResponse(f"{prefix}/relatify-beauty?bb_subscribed=1", status_code=303)


@router.post("/relatify_beauty_contact")
@limiter.limit("5/minute")
def booking_beauty_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    whatsapp: str = Form(default=""),
    message: str = Form(...),
    lang: str = Form(default="pt"),
    website: str = Form(default=""),
):
    prefix = f"/{lang}" if lang in ("en", "es") else ""
    redirect_url = f"{prefix}/relatify-beauty?bb_sent=1"
    # Honeypot preenchido ou e-mail de domínio bloqueado: fingimos sucesso silenciosamente
    if website or _is_blocked_email(email):
        return RedirectResponse(redirect_url, status_code=303)
    send_contact_email(name, email, f"[Booking AI Beauty] WhatsApp: {whatsapp}\n\n{message}")
    return RedirectResponse(redirect_url, status_code=303)


@router.post("/qualityassurance_contact")
@limiter.limit("5/minute")
def testes_software_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...),
    lang: str = Form(default="pt"),
):
    if lang == "en":
        redirect_url = "/en/software-testing?sent=1"
    elif lang == "es":
        redirect_url = "/es/pruebas-de-software?sent=1"
    else:
        redirect_url = "/testes-de-software?sent=1"
    if _is_blocked_email(email):
        return RedirectResponse(redirect_url, status_code=303)
    send_contact_email(name, email, f"[Testes de Software] {message}")
    return RedirectResponse(redirect_url, status_code=303)


@router.post("/pilotqa_contact")
@limiter.limit("5/minute")
def pilotqa_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...),
    origin: str = Form(default="home"),
    lang: str = Form(default="pt"),
):
    prefix = f"/{lang}" if lang in ("en", "es") else ""
    page = "/pilotqa-ai" if origin == "pilotqa" else "/"
    if page == "/":
        redirect = f"{prefix}/?pq_sent=1" if prefix else "/?pq_sent=1"
    else:
        redirect = f"{prefix}{page}?pq_sent=1"
    if _is_blocked_email(email):
        return RedirectResponse(redirect, status_code=303)
    send_pilotqa_contact_email(name, email, message)
    return RedirectResponse(redirect, status_code=303)


@router.post("/pilotqa_ai/subscribe")
@limiter.limit("5/minute")
def pilotqa_subscribe(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    plan: str = Form(...),
    cpf_cnpj: str = Form(default=""),
    session: Session = Depends(get_session),
):
    if plan not in PLANS:
        raise HTTPException(status_code=400, detail="Plano inválido.")

    if _is_blocked_email(email):
        raise HTTPException(status_code=400, detail="E-mail inválido.")

    if not settings.asaas_api_key:
        raise HTTPException(status_code=503, detail="Pagamento não configurado.")

    cpf_cnpj_clean = re.sub(r"\D", "", cpf_cnpj)

    subscriber = session.exec(
        select(PilotQASubscriber).where(PilotQASubscriber.email == email)
    ).first()

    if not subscriber:
        subscriber = PilotQASubscriber(name=name, email=email, plan=plan)
        session.add(subscriber)
        session.commit()
        session.refresh(subscriber)

    if not subscriber.asaas_customer_id:
        customer = create_customer(name, email, cpf_cnpj_clean)
        subscriber.asaas_customer_id = customer["id"]
        session.add(subscriber)
        session.commit()
    elif cpf_cnpj_clean:
        update_customer(subscriber.asaas_customer_id, cpf_cnpj_clean)

    plan_info = PLANS[plan]
    sub = create_subscription(subscriber.asaas_customer_id, plan_info["value"], plan_info["description"])
    subscriber.asaas_subscription_id = sub["id"]
    session.add(subscriber)
    session.commit()

    payment_url = get_subscription_payment_link(sub["id"]) or sub.get("invoiceUrl")
    if not payment_url:
        return RedirectResponse("/pilotqa-ai?subscribe_error=1", status_code=303)
    return RedirectResponse(payment_url, status_code=303)


@router.post("/pilotqa_ai/webhook/asaas")
async def pilotqa_asaas_webhook(request: Request, session: Session = Depends(get_session)):
    token = request.headers.get("asaas-access-token", "")
    if settings.asaas_webhook_token and token != settings.asaas_webhook_token:
        raise HTTPException(status_code=401, detail="Token inválido.")
    data = await request.json()
    event = data.get("event", "")
    if event in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        subscription_id = data.get("payment", {}).get("subscription")
        if subscription_id:
            subscriber = session.exec(
                select(PilotQASubscriber).where(PilotQASubscriber.asaas_subscription_id == subscription_id)
            ).first()
            if subscriber and settings.pilotqa_jwt_private_key:
                jwt_token = generate_pilotqa_token(subscriber.email, subscriber.plan)
                send_pilotqa_token_email(subscriber.name, subscriber.email, subscriber.plan, jwt_token)
                session.add(subscriber)
                session.commit()
    return {"received": True}
