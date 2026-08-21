import html as _html

import resend

from config import settings

_CONTACT_TO = "faleconosco@mtjltechnology.com"


def _esc(value: str) -> str:
    """Escapa HTML para evitar HTML/script injection quando o valor é
    interpolado no corpo de e-mails enviados a partir de formulários públicos."""
    return _html.escape(value or "", quote=True)


def send_pilotqa_contact_email(name: str, email: str, message: str) -> None:
    if not settings.resend_api_key:
        return

    resend.api_key = settings.resend_api_key

    name_safe = _esc(name)
    email_safe = _esc(email)
    message_safe = _esc(message)

    resend.Emails.send({
        "from": "MTJL Technology <noreply@mtjltechnology.com>",
        "reply_to": email,
        "to": [_CONTACT_TO],
        "subject": f"PILOTQA-AI - {name}",
        "text": f"Nome: {name}\nE-mail: {email}\n\nMensagem:\n{message}",
        "html": f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#080e1f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#080e1f;padding:40px 16px">
  <tr><td align="center">
    <table width="520" cellpadding="0" cellspacing="0" style="background:#111827;border-radius:12px;padding:40px 32px;color:#e2e8f0;max-width:520px;border:1px solid rgba(6,182,212,.2)">
      <tr><td style="padding-bottom:16px;border-bottom:1px solid rgba(255,255,255,.08)">
        <p style="margin:0 0 4px;font-size:13px;color:#06b6d4;text-transform:uppercase;letter-spacing:.08em;font-weight:700">PilotQA AI · Novo Contato</p>
        <h1 style="margin:0;font-size:20px;font-weight:700;color:#ffffff">PILOTQA-AI — {name_safe}</h1>
      </td></tr>
      <tr><td style="padding-top:24px">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr><td style="padding-bottom:12px">
            <p style="margin:0 0 2px;font-size:11px;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:.08em">Nome</p>
            <p style="margin:0;font-size:15px;color:#e2e8f0">{name_safe}</p>
          </td></tr>
          <tr><td style="padding-bottom:12px">
            <p style="margin:0 0 2px;font-size:11px;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:.08em">E-mail</p>
            <p style="margin:0;font-size:15px"><a href="mailto:{email_safe}" style="color:#06b6d4">{email_safe}</a></p>
          </td></tr>
          <tr><td style="padding-bottom:24px">
            <p style="margin:0 0 8px;font-size:11px;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:.08em">Assunto</p>
            <div style="background:#0d1117;border-radius:8px;padding:16px;font-size:15px;color:#cbd5e1;line-height:1.6;white-space:pre-wrap;border:1px solid rgba(255,255,255,.07)">{message_safe}</div>
          </td></tr>
        </table>
      </td></tr>
      <tr><td style="border-top:1px solid rgba(255,255,255,.08);padding-top:16px">
        <p style="margin:0;font-size:12px;color:#475569">© 2026 MTJL Technology · PilotQA AI</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>""",
    })


def send_pilotqa_token_email(name: str, email: str, plan: str, token: str) -> None:
    if not settings.resend_api_key:
        return

    resend.api_key = settings.resend_api_key
    plan_label = {"pro": "Pro", "enterprise": "Enterprise"}.get(plan.lower(), plan.title())

    resend.Emails.send({
        "from": "PilotQA AI <noreply@mtjltechnology.com>",
        "to": [email],
        "subject": f"Seu token PilotQA AI — Plano {plan_label}",
        "text": f"Olá {name},\n\nSeu pagamento foi confirmado!\n\nSeu token de acesso PilotQA AI:\n\n{token}\n\nConfigure no seu .env_pilotqa:\nPILOTQA_AUTH_TOKEN={token}\n\nDocumentação: https://mtjltechnology.com/pilotqa-ai\n\nMTJL Technology",
        "html": f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#080e1f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#080e1f;padding:40px 16px">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#111827;border-radius:12px;padding:40px 32px;color:#e2e8f0;max-width:560px;border:1px solid rgba(6,182,212,.2)">
      <tr><td style="padding-bottom:20px;border-bottom:1px solid rgba(255,255,255,.08)">
        <p style="margin:0 0 4px;font-size:13px;color:#06b6d4;text-transform:uppercase;letter-spacing:.08em;font-weight:700">PilotQA AI · Plano {plan_label}</p>
        <h1 style="margin:0;font-size:22px;font-weight:800;color:#ffffff">✅ Pagamento confirmado!</h1>
      </td></tr>
      <tr><td style="padding-top:24px">
        <p style="font-size:15px;color:#cbd5e1;margin:0 0 24px">Olá <strong>{name}</strong>, seu acesso ao PilotQA AI está pronto.</p>
        <p style="margin:0 0 8px;font-size:12px;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:.08em">Seu token de acesso</p>
        <div style="background:#0d1117;border-radius:8px;padding:16px;font-family:monospace;font-size:11px;color:#06b6d4;word-break:break-all;border:1px solid rgba(6,182,212,.3);margin-bottom:24px">{token}</div>
        <p style="margin:0 0 8px;font-size:13px;color:#94a3b8">Configure no seu arquivo <code style="color:#06b6d4;font-size:12px">.env_pilotqa</code>:</p>
        <div style="background:#0d1117;border-radius:8px;padding:12px 16px;font-family:monospace;font-size:13px;color:#10b981;border:1px solid rgba(16,185,129,.2);margin-bottom:24px">PILOTQA_AUTH_TOKEN={token}</div>
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px">
          <tr>
            <td style="background:#0d1117;border-radius:8px;padding:14px 16px;border:1px solid rgba(255,255,255,.07)">
              <p style="margin:0 0 4px;font-size:12px;color:#94a3b8">Plano</p>
              <p style="margin:0;font-size:15px;font-weight:700;color:#ffffff">{plan_label}</p>
            </td>
            <td width="16"></td>
            <td style="background:#0d1117;border-radius:8px;padding:14px 16px;border:1px solid rgba(255,255,255,.07)">
              <p style="margin:0 0 4px;font-size:12px;color:#94a3b8">Execuções</p>
              <p style="margin:0;font-size:15px;font-weight:700;color:#ffffff">{"100/dia" if plan.lower() == "pro" else "500/dia"}</p>
            </td>
            <td width="16"></td>
            <td style="background:#0d1117;border-radius:8px;padding:14px 16px;border:1px solid rgba(255,255,255,.07)">
              <p style="margin:0 0 4px;font-size:12px;color:#94a3b8">Validade</p>
              <p style="margin:0;font-size:15px;font-weight:700;color:#ffffff">1 ano</p>
            </td>
          </tr>
        </table>
        <a href="https://mtjltechnology.com/pilotqa-ai" style="display:inline-block;background:#06b6d4;color:#fff;font-weight:700;font-size:14px;padding:12px 24px;border-radius:50px;text-decoration:none">Ver documentação →</a>
      </td></tr>
      <tr><td style="border-top:1px solid rgba(255,255,255,.08);padding-top:16px;margin-top:24px">
        <p style="margin:0;font-size:12px;color:#475569">© 2026 MTJL Technology · PilotQA AI · <a href="https://mtjltechnology.com" style="color:#475569">mtjltechnology.com</a></p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>""",
    })


def send_contact_email(name: str, email: str, message: str) -> None:
    if not settings.resend_api_key:
        print("[email] resend_api_key não configurada — send_contact_email ignorado")
        return

    resend.api_key = settings.resend_api_key

    name_safe = _esc(name)
    email_safe = _esc(email)
    message_safe = _esc(message)

    try:
        resend.Emails.send({
            "from": "MTJL Technology <noreply@mtjltechnology.com>",
            "reply_to": email,
            "to": [_CONTACT_TO],
            "subject": f"Contato via site — {name}",
            "text": f"Nome: {name}\nE-mail: {email}\n\nMensagem:\n{message}",
            "html": f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:40px 16px">
  <tr><td align="center">
    <table width="520" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;padding:40px 32px;color:#111827;max-width:520px">
      <tr><td style="padding-bottom:16px;border-bottom:1px solid #f3f4f6">
        <p style="margin:0 0 4px;font-size:13px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;font-weight:600">MTJL Technology</p>
        <h1 style="margin:0;font-size:20px;font-weight:700">Novo contato via site</h1>
      </td></tr>
      <tr><td style="padding-top:24px">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr><td style="padding-bottom:12px">
            <p style="margin:0 0 2px;font-size:12px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Nome</p>
            <p style="margin:0;font-size:15px;color:#111827">{name_safe}</p>
          </td></tr>
          <tr><td style="padding-bottom:12px">
            <p style="margin:0 0 2px;font-size:12px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.05em">E-mail</p>
            <p style="margin:0;font-size:15px;color:#111827"><a href="mailto:{email_safe}" style="color:#0b55b7">{email_safe}</a></p>
          </td></tr>
          <tr><td style="padding-bottom:24px">
            <p style="margin:0 0 8px;font-size:12px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Assunto</p>
            <div style="background:#f9fafb;border-radius:8px;padding:16px;font-size:15px;color:#374151;line-height:1.6;white-space:pre-wrap">{message_safe}</div>
          </td></tr>
        </table>
      </td></tr>
      <tr><td style="border-top:1px solid #f3f4f6;padding-top:16px">
        <p style="margin:0;font-size:12px;color:#9ca3af">© 2026 MTJL Technology · <a href="https://mtjltechnology.com" style="color:#9ca3af">mtjltechnology.com</a></p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>""",
        })
    except Exception as exc:
        print(f"[email] Erro ao enviar send_contact_email para {email}: {exc}")
