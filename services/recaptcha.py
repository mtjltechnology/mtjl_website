"""Verificação de reCAPTCHA v3 nos formulários de contato do site.

O v3 não desafia o visitante: ele devolve um score de 0.0 (certamente bot) a
1.0 (certamente humano), e cabe ao servidor decidir o corte. Aqui o corte é
`settings.recaptcha_min_score`.

Duas situações deixam a submissão passar de propósito, porque derrubar um lead
real custa mais do que deixar um spam entrar:

- Chave secreta não configurada. Nada é consultado e nada é bloqueado.
- Google inacessível ou lento. A indisponibilidade é deles, não do visitante.

Um token ausente ou reprovado, porém, bloqueia: é exatamente o caso do bot que
posta direto no endpoint sem executar o JavaScript da página.
"""
import httpx

from config import settings

_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
_TIMEOUT = 5


def is_human(token: str, remote_ip: str | None = None) -> bool:
    if not settings.recaptcha_secret_key:
        return True
    if not token:
        return False

    payload = {"secret": settings.recaptcha_secret_key, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        result = httpx.post(_VERIFY_URL, data=payload, timeout=_TIMEOUT).json()
    except Exception:
        return True

    if not result.get("success"):
        return False
    # `score` só existe no v3. Um par de chaves v2 responde sem ele, e aí o
    # próprio `success` já é a resposta.
    return float(result.get("score", 1.0)) >= settings.recaptcha_min_score
