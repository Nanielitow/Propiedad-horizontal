"""Datos de demostración (idempotente): python -m app.scripts.seed

Dos copropiedades para poder demostrar el aislamiento multi-tenant:
- Conjunto Residencial Los Pinos: un admin y un residente
- Edificio Torre Central: un admin
"""

import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.db.rls import set_rls_context_sync
from app.db.session import SyncSessionLocal
from app.models import Membership, Tenant, User
from app.models.enums import UserRole

DEMO_PASSWORD = "Demo1234!"

TENANTS = [
    {"slug": "los-pinos", "name": "Conjunto Residencial Los Pinos", "city": "Bogotá", "nit": "900123456-1"},
    {"slug": "torre-central", "name": "Edificio Torre Central", "city": "Medellín", "nit": "900654321-2"},
]
USERS = [
    ("admin@lospinos.demo", "Laura Gómez (Administradora)", "los-pinos", UserRole.ADMIN),
    ("residente@lospinos.demo", "Carlos Pérez (Apto 502)", "los-pinos", UserRole.RESIDENTE),
    ("admin@torrecentral.demo", "Andrés Ruiz (Administrador)", "torre-central", UserRole.ADMIN),
]


def main() -> None:
    with SyncSessionLocal() as db:
        # tenants y users son tablas globales (sin RLS por tenant)
        tenants: dict[str, Tenant] = {}
        for data in TENANTS:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == data["slug"]))
            if tenant is None:
                tenant = Tenant(id=uuid.uuid4(), **data)
                db.add(tenant)
            tenants[data["slug"]] = tenant
        db.commit()

        password_hash = hash_password(DEMO_PASSWORD)
        for email, name, slug, role in USERS:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(id=uuid.uuid4(), email=email, full_name=name, password_hash=password_hash)
                db.add(user)
                db.commit()
            # memberships SÍ tiene RLS: hay que fijar el tenant antes de insertar
            set_rls_context_sync(db, tenant_id=tenants[slug].id, role="SYSTEM")
            exists = db.scalar(
                select(Membership.id).where(Membership.tenant_id == tenants[slug].id, Membership.user_id == user.id)
            )
            if exists is None:
                db.add(Membership(id=uuid.uuid4(), tenant_id=tenants[slug].id, user_id=user.id, role=role))
            db.commit()

    print("Datos de demo listos. Contraseña para todos:", DEMO_PASSWORD)
    for email, _, slug, role in USERS:
        print(f"  {role.value:<10} {email:<28} -> {slug}")


if __name__ == "__main__":
    main()
