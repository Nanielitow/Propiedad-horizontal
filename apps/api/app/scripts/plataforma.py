"""Dueño de la plataforma (se ejecuta una vez por persona):

    python -m app.scripts.plataforma dueno --email correo@dominio.com --nombre "Nombre Apellido"

Crea la cuenta si no existe (sin clave), la marca como dueña de la plataforma y le ENVÍA POR CORREO el enlace para
definir la contraseña. El enlace nunca se imprime: quien ejecuta el script no puede usarlo. Si la cuenta ya tiene
clave, solo se le da el permiso.

    python -m app.scripts.plataforma quitar --email correo@dominio.com    # retira el permiso
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import User
from app.services.cuentas import enlaces
from app.services.notifications.email import email_enabled, send_email


async def dueno(email: str, nombre: str) -> None:
    if not email_enabled():
        sys.exit("SMTP_HOST no está configurado: sin correo no hay cómo entregar el enlace de activación.")
    async with SessionLocal() as db:  # users y account_tokens no tienen RLS
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=nombre, password_hash=None)
            db.add(user)
            await db.flush()
        user.is_platform_admin = True
        user.is_active = True
        correo = None
        if user.password_hash is None:
            url = await enlaces.emitir(db, user, enlaces.INVITACION)
            correo = enlaces.correo_invitacion(user, url, None, None)
        await db.commit()
    if correo:
        send_email([correo.destino], correo.asunto, correo.texto, correo.html, demo=False)
        print("✓ Cuenta de dueño creada. El enlace para definir la contraseña se envió a ese correo (vence en 7 días).")
    else:
        print("✓ La cuenta ya tenía contraseña: ahora es dueña de la plataforma.")


async def quitar(email: str) -> None:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            sys.exit("No existe una cuenta con ese correo.")
        user.is_platform_admin = False
        await db.commit()
    print("✓ Permiso de dueño retirado.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dueno")
    d.add_argument("--email", required=True)
    d.add_argument("--nombre", required=True)
    q = sub.add_parser("quitar")
    q.add_argument("--email", required=True)
    a = p.parse_args()
    email = a.email.strip().lower()
    if "@" not in email or enlaces.es_cuenta_demo(email):
        sys.exit("Correo inválido.")
    asyncio.run(dueno(email, a.nombre.strip()) if a.cmd == "dueno" else quitar(email))


if __name__ == "__main__":
    main()
