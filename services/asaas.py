import logging

import httpx

from config import settings

ASAAS_BASE_URL = "https://api.asaas.com/v3"

PLANS = {
    "pro": {"value": 197.00, "description": "PilotQA AI — Plano Pro"},
    "enterprise": {"value": 697.00, "description": "PilotQA AI — Plano Enterprise"},
}

_log = logging.getLogger("mock.asaas")


def _headers() -> dict:
    return {"access_token": settings.asaas_api_key, "Content-Type": "application/json"}


def create_customer(name: str, email: str, cpf_cnpj: str = "") -> dict:
    if settings.app_env != "production":
        _log.info("[MOCK] create_customer | name=%s email=%s", name, email)
        return {"id": "cus_mock_0000001", "name": name, "email": email}
    payload = {"name": name, "email": email}
    if cpf_cnpj:
        payload["cpfCnpj"] = cpf_cnpj
    with httpx.Client() as client:
        response = client.post(
            f"{ASAAS_BASE_URL}/customers",
            headers=_headers(),
            json=payload,
        )
        if not response.is_success:
            raise ValueError(f"Asaas error {response.status_code}: {response.text}")
        return response.json()


def update_customer(customer_id: str, cpf_cnpj: str) -> None:
    if settings.app_env != "production":
        _log.info("[MOCK] update_customer | customer_id=%s", customer_id)
        return
    with httpx.Client() as client:
        client.put(
            f"{ASAAS_BASE_URL}/customers/{customer_id}",
            headers=_headers(),
            json={"cpfCnpj": cpf_cnpj},
        )


def create_subscription(customer_id: str, value: float, description: str) -> dict:
    if settings.app_env != "production":
        _log.info("[MOCK] create_subscription | customer_id=%s value=%s", customer_id, value)
        return {
            "id": "sub_mock_0000001",
            "customer": customer_id,
            "value": value,
            "status": "ACTIVE",
            "billingType": "UNDEFINED",
            "nextDueDate": "2099-01-01",
            "invoiceUrl": "http://localhost:8000/mock-invoice",
        }
    from datetime import date
    next_due = date.today().isoformat()
    with httpx.Client() as client:
        response = client.post(
            f"{ASAAS_BASE_URL}/subscriptions",
            headers=_headers(),
            json={
                "customer": customer_id,
                "billingType": "UNDEFINED",
                "value": value,
                "nextDueDate": next_due,
                "cycle": "MONTHLY",
                "description": description,
            },
        )
        if not response.is_success:
            raise ValueError(f"Asaas error {response.status_code}: {response.text}")
        return response.json()


def get_subscription_payment_link(subscription_id: str) -> str | None:
    if settings.app_env != "production":
        _log.info("[MOCK] get_subscription_payment_link | subscription_id=%s", subscription_id)
        return "http://localhost:8000/mock-invoice"
    with httpx.Client() as client:
        response = client.get(
            f"{ASAAS_BASE_URL}/subscriptions/{subscription_id}/payments",
            headers=_headers(),
        )
        if not response.is_success:
            return None
        payments = response.json().get("data", [])
        if payments:
            return payments[0].get("invoiceUrl")
    return None
