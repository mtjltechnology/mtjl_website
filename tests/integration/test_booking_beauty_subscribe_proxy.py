"""
Integration tests for the /booking_beauty/subscribe → booking internal API
proxy. O site institucional não cria Establishment diretamente (isso mudou
na separação site/produto) — ele só repassa o form pro endpoint interno do
MTJL_BookingAI_Beauty e traduz a resposta JSON de volta pro mesmo redirect
que a UI já esperava.
"""
import httpx
import pytest


def _payload(**overrides):
    payload = {
        "name": "Salão Legítimo",
        "email": "dono@empresa-legitima.com.br",
        "plan": "bb_starter",
        "phone": "41999998888",
        "accept_terms": "on",
    }
    payload.update(overrides)
    return payload


def _mock_backend_response(mocker, json_body, status_code=200):
    response = httpx.Response(status_code, json=json_body, request=httpx.Request("POST", "http://test"))
    return mocker.patch("httpx.AsyncClient.post", return_value=response)


def test_backend_ok_redireciona_para_bb_subscribed(client, mocker):
    mock_post = _mock_backend_response(mocker, {"ok": True})

    r = client.post("/booking_beauty/subscribe", data=_payload(), follow_redirects=False)

    assert r.status_code == 303
    assert "bb_subscribed=1" in r.headers["location"]
    mock_post.assert_called_once()


@pytest.mark.parametrize("error_code", ["email", "phone", "terms", "invalid_email", "security", "invalid_plan"])
def test_backend_erro_redireciona_com_bb_error(client, mocker, error_code):
    _mock_backend_response(mocker, {"ok": False, "error": error_code})

    r = client.post("/booking_beauty/subscribe", data=_payload(), follow_redirects=False)

    assert r.status_code == 303
    assert f"bb_error={error_code}" in r.headers["location"]


def test_backend_indisponivel_redireciona_com_bb_error_unavailable(client, mocker):
    mocker.patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("connection refused"))

    r = client.post("/booking_beauty/subscribe", data=_payload(), follow_redirects=False)

    assert r.status_code == 303
    assert "bb_error=unavailable" in r.headers["location"]


def test_payload_repassado_ao_backend_inclui_master_key_e_dados_do_form(client, mocker):
    mock_post = _mock_backend_response(mocker, {"ok": True})

    client.post(
        "/booking_beauty/subscribe",
        data=_payload(name="Ana", email="ana@empresa.com", phone="41988887777"),
        follow_redirects=False,
        headers={"user-agent": "pytest-agent"},
    )

    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["X-Master-Key"]
    body = kwargs["json"]
    assert body["name"] == "Ana"
    assert body["email"] == "ana@empresa.com"
    assert body["phone"] == "41988887777"
    assert body["accept_terms"] is True
    assert body["terms_user_agent"] == "pytest-agent"


def test_prefixo_de_idioma_preservado_no_redirect(client, mocker):
    _mock_backend_response(mocker, {"ok": True})

    r = client.post("/booking_beauty/subscribe", data=_payload(lang="en"), follow_redirects=False)

    assert r.headers["location"].startswith("/en/booking_beauty")
