"""
Unit tests for services/asaas.py — mock mode (APP_ENV != production).

Incidente: o QA identificou que este módulo chamava a API real do Asaas via
httpx.Client().post(...) sem nenhum guard de ambiente dev/test, diferente do
resto do projeto. Estes testes garantem que o guard existe e funciona: fora
de produção, nenhuma chamada de rede real é feita e um stub previsível é
retornado.
"""
from services.asaas import (
    create_customer,
    create_subscription,
    get_subscription_payment_link,
    update_customer,
)


# ── create_customer ────────────────────────────────────────────────────────────

def test_create_customer_retorna_id_mock():
    result = create_customer("Ana Souza", "ana@email.com")
    assert result["id"] == "cus_mock_0000001"


def test_create_customer_preserva_nome_e_email():
    result = create_customer("João", "joao@email.com")
    assert result["name"] == "João"
    assert result["email"] == "joao@email.com"


def test_create_customer_nao_chama_api_externa(mocker):
    spy = mocker.patch("services.asaas.httpx.Client")
    create_customer("X", "x@x.com")
    spy.assert_not_called()


# ── update_customer ────────────────────────────────────────────────────────────

def test_update_customer_nao_chama_api_externa(mocker):
    spy = mocker.patch("services.asaas.httpx.Client")
    update_customer("cus_123", "12345678901")
    spy.assert_not_called()


# ── create_subscription ────────────────────────────────────────────────────────

def test_create_subscription_retorna_id_mock():
    result = create_subscription("cus_mock_0000001", 197.0, "PilotQA AI — Plano Pro")
    assert result["id"] == "sub_mock_0000001"
    assert result["status"] == "ACTIVE"


def test_create_subscription_preserva_valor():
    result = create_subscription("cus_abc", 697.0, "PilotQA AI — Plano Enterprise")
    assert result["value"] == 697.0


def test_create_subscription_nao_chama_api_externa(mocker):
    spy = mocker.patch("services.asaas.httpx.Client")
    create_subscription("cus_abc", 197.0, "desc")
    spy.assert_not_called()


# ── get_subscription_payment_link ─────────────────────────────────────────────

def test_get_subscription_payment_link_retorna_url_mock():
    url = get_subscription_payment_link("sub_mock_0000001")
    assert url is not None
    assert url.startswith("http")


def test_get_subscription_payment_link_nao_chama_api_externa(mocker):
    spy = mocker.patch("services.asaas.httpx.Client")
    get_subscription_payment_link("sub_mock_0000001")
    spy.assert_not_called()


# ── modo produção continua chamando a API real ────────────────────────────────

def test_create_customer_em_producao_chama_api_externa(monkeypatch, mocker):
    from config import settings
    monkeypatch.setattr(settings, "app_env", "production")

    mock_response = mocker.Mock()
    mock_response.is_success = True
    mock_response.json.return_value = {"id": "cus_real_123", "name": "X", "email": "x@x.com"}
    mock_post = mocker.patch("services.asaas.httpx.Client.post", return_value=mock_response)

    result = create_customer("X", "x@x.com")

    mock_post.assert_called_once()
    assert result["id"] == "cus_real_123"
