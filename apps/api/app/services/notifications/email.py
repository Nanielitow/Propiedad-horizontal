"""Envío de correo por SMTP (sin dependencias extra).

En desarrollo, docker compose levanta Mailpit: atrapa todos los correos y los
muestra en http://localhost:8025, sin enviar nada a internet. En producción se
apunta SMTP_* a un proveedor transaccional (SES, Postmark, Brevo...).
"""

import logging
import smtplib
from email.message import EmailMessage
from html import escape

from app.core.config import get_settings

log = logging.getLogger(__name__)


def email_enabled() -> bool:
    return bool(get_settings().smtp_host)


def send_email(to: list[str], subject: str, text: str, html: str) -> None:
    """Lanza excepción si falla: quien llama decide si reintenta."""
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
    log.info("correo enviado a %s: %s", to, subject)


def deadline_reminder(
    *, tenant_name: str, title: str, due: str, days_left: int, provider: str | None, document: str, url: str
) -> tuple[str, str, str]:
    """Devuelve (asunto, texto, html) de un recordatorio de vencimiento."""
    when = "hoy" if days_left == 0 else "mañana" if days_left == 1 else f"en {days_left} días"
    subject = f"Vence {when}: {title} · {tenant_name}"
    lines = [
        f"Recordatorio de {tenant_name}",
        "",
        f"{title}",
        f"Fecha: {due} (vence {when})",
        *([f"Proveedor: {provider}"] if provider else []),
        f"Documento de origen: {document}",
        "",
        f"Ver en PH Gestión: {url}",
    ]
    rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#5b6573">{escape(k)}</td><td style="padding:4px 0">{escape(v)}</td></tr>'
        for k, v in [
            ("Fecha", f"{due} (vence {when})"),
            *([("Proveedor", provider)] if provider else []),
            ("Documento", document),
        ]
    )
    html = f"""<div style="font-family:Arial,sans-serif;color:#1b2430;max-width:560px">
  <p style="color:#5b6573;margin:0 0 4px">Recordatorio · {escape(tenant_name)}</p>
  <h2 style="margin:0 0 16px;color:#1f3a5f">{escape(title)}</h2>
  <table style="font-size:14px;border-collapse:collapse">{rows}</table>
  <p style="margin:24px 0"><a href="{escape(url)}" style="background:#1f3a5f;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none">Ver vencimientos</a></p>
  <p style="font-size:12px;color:#8a929e">Recibe este correo porque es administrador de {escape(tenant_name)} en PH Gestión.</p>
</div>"""
    return subject, "\n".join(lines), html
