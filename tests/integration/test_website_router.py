"""
Integration tests for router.py — anti-spam protections on the public
contact/subscribe endpoints (`/contact`, `/booking_beauty_contact`,
`/qualityassurance_contact`, `/pilotqa_contact`, `/pilotqa_ai/subscribe`,
and the honeypot/rate-limit layer of `/booking_beauty/subscribe`).

`/booking_beauty/subscribe` agora só faz honeypot localmente e repassa o
resto (bloqueio de e-mail, reCAPTCHA, duplicidade) pro endpoint interno do
produto (MTJL_BookingAI_Beauty) — ver test_booking_beauty_subscribe_proxy.py
pra cobertura desse repasse.
"""
import pytest


def _bb_subscribe_payload(**overrides):
    payload = {
        "name": "Salão Legítimo",
        "email": "dono@empresa-legitima.com.br",
        "plan": "bb_starter",
        "accept_terms": "on",
    }
    payload.update(overrides)
    return payload


# ── Honeypot ──────────────────────────────────────────────────────────────────

def test_subscribe_honeypot_preenchido_nao_chama_backend(client, mocker):
    mock_post = mocker.patch("httpx.AsyncClient.post")

    r = client.post(
        "/relatify_beauty/subscribe",
        data=_bb_subscribe_payload(
            email="bot@spam-domain-qualquer.com",
            website="http://spam-bot.example.com",  # honeypot preenchido
        ),
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert "bb_subscribed=1" in r.headers["location"]
    mock_post.assert_not_called()


def test_booking_beauty_contact_honeypot_preenchido_nao_envia_email(client, mocker):
    mock_send = mocker.patch("resend.Emails.send")

    r = client.post(
        "/relatify_beauty_contact",
        data={
            "name": "Bot",
            "email": "bot@spam-domain-qualquer.com",
            "message": "spam",
            "website": "http://spam-bot.example.com",  # honeypot preenchido
        },
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert "bb_sent=1" in r.headers["location"]
    mock_send.assert_not_called()


# ── Rate limit (5/minute) ─────────────────────────────────────────────────────

RATE_LIMITED_ENDPOINTS = [
    ("/contact", {"name": "Rate Bot", "email": "ratebot-contact@empresa-legitima.com", "message": "oi"}),
    ("/relatify_beauty_contact", {"name": "Rate Bot", "email": "ratebot-bbc@empresa-legitima.com", "message": "oi"}),
    ("/qualityassurance_contact", {"name": "Rate Bot", "email": "ratebot-qa@empresa-legitima.com", "message": "oi"}),
    ("/pilotqa_contact", {"name": "Rate Bot", "email": "ratebot-pq@empresa-legitima.com", "message": "oi"}),
    ("/pilotqa_ai/subscribe", {"name": "Rate Bot", "email": "ratebot-pqs@empresa-legitima.com", "plan": "pro"}),
]


@pytest.mark.parametrize("path,payload", RATE_LIMITED_ENDPOINTS)
def test_rate_limit_5_por_minuto_bloqueia_a_sexta_requisicao(client, path, payload, mocker):
    mocker.patch("resend.Emails.send")
    # /pilotqa_ai/subscribe usa services/asaas.py, que só chama a API real do
    # Asaas quando settings.app_env == "production" (guard em nível de serviço).
    # Em teste (app_env=development) ele já retorna stubs mockados automaticamente.
    statuses = [client.post(path, data=payload, follow_redirects=False).status_code for _ in range(5)]
    assert all(s != 429 for s in statuses), f"{path}: requisição dentro do limite retornou 429: {statuses}"

    sixth = client.post(path, data=payload, follow_redirects=False)
    assert sixth.status_code == 429, f"{path}: 6ª requisição no mesmo minuto deveria retornar 429"


def test_rate_limit_booking_beauty_subscribe_bloqueia_a_sexta_requisicao(client, mocker):
    mocker.patch("httpx.AsyncClient.post", side_effect=Exception("sem backend no teste"))
    payload = {"name": "Rate Bot", "email": "ratebot-bb@empresa-legitima.com", "plan": "bb_starter", "accept_terms": "on"}

    statuses = [client.post("/relatify_beauty/subscribe", data=payload, follow_redirects=False).status_code for _ in range(5)]
    assert all(s != 429 for s in statuses), f"requisição dentro do limite retornou 429: {statuses}"

    sixth = client.post("/relatify_beauty/subscribe", data=payload, follow_redirects=False)
    assert sixth.status_code == 429


# ── Blocklist de e-mail ────────────────────────────────────────────────────────

CONTACT_BLOCKLIST_ENDPOINTS = [
    ("/contact", {"name": "Bot", "email": "x@test.com", "message": "spam"}, "sent=1"),
    ("/relatify_beauty_contact", {"name": "Bot", "email": "x@test.com", "message": "spam"}, "bb_sent=1"),
    ("/qualityassurance_contact", {"name": "Bot", "email": "x@test.com", "message": "spam"}, "sent=1"),
    ("/pilotqa_contact", {"name": "Bot", "email": "x@test.com", "message": "spam"}, "pq_sent=1"),
]


@pytest.mark.parametrize("path,payload,expected_marker", CONTACT_BLOCKLIST_ENDPOINTS)
def test_contact_endpoints_email_bloqueado_retorna_sucesso_fake_sem_enviar(client, path, payload, expected_marker, mocker):
    mock_send = mocker.patch("resend.Emails.send")

    r = client.post(path, data=payload, follow_redirects=False)

    assert r.status_code == 303
    assert expected_marker in r.headers["location"]
    mock_send.assert_not_called()


def test_pilotqa_subscribe_email_bloqueado_retorna_400(client):
    r = client.post(
        "/pilotqa_ai/subscribe",
        data={"name": "Bot", "email": "x@test.com", "plan": "pro"},
        follow_redirects=False,
    )
    assert r.status_code == 400


# ── HTML injection (name/email/message escapados no corpo do e-mail) ──────────

def test_contact_html_injection_e_escapado_no_corpo_do_email(client, monkeypatch, mocker):
    from config import settings
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    mock_send = mocker.patch("resend.Emails.send")

    r = client.post(
        "/contact",
        data={"name": "<b>Nome</b>", "email": "injection@empresa-legitima.com", "message": "<script>alert('xss')</script>"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    mock_send.assert_called_once()
    html_body = mock_send.call_args_list[0].args[0]["html"]
    assert "&lt;script&gt;alert" in html_body
    assert "<script>alert" not in html_body
    assert "<b>Nome</b>" not in html_body


def test_booking_beauty_contact_html_injection_e_escapado_no_corpo_do_email(client, monkeypatch, mocker):
    from config import settings
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    mock_send = mocker.patch("resend.Emails.send")

    r = client.post(
        "/relatify_beauty_contact",
        data={
            "name": "<b>Nome</b>",
            "email": "injection2@empresa-legitima.com",
            "message": "<script>alert('xss')</script>",
        },
        follow_redirects=False,
    )

    assert r.status_code == 303
    mock_send.assert_called_once()
    html_body = mock_send.call_args_list[0].args[0]["html"]
    assert "&lt;script&gt;alert" in html_body
    assert "<script>alert" not in html_body
    assert "<b>Nome</b>" not in html_body


# ── Fluxo legítimo continua funcionando ────────────────────────────────────────

def test_booking_beauty_contact_fluxo_legitimo_envia_email(client, monkeypatch, mocker):
    from config import settings
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    mock_send = mocker.patch("resend.Emails.send")

    r = client.post(
        "/relatify_beauty_contact",
        data={
            "name": "Cliente Real",
            "email": "cliente@empresa-legitima.com",
            "whatsapp": "41999990000",
            "message": "Quero saber mais",
        },
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert "bb_sent=1" in r.headers["location"]
    mock_send.assert_called_once()


# ── Descarte de submissão de bot ──────────────────────────────────────────────
# O site vinha recebendo dezenas de envios/dia de bot de link building. O corpo
# real de um deles: assunto `<a href=https://t.me/...>ко ланта</a> ко ланта`.

SPAM_SUBMISSIONS = [
    ("honeypot preenchido", {"name": "Bot", "email": "bot@empresa-legitima.com", "message": "oi", "website": "http://x.com"}),
    ("anchor html", {"name": "Jamesdig", "email": "xrumer23Nit@gmail.com", "message": "<a href=https://t.me/x>ко ланта</a>"}),
    ("bbcode", {"name": "Bot", "email": "bot@empresa-legitima.com", "message": "[url=https://x.com]clique[/url]"}),
    ("cirilico", {"name": "Bot", "email": "bot@empresa-legitima.com", "message": "ко ланта"}),
    ("varios links", {"name": "Bot", "email": "bot@empresa-legitima.com", "message": "veja https://a.com e https://b.com"}),
    ("link no nome", {"name": "https://a.com https://b.com", "email": "bot@empresa-legitima.com", "message": "oi"}),
]


@pytest.mark.parametrize("path,marker", [
    ("/contact", "sent=1"),
    ("/qualityassurance_contact", "sent=1"),
    ("/pilotqa_contact", "pq_sent=1"),
    ("/relatify_beauty_contact", "bb_sent=1"),
    ("/pedemarket_contact", "sent=1"),
    ("/desenvolvimento_contact", "sent=1"),
    ("/inteligencia_artificial_contact", "sent=1"),
    ("/larclinica_contact", "sent=1"),
])
@pytest.mark.parametrize("payload", [p for _, p in SPAM_SUBMISSIONS], ids=[c for c, _ in SPAM_SUBMISSIONS])
def test_submissao_de_bot_retorna_sucesso_fake_sem_enviar(client, path, marker, payload, mocker):
    mock_send = mocker.patch("resend.Emails.send")

    r = client.post(path, data=payload, follow_redirects=False)

    assert r.status_code == 303
    assert marker in r.headers["location"]
    mock_send.assert_not_called()


@pytest.mark.parametrize("message", [
    "Olá, quero um orçamento para automação de testes.",
    "Somos a Acme, veja https://acme.com.br, precisamos de um piloto.",
])
def test_lead_legitimo_continua_passando(client, monkeypatch, message, mocker):
    from config import settings
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    mock_send = mocker.patch("resend.Emails.send")

    r = client.post(
        "/contact",
        data={"name": "Maria Silva", "email": "maria@empresa-legitima.com", "message": message},
        follow_redirects=False,
    )

    assert r.status_code == 303
    mock_send.assert_called_once()


# ── reCAPTCHA v3 ──────────────────────────────────────────────────────────────
# Fecha o caso que honeypot e filtro de texto não pegam: bot que posta direto no
# endpoint com texto limpo, sem executar o JavaScript da página.

@pytest.fixture(name="recaptcha_on")
def recaptcha_on_fixture(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "recaptcha_secret_key", "secret-de-teste")
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")


LEAD = {"name": "Maria Silva", "email": "maria@empresa-legitima.com", "message": "Quero um orçamento."}


def test_sem_token_nao_envia(client, recaptcha_on, mocker):
    mock_send = mocker.patch("resend.Emails.send")
    mock_verify = mocker.patch("services.recaptcha.httpx.post")

    r = client.post("/contact", data=LEAD, follow_redirects=False)

    assert r.status_code == 303
    assert "sent=1" in r.headers["location"]
    mock_send.assert_not_called()
    # token vazio é reprovado localmente: nem chega a consultar o Google
    mock_verify.assert_not_called()


@pytest.mark.parametrize("verify_response,deve_enviar", [
    ({"success": True, "score": 0.9}, True),
    ({"success": True, "score": 0.5}, True),
    ({"success": True, "score": 0.1}, False),
    ({"success": False, "error-codes": ["invalid-input-response"]}, False),
    ({"success": True}, True),  # par de chaves v2: responde sem score
])
def test_score_do_google_decide(client, recaptcha_on, mocker, verify_response, deve_enviar):
    mock_send = mocker.patch("resend.Emails.send")
    mocker.patch("services.recaptcha.httpx.post").return_value.json.return_value = verify_response

    r = client.post("/contact", data={**LEAD, "recaptcha_token": "tok"}, follow_redirects=False)

    assert r.status_code == 303
    assert mock_send.call_count == (1 if deve_enviar else 0)


def test_google_indisponivel_nao_derruba_o_formulario(client, recaptcha_on, mocker):
    mock_send = mocker.patch("resend.Emails.send")
    mocker.patch("services.recaptcha.httpx.post", side_effect=Exception("timeout"))

    r = client.post("/contact", data={**LEAD, "recaptcha_token": "tok"}, follow_redirects=False)

    assert r.status_code == 303
    mock_send.assert_called_once()


def test_secret_ausente_nao_verifica_nada(client, monkeypatch, mocker):
    from config import settings
    monkeypatch.setattr(settings, "recaptcha_secret_key", "")
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    mock_send = mocker.patch("resend.Emails.send")
    mock_verify = mocker.patch("services.recaptcha.httpx.post")

    r = client.post("/contact", data=LEAD, follow_redirects=False)

    assert r.status_code == 303
    mock_send.assert_called_once()
    mock_verify.assert_not_called()


def test_honeypot_evita_ida_ao_google(client, recaptcha_on, mocker):
    """Os filtros locais rodam antes: submissão de bot não gasta chamada de rede."""
    mock_verify = mocker.patch("services.recaptcha.httpx.post")

    r = client.post("/contact", data={**LEAD, "website": "http://x.com", "recaptcha_token": "tok"}, follow_redirects=False)

    assert r.status_code == 303
    mock_verify.assert_not_called()


@pytest.mark.parametrize("path,marker", [
    ("/contact", "sent=1"),
    ("/qualityassurance_contact", "sent=1"),
    ("/pilotqa_contact", "pq_sent=1"),
    ("/relatify_beauty_contact", "bb_sent=1"),
    ("/pedemarket_contact", "sent=1"),
    ("/desenvolvimento_contact", "sent=1"),
    ("/inteligencia_artificial_contact", "sent=1"),
    ("/larclinica_contact", "sent=1"),
])
def test_todos_os_formularios_exigem_token(client, recaptcha_on, mocker, path, marker):
    mock_send = mocker.patch("resend.Emails.send")

    r = client.post(path, data=LEAD, follow_redirects=False)

    assert r.status_code == 303
    assert marker in r.headers["location"]
    mock_send.assert_not_called()


def test_todos_os_templates_de_contato_mandam_o_token(client):
    """Se um form perder o hidden input, o reCAPTCHA passa a barrar lead real."""
    import pathlib
    import re

    faltando = []
    for f in sorted(pathlib.Path("templates").glob("*.html")):
        src = f.read_text()
        for form in re.findall(r"<form[^>]*data-recaptcha[^>]*>.*?</form>", src, re.S):
            if 'name="recaptcha_token"' not in form:
                faltando.append(f.name)
    assert not faltando, f"form com data-recaptcha e sem hidden input: {faltando}"
