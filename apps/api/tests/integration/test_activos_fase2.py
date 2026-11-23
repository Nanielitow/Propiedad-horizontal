"""Fase 2 del módulo de activos: QR y etiquetas, evidencias, vencimientos vinculados,
alertas diarias y reestimación por horómetro."""

import uuid
from datetime import timedelta
from typing import Any

import pymupdf
import pytest
from sqlalchemy import select, text

from app.db.rls import set_rls_context
from app.models import ActividadProgramada
from app.models.enums import EntidadEvidencia, MomentoEvidencia, Periodicidad, UserRole
from app.schemas.activos import EvidenciaIn, PlanIn, VinculoDocumentoIn
from app.services.activos import activos, alertas, evidencias, planes, qr
from app.services.comun import TZ, NoEncontrado, ValidacionError
from app.services.notifications.email import maintenance_alerts
from tests.integration.conftest import AHORA, Mundo
from tests.integration.test_activos import m, nuevo_activo  # noqa: F401  (fixture y ayudante compartidos)

pytestmark = pytest.mark.integration
HOY = AHORA.astimezone(TZ).date()


async def como_sistema(mundo: Mundo) -> None:
    await set_rls_context(mundo.db, tenant_id=mundo.tenant, role="SYSTEM")


# --- QR y etiquetas -------------------------------------------------------------------


async def test_qr_y_hoja_de_etiquetas(m: Mundo) -> None:  # noqa: F811
    lista = [await nuevo_activo(m, f"Equipo {i}") for i in range(12)]
    url = qr.url_qr("los-pinos", lista[0].qr_token)
    assert url.endswith(f"/los-pinos/activos/qr/{lista[0].qr_token}")
    assert qr.svg(url).startswith("<svg")

    doc = pymupdf.open("pdf", qr.etiquetas_pdf(lista, "los-pinos", "Conjunto de prueba"))
    assert doc.page_count == 2  # 10 etiquetas por hoja
    texto = doc[0].get_text()
    assert "ACT-001" in texto and "Escanee con la cámara del celular" in texto
    assert len(doc[0].get_images()) == 10


# --- Evidencias ------------------------------------------------------------------------


class AlmacenFalso:
    def __init__(self) -> None:
        self.objetos: dict[str, int] = {}

    def activo_evidencia_key(self, tenant_id: Any, extension: str) -> str:
        return f"tenants/{tenant_id}/activos/evidencias/{uuid.uuid4()}.{extension}"

    def presign_put(self, key: str, content_type: str) -> str:
        return f"https://almacen.test/put/{key}"

    def presign_get(self, key: str, filename: str, content_type: str = "") -> str:
        return f"https://almacen.test/get/{key}"

    def object_size(self, key: str) -> int | None:
        return self.objetos.get(key)

    def delete(self, key: str) -> None:
        self.objetos.pop(key, None)


async def test_evidencias_solo_de_la_propia_copropiedad(m: Mundo, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    almacen = AlmacenFalso()
    monkeypatch.setattr(evidencias, "get_storage", lambda: almacen)
    a = await nuevo_activo(m)
    tecnico = await m.como(UserRole.MANTENIMIENTO)
    with pytest.raises(ValidacionError, match="foto"):
        evidencias.url_subida(tecnico, "text/html", 100)
    subida = evidencias.url_subida(tecnico, "image/jpeg", 200_000)
    assert subida.storage_key.startswith(f"tenants/{m.tenant}/activos/evidencias/")

    datos = {"entidad": EntidadEvidencia.ACTIVO, "entidad_id": a.id, "momento": MomentoEvidencia.FOTO_ACTIVO}
    with pytest.raises(ValidacionError, match="aún no se ha subido"):
        await evidencias.registrar(m.db, tecnico, EvidenciaIn(**datos, storage_key=subida.storage_key))
    almacen.objetos[subida.storage_key] = 200_000
    ajena = f"tenants/{uuid.uuid4()}/activos/evidencias/{uuid.uuid4()}.jpg"
    with pytest.raises(ValidacionError, match="no es válido"):
        await evidencias.registrar(m.db, tecnico, EvidenciaIn(**datos, storage_key=ajena))
    with pytest.raises(NoEncontrado):
        await evidencias.registrar(
            m.db, tecnico, EvidenciaIn(**(datos | {"entidad_id": uuid.uuid4()}), storage_key=subida.storage_key)
        )

    ev = await evidencias.registrar(m.db, tecnico, EvidenciaIn(**datos, storage_key=subida.storage_key))
    assert (ev.content_type, ev.size_bytes) == ("image/jpeg", 200_000)
    [(registrada, url)] = await evidencias.listar(m.db, tecnico, EntidadEvidencia.ACTIVO, a.id)
    assert registrada.id == ev.id and url.startswith("https://almacen.test/get/")


# --- Vencimientos de los documentos vinculados -----------------------------------------


async def test_vencimientos_de_documentos_vinculados(m: Mundo) -> None:  # noqa: F811
    a = await nuevo_activo(m)
    await como_sistema(m)
    doc = uuid.uuid4()
    await m.db.execute(
        text(
            "INSERT INTO documents (id, tenant_id, title, original_filename, category, access_level, status, storage_key, size_bytes, sha256)"
            " VALUES (:id, :t, 'Contrato ascensores', 'c.pdf', 'CONTRATOS', 'ADMIN', 'READY', 'k', 10, :sha)"
        ),
        {"id": doc, "t": m.tenant, "sha": uuid.uuid4().hex * 2},
    )
    await m.db.execute(
        text(
            "INSERT INTO deadlines (tenant_id, document_id, title, type, status, due_date)"
            " VALUES (:t, :d, 'Fin del contrato de mantenimiento', 'CONTRACT_END', 'ACTIVE', :f)"
        ),
        {"t": m.tenant, "d": doc, "f": HOY + timedelta(days=90)},
    )
    admin = await m.como(UserRole.ADMIN)
    await activos.vincular_documento(m.db, admin, a.id, VinculoDocumentoIn(document_id=doc, tipo="CONTRATO"))
    [v] = await activos.vencimientos(m.db, admin, a.id)
    assert v.title == "Fin del contrato de mantenimiento"
    tecnico = await m.como(UserRole.MANTENIMIENTO)
    assert await activos.vencimientos(m.db, tecnico, a.id) == []  # vencimientos: solo la administración (RLS)


# --- Alertas diarias ---------------------------------------------------------------------


async def test_alertas_del_dia_sin_duplicados_y_por_destinatario(m: Mundo) -> None:  # noqa: F811
    a = await nuevo_activo(m)
    admin = await m.como(UserRole.ADMIN)
    plan = await planes.crear_plan(
        m.db,
        admin,
        PlanIn(
            activo_id=a.id, nombre="Revisión", periodicidad=Periodicidad.ANUAL, fecha_inicio=HOY + timedelta(days=400)
        ),
    )
    await planes.aprobar_plan(
        m.db, admin, plan.id, hoy=HOY
    )  # su primera fecha queda fuera del horizonte: sin actividades
    await m.usuario("TECNICO2", "MANTENIMIENTO")
    await como_sistema(m)
    for dias, asignado in ((15, None), (7, m.usuarios["MANTENIMIENTO"]), (1, None), (-1, None), (30, None)):
        f = HOY + timedelta(days=dias)
        await m.db.execute(
            text(
                "INSERT INTO actividades_programadas (tenant_id, plan_id, activo_id, fecha_programada, fecha_original, asignado_a_id)"
                " VALUES (:t, :p, :a, :f, :f, :u)"
            ),
            {"t": m.tenant, "p": plan.id, "a": a.id, "f": f, "u": asignado},
        )
    await m.db.execute(
        text("UPDATE activos SET fecha_vencimiento_garantia = :f WHERE id = :id"),
        {"f": HOY + timedelta(days=30), "id": a.id},
    )
    await m.db.execute(
        text(
            "INSERT INTO contratistas (tenant_id, razon_social, vigencia_contrato_fin, valor_contrato) VALUES (:t, 'Ascensores Andinos', :f, 12000000)"
        ),
        {"t": m.tenant, "f": HOY + timedelta(days=60)},
    )
    await m.db.execute(
        text(
            "INSERT INTO novedades (tenant_id, activo_id, reportado_por_id, descripcion, prioridad, fecha_reporte)"
            " VALUES (:t, :a, :u, 'Ascensor detenido con personas', 'CRITICA', now() - interval '30 hours')"
        ),
        {"t": m.tenant, "a": a.id, "u": m.usuarios["ADMIN"]},
    )
    await m.db.execute(
        text(
            "INSERT INTO recomendaciones_tecnicas (tenant_id, activo_id, descripcion, prioridad, fecha_limite) VALUES (:t, :a, 'Cambiar guayas', 'ALTA', :f)"
        ),
        {"t": m.tenant, "a": a.id, "f": HOY - timedelta(days=1)},
    )

    avisos = await alertas.calcular(m.db, HOY)
    tipos = sorted(x.tipo for x in avisos)
    assert tipos.count("actividad_proxima") == 3  # 15, 7 y 1 días (la de 30 días no avisa)
    assert {"actividad_vencida", "garantia", "contrato", "novedad_sin_atender", "recomendacion_vencida"} <= set(tipos)

    nuevos = await alertas.registrar_nuevos(m.db, m.tenant, avisos)
    assert len(nuevos) == len(avisos)
    assert await alertas.registrar_nuevos(m.db, m.tenant, await alertas.calcular(m.db, HOY)) == []  # nunca dos veces

    personal = [
        (m.usuarios["ADMIN"], "admin@x", UserRole.ADMIN),
        (m.usuarios["CONTABILIDAD"], "conta@x", UserRole.CONTABILIDAD),
        (m.usuarios["MANTENIMIENTO"], "tecnico@x", UserRole.MANTENIMIENTO),
        (m.usuarios["TECNICO2"], "tecnico2@x", UserRole.MANTENIMIENTO),
    ]
    por_correo = alertas.agrupar_por_destinatario(nuevos, personal)
    assert len(por_correo["admin@x"]) == len(nuevos)  # la administración recibe todos los avisos
    assert [s for s, _ in por_correo["conta@x"]] == ["Contratos de contratistas por vencer"]
    assert len(por_correo["tecnico@x"]) == 1 and "vence en 7 días" in por_correo["tecnico@x"][0][1]  # solo lo suyo
    assert "tecnico2@x" not in por_correo


def test_correo_de_mantenimiento_agrupa_por_seccion() -> None:
    asunto, texto, html = maintenance_alerts(
        tenant_name="Los Pinos",
        items=[
            ("Novedades críticas", "NOV-0001 ascensor detenido"),
            ("Mantenimientos próximos", "ACT-001 vence mañana"),
        ],
        url="https://app.test/los-pinos/activos",
    )
    assert asunto.startswith("⚠ Mantenimiento: 2 avisos")
    assert texto.index("Novedades críticas") < texto.index("Mantenimientos próximos")
    assert "NOV-0001 ascensor detenido" in html


# --- Horómetro ------------------------------------------------------------------------------


async def test_reestimacion_por_horas_de_uso(m: Mundo) -> None:  # noqa: F811
    a = await nuevo_activo(m, "Planta eléctrica")
    admin = await m.como(UserRole.ADMIN)
    plan = await planes.crear_plan(
        m.db,
        admin,
        PlanIn(
            activo_id=a.id,
            nombre="Cambio de aceite",
            periodicidad=Periodicidad.POR_HORAS_USO,
            intervalo_horas=100,
            fecha_inicio=HOY,
        ),
    )
    await planes.aprobar_plan(m.db, admin, plan.id, hoy=HOY)
    await como_sistema(m)
    for dias, horas in ((20, 0), (10, 30), (0, 60)):  # 60 h en 20 días: 3 h diarias
        await m.db.execute(
            text("INSERT INTO lecturas_uso (tenant_id, activo_id, fecha, horas_acumuladas) VALUES (:t, :a, :f, :h)"),
            {"t": m.tenant, "a": a.id, "f": AHORA - timedelta(days=dias), "h": horas},
        )
    assert await planes.reestimar_por_horas(m.db, HOY) == 1
    act = (await m.db.scalars(select(ActividadProgramada).where(ActividadProgramada.plan_id == plan.id))).one()
    assert act.fecha_programada == HOY + timedelta(days=14)  # quedan 40 h a 3 h/día
    motivo = await m.db.scalar(text("SELECT motivo FROM reprogramaciones WHERE actividad_id = :id"), {"id": act.id})
    assert motivo == "Reestimada por horómetro: quedan 40.0 h de 100 h"
    assert await planes.reestimar_por_horas(m.db, HOY) == 0  # ya está bien estimada


async def test_reestimacion_cuenta_desde_el_ultimo_mantenimiento(m: Mundo) -> None:  # noqa: F811
    from app.services.activos import mantenimientos
    from tests.integration.test_activos import preventivo

    a = await nuevo_activo(m, "Motobomba de presión")
    admin = await m.como(UserRole.ADMIN)
    plan = await planes.crear_plan(
        m.db,
        admin,
        PlanIn(
            activo_id=a.id,
            nombre="Cambio de sellos",
            periodicidad=Periodicidad.POR_HORAS_USO,
            intervalo_horas=100,
            fecha_inicio=HOY,
        ),
    )
    await planes.aprobar_plan(m.db, admin, plan.id, hoy=HOY)
    await como_sistema(m)
    for dias, horas in ((20, 0), (10, 30), (0, 60)):
        await m.db.execute(
            text("INSERT INTO lecturas_uso (tenant_id, activo_id, fecha, horas_acumuladas) VALUES (:t, :a, :f, :h)"),
            {"t": m.tenant, "a": a.id, "f": AHORA - timedelta(days=dias), "h": horas},
        )
    [primera] = (await m.db.scalars(select(ActividadProgramada).where(ActividadProgramada.plan_id == plan.id))).all()
    admin = await m.como(UserRole.ADMIN)
    # Mantenimiento hace 10 días, cuando el horómetro marcaba 30 h: la base pasa a ser 30 h
    await mantenimientos.registrar(m.db, admin, preventivo(a, primera.id, fecha_ejecucion=HOY - timedelta(days=10)))
    await como_sistema(m)
    assert await planes.reestimar_por_horas(m.db, HOY) == 1
    siguiente = (
        await m.db.scalars(
            select(ActividadProgramada).where(
                ActividadProgramada.plan_id == plan.id, ActividadProgramada.estado == "PROGRAMADA"
            )
        )
    ).one()
    assert siguiente.fecha_programada == HOY + timedelta(days=24)  # 100 - (60 - 30) = 70 h a 3 h/día
