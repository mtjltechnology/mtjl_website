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
        "/booking_beauty/subscribe",
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
        "/booking_beauty_contact",
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
    ("/booking_beauty_contact", {"name": "Rate Bot", "email": "ratebot-bbc@empresa-legitima.com", "message": "oi"}),
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

    statuses = [client.post("/booking_beauty/subscribe", data=payload, follow_redirects=False).status_code for _ in range(5)]
    assert all(s != 429 for s in statuses), f"requisição dentro do limite retornou 429: {statuses}"

    sixth = client.post("/booking_beauty/subscribe", data=payload, follow_redirects=False)
    assert sixth.status_code == 429


# ── Blocklist de e-mail ────────────────────────────────────────────────────────

CONTACT_BLOCKLIST_ENDPOINTS = [
    ("/contact", {"name": "Bot", "email": "x@test.com", "message": "spam"}, "sent=1"),
    ("/booking_beauty_contact", {"name": "Bot", "email": "x@test.com", "message": "spam"}, "bb_sent=1"),
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
        "/booking_beauty_contact",
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
        "/booking_beauty_contact",
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
