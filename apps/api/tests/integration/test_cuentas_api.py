"""Cuentas reales por HTTP: invitar, activar, entrar, recuperar la clave, roles, demo y panel de la plataforma."""

import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select, text

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.rls import set_rls_context
from app.main import app
from app.models import Persona, User
from app.workers.celery_app import celery_app
from tests.integration.conftest import Mundo

pytestmark = pytest.mark.integration
CLAVE = "Clave-Segura-2026"


class Cliente:
    def __init__(self, http: httpx.AsyncClient, mundo: Mundo, correos: list[list[Any]]) -> None:
        self.http = http
        self.mundo = mundo
        self.correos = correos
        self.base = f"/api/v1/tenants/{mundo.tenant}"

    def auth(self, quien: str | uuid.UUID) -> dict[str, str]:
        user = quien if isinstance(quien, uuid.UUID) else self.mundo.usuarios[quien]
        return {"Authorization": f"Bearer {create_access_token(user)[0]}"}

    async def get(self, quien: str | uuid.UUID, ruta: str) -> httpx.Response:
        return await self.http.get(self.base + ruta, headers=self.auth(quien))

    async def send(self, metodo: str, quien: str | uuid.UUID, ruta: str, body: Any = None) -> httpx.Response:
        return await self.http.request(metodo, self.base + ruta, json=body, headers=self.auth(quien))

    async def publico(self, metodo: str, ruta: str, body: Any = None, token: str | None = None) -> httpx.Response:
        h = {"Authorization": f"Bearer {token}"} if token else {}
        return await self.http.request(metodo, "/api/v1" + ruta, json=body, headers=h)

    def ultimo_token(self) -> str:
        """Token del enlace del último correo encolado (como lo leería la persona en su bandeja)."""
        texto = self.correos[-1][2]
        m = re.search(r"/(?:activar|restablecer)#token=([A-Za-z0-9_-]+)", texto)
        assert m, texto
        return m.group(1)

    async def invitar(self, email: str, rol: str = "AUXILIAR", **extra: Any) -> httpx.Response:
        return await self.send(
            "POST", "ADMIN", "/usuarios", {"email": email, "nombre": "Nueva Persona", "rol": rol, **extra}
        )


@pytest.fixture
async def api(mundo: Mundo, sin_limites: None, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Cliente]:
    correos: list[list[Any]] = []

    def capturar(nombre: str, args: Any = None, **_: Any) -> Any:
        if nombre == "cuentas.correo":
            correos.append(list(args))
        return type("R", (), {"id": "x"})()

    monkeypatch.setattr(celery_app, "send_task", capturar)

    async def _db() -> AsyncIterator[Any]:
        yield mundo.db

    app.dependency_overrides[get_db] = _db
    app.state.redis = Redis.from_url(get_settings().redis_url)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            yield Cliente(http, mundo, correos)
    finally:
        app.dependency_overrides.clear()
        await app.state.redis.aclose()


def _email() -> str:
    return f"{uuid.uuid4().hex[:10]}@ejemplo.co"


async def test_invitar_activar_y_entrar(api: Cliente) -> None:
    email = _email()
    r = await api.invitar(email, "CONTABILIDAD")
    assert r.status_code == 201, r.text
    assert r.json()["nuevo"] is True and r.json()["usuario"]["estado"] == "INVITADO"
    assert api.correos[-1][0] == email and "Active su cuenta de Conjunto de prueba" in api.correos[-1][1]

    # Sin clave todavía: no puede entrar
    assert (await api.publico("POST", "/auth/login", {"email": email, "password": CLAVE})).status_code == 401

    token = api.ultimo_token()
    info = (await api.publico("POST", "/auth/enlace", {"token": token})).json()
    assert info["tipo"] == "INVITACION" and info["copropiedad"] == "Conjunto de prueba" and info["requiere_politica"]

    sin_politica = await api.publico(
        "POST", "/auth/activar", {"token": token, "password": CLAVE, "acepta_politica": False}
    )
    assert sin_politica.status_code == 400
    simple = await api.publico(
        "POST", "/auth/activar", {"token": token, "password": "aaaaaaaaaa", "acepta_politica": True}
    )
    assert simple.status_code == 422

    r = await api.publico("POST", "/auth/activar", {"token": token, "password": CLAVE, "acepta_politica": True})
    assert r.status_code == 200, r.text
    assert [m["role"] for m in r.json()["memberships"]] == ["CONTABILIDAD"]
    # El enlace es de un solo uso
    assert (
        await api.publico("POST", "/auth/activar", {"token": token, "password": CLAVE, "acepta_politica": True})
    ).status_code == 400

    login = await api.publico("POST", "/auth/login", {"email": email, "password": CLAVE})
    assert login.status_code == 200
    usuarios = (await api.get("ADMIN", "/usuarios")).json()
    assert next(u for u in usuarios if u["email"] == email)["estado"] == "ACTIVO"


async def test_cuenta_existente_solo_recibe_aviso_y_no_se_duplica(api: Cliente) -> None:
    email = _email()
    await api.mundo.db.execute(
        text("INSERT INTO users (email, full_name, password_hash) VALUES (:e, 'Con Cuenta', :h)"),
        {"e": email, "h": hash_password(CLAVE)},
    )
    r = await api.invitar(email, "CONSEJO")
    assert r.status_code == 201 and r.json()["nuevo"] is False
    assert "Nuevo acceso: Conjunto de prueba" in api.correos[-1][1]
    assert "token=" not in api.correos[-1][2]  # a una cuenta con clave nunca se le manda enlace
    assert (await api.invitar(email.upper(), "CONSEJO")).status_code == 409


async def test_solo_el_administrador_gestiona_usuarios(api: Cliente) -> None:
    assert (await api.get("AUXILIAR", "/usuarios")).status_code == 403
    r = await api.send("POST", "AUXILIAR", "/usuarios", {"email": _email(), "nombre": "X Y", "rol": "ADMIN"})
    assert r.status_code == 403


async def test_siempre_queda_un_administrador_y_retirar_quita_el_acceso(api: Cliente) -> None:
    admin = str(api.mundo.usuarios["ADMIN"])
    assert (await api.send("PATCH", "ADMIN", f"/usuarios/{admin}", {"rol": "CONSEJO"})).status_code == 409
    assert (await api.send("DELETE", "ADMIN", f"/usuarios/{admin}")).status_code == 409

    aux = str(api.mundo.usuarios["AUXILIAR"])
    r = await api.send("PATCH", "ADMIN", f"/usuarios/{aux}", {"rol": "ADMIN"})
    assert r.status_code == 200 and r.json()["rol_etiqueta"] == "Administrador"
    # Con dos administradores, uno puede dejar de serlo
    assert (await api.send("PATCH", "ADMIN", f"/usuarios/{admin}", {"rol": "CONSEJO"})).status_code == 200

    assert (await api.send("DELETE", "AUXILIAR", f"/usuarios/{admin}")).status_code == 204
    await set_rls_context(api.mundo.db, tenant_id=api.mundo.tenant, role="SYSTEM")
    assert (await api.get("ADMIN", "/unidades")).status_code == 404  # ya no pertenece a la copropiedad


async def test_la_demo_no_permite_invitar(api: Cliente) -> None:
    await api.mundo.db.execute(text("UPDATE tenants SET is_demo = true WHERE id = :t"), {"t": api.mundo.tenant})
    r = await api.invitar(_email())
    assert r.status_code == 403 and "demostración" in r.json()["detail"]
    assert api.correos == []


async def test_dar_acceso_al_portal_a_una_persona_del_censo(api: Cliente) -> None:
    unidad = (await api.send("POST", "ADMIN", "/unidades", {"tower": "1", "number": "301", "coefficient": "1"})).json()
    email = _email()
    v = await api.send(
        "POST",
        "ADMIN",
        f"/unidades/{unidad['id']}/vinculos",
        {"relacion": "PROPIETARIO", "persona": {"nombre_completo": "Rosa Díaz", "email": email}},
    )
    assert v.status_code == 201, v.text
    await set_rls_context(api.mundo.db, tenant_id=api.mundo.tenant, role="SYSTEM")
    persona = (await api.mundo.db.scalars(select(Persona).where(Persona.email == email))).one()

    r = await api.invitar(email, "RESIDENTE", persona_id=str(persona.id))
    assert r.status_code == 201, r.text
    user_id = uuid.UUID(r.json()["usuario"]["user_id"])
    await set_rls_context(api.mundo.db, tenant_id=api.mundo.tenant, role="SYSTEM")
    api.mundo.db.expunge_all()
    unit_id = await api.mundo.db.scalar(
        text("SELECT unit_id FROM memberships WHERE tenant_id = :t AND user_id = :u"),
        {"t": api.mundo.tenant, "u": user_id},
    )
    assert str(unit_id) == unidad["id"]  # verá su unidad en el portal

    # Al retirarle el acceso, la persona del censo queda sin cuenta vinculada
    assert (await api.send("DELETE", "ADMIN", f"/usuarios/{user_id}")).status_code == 204
    await set_rls_context(api.mundo.db, tenant_id=api.mundo.tenant, role="SYSTEM")
    api.mundo.db.expunge_all()
    assert (await api.mundo.db.get(Persona, persona.id)).user_id is None  # type: ignore[union-attr]


async def test_recuperar_y_restablecer_cierra_las_sesiones(api: Cliente) -> None:
    email = _email()
    user_id = (
        await api.mundo.db.execute(
            text("INSERT INTO users (email, full_name, password_hash) VALUES (:e, 'Olvidadiza', :h) RETURNING id"),
            {"e": email, "h": hash_password(CLAVE)},
        )
    ).scalar_one()
    viejo = create_access_token(user_id)[0]

    # Correo desconocido: misma respuesta y ningún correo
    assert (await api.publico("POST", "/auth/recuperar", {"email": _email()})).status_code == 202
    assert api.correos == []
    assert (await api.publico("POST", "/auth/recuperar", {"email": email})).status_code == 202
    assert "Restablecer su contraseña" in api.correos[-1][1]

    await asyncio.sleep(1.1)  # el `iat` de los JWT tiene resolución de segundos
    nueva = "Otra-Clave-Distinta-9"
    r = await api.publico("POST", "/auth/restablecer", {"token": api.ultimo_token(), "password": nueva})
    assert r.status_code == 200, r.text
    assert (await api.publico("GET", "/auth/me", token=viejo)).status_code == 401  # sesión anterior cerrada
    assert (await api.publico("GET", "/auth/me", token=r.json()["access_token"])).status_code == 200
    assert (await api.publico("POST", "/auth/login", {"email": email, "password": CLAVE})).status_code == 401
    assert (await api.publico("POST", "/auth/login", {"email": email, "password": nueva})).status_code == 200


async def test_cambiar_clave(api: Cliente) -> None:
    email = _email()
    user_id = (
        await api.mundo.db.execute(
            text("INSERT INTO users (email, full_name, password_hash) VALUES (:e, 'Juan', :h) RETURNING id"),
            {"e": email, "h": hash_password(CLAVE)},
        )
    ).scalar_one()
    token = create_access_token(user_id)[0]
    mal = await api.publico("POST", "/auth/cambiar-clave", {"actual": "no-es", "nueva": "Nueva-Clave-123"}, token)
    assert mal.status_code == 400
    ok = await api.publico("POST", "/auth/cambiar-clave", {"actual": CLAVE, "nueva": "Nueva-Clave-123"}, token)
    assert ok.status_code == 200 and ok.json()["access_token"]
    assert (
        await api.publico("POST", "/auth/login", {"email": email, "password": "Nueva-Clave-123"})
    ).status_code == 200

    demo = (
        await api.mundo.db.execute(
            text("INSERT INTO users (email, full_name, password_hash) VALUES (:e, 'Demo', :h) RETURNING id"),
            {"e": f"{uuid.uuid4().hex[:8]}@lospinos.demo", "h": hash_password(CLAVE)},
        )
    ).scalar_one()
    r = await api.publico(
        "POST", "/auth/cambiar-clave", {"actual": CLAVE, "nueva": "Nueva-Clave-123"}, create_access_token(demo)[0]
    )
    assert r.status_code == 403


async def test_panel_de_la_plataforma(api: Cliente) -> None:
    # Un administrador de copropiedad no ve el panel (ni sabe que existe)
    assert (
        await api.publico("GET", "/plataforma/copropiedades", token=api.auth("ADMIN")["Authorization"][7:])
    ).status_code == 404

    dueno = (
        await api.mundo.db.execute(
            text(
                "INSERT INTO users (email, full_name, password_hash, is_platform_admin) "
                "VALUES (:e, 'Dueño Plataforma', :h, true) RETURNING id"
            ),
            {"e": _email(), "h": hash_password(CLAVE)},
        )
    ).scalar_one()
    token = create_access_token(dueno)[0]
    me = (await api.publico("GET", "/auth/me", token=token)).json()
    assert me["user"]["is_platform_admin"] is True and me["memberships"] == []

    admin_email = _email()
    r = await api.publico(
        "POST",
        "/plataforma/copropiedades",
        {
            "nombre": "Conjunto Residencial Mirador del Río",
            "nit": f"9{uuid.uuid4().int % 10**8:08d}-1",
            "ciudad": "Bogotá",
            "admin_email": admin_email,
            "admin_nombre": "Patricia Mora",
        },
        token,
    )
    assert r.status_code == 201, r.text
    c = r.json()["copropiedad"]
    assert c["slug"].startswith("mirador-del-rio") and c["is_demo"] is False
    assert c["administradores"] == 1 and c["invitaciones_pendientes"] == 1
    assert api.correos[-1][0] == admin_email and "Mirador del Río" in api.correos[-1][1]
    # El dueño recibe el mismo enlace del correo, para enviarlo él mismo si quiere
    del_correo = api.ultimo_token()
    assert r.json()["enlace_invitacion"].endswith(f"/activar#token={del_correo}")

    # «Enlace»: genera uno nuevo y anula el del correo
    enl = await api.publico("POST", f"/plataforma/copropiedades/{c['id']}/enlaces", token=token)
    assert enl.status_code == 200, enl.text
    assert [(x["email"], x["nombre"]) for x in enl.json()] == [(admin_email, "Patricia Mora")]
    nuevo_token = enl.json()[0]["enlace"].split("token=")[1]
    assert nuevo_token != del_correo
    assert (await api.publico("POST", "/auth/enlace", {"token": del_correo})).status_code == 400
    admin_token = api.auth("ADMIN")["Authorization"][7:]
    assert (
        await api.publico("POST", f"/plataforma/copropiedades/{c['id']}/enlaces", token=admin_token)
    ).status_code == 404

    # Los catálogos base quedaron creados (recaudos, activos, cartera)
    await set_rls_context(api.mundo.db, tenant_id=uuid.UUID(c["id"]), role="SYSTEM")
    for tabla in ("conceptos_recaudo", "categorias_activos", "conceptos_cartera"):
        n = await api.mundo.db.scalar(text(f"SELECT count(*) FROM {tabla} WHERE tenant_id = :t"), {"t": c["id"]})  # noqa: S608
        assert n and n > 0, tabla

    # La administradora activa su cuenta y entra directo a su copropiedad
    r = await api.publico("POST", "/auth/activar", {"token": nuevo_token, "password": CLAVE, "acepta_politica": True})
    assert [(m["tenant_slug"], m["role"]) for m in r.json()["memberships"]] == [(c["slug"], "ADMIN")]
    # Ya activó: no hay enlaces que generar (a una cuenta activa nunca se le genera uno)
    assert (await api.publico("POST", f"/plataforma/copropiedades/{c['id']}/enlaces", token=token)).status_code == 409

    lista = (await api.publico("GET", "/plataforma/copropiedades", token=token)).json()
    assert any(x["id"] == c["id"] and x["invitaciones_pendientes"] == 0 for x in lista)
    p = await api.publico("PATCH", f"/plataforma/copropiedades/{c['id']}", {"is_demo": True}, token)
    assert p.status_code == 200 and p.json()["is_demo"] is True

    # Mismo NIT: rechazado
    dup = await api.publico(
        "POST",
        "/plataforma/copropiedades",
        {"nombre": "Otro", "nit": c["nit"], "admin_email": _email(), "admin_nombre": "X Y"},
        token,
    )
    assert dup.status_code == 409


async def test_usuario_dado_de_baja_no_entra(api: Cliente) -> None:
    email = _email()
    await api.mundo.db.execute(
        text("INSERT INTO users (email, full_name, password_hash, is_active) VALUES (:e, 'Baja', :h, false)"),
        {"e": email, "h": hash_password(CLAVE)},
    )
    assert (await api.publico("POST", "/auth/login", {"email": email, "password": CLAVE})).status_code == 401
    assert (await api.publico("POST", "/auth/recuperar", {"email": email})).status_code == 202
    assert api.correos == []
    assert (await api.invitar(email)).status_code == 409
    assert await api.mundo.db.scalar(select(User.is_active).where(User.email == email)) is False
