"""Alertas de mantenimiento: qué avisar hoy y a quién (docs/MANTENIMIENTO.md §2.4).

La tarea diaria (como SYSTEM) calcula los avisos, registra cada uno en
notificaciones_mantenimiento (clave única tipo + registro + fecha: nunca se
envía dos veces) y manda UN correo por destinatario con todo agrupado.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.services.comun import pesos

# Sección del correo de cada tipo de aviso, en orden de lectura
SECCIONES = {
    "novedad_critica": "Novedades críticas",
    "novedad_sin_atender": "Novedades sin atender",
    "actividad_vencida": "Mantenimientos vencidos",
    "resumen_vencidas": "Mantenimientos vencidos",
    "actividad_proxima": "Mantenimientos próximos",
    "recomendacion_vencida": "Recomendaciones de prioridad alta vencidas",
    "garantia": "Garantías por vencer",
    "contrato": "Contratos de contratistas por vencer",
}
ADMINISTRACION = frozenset({UserRole.ADMIN, UserRole.AUXILIAR})
DIAS_AVISO_ACTIVIDAD = (15, 7, 1)
DIAS_AVISO_CONTRATO = (60, 30)
DIAS_AVISO_GARANTIA = 30


@dataclass
class Aviso:
    tipo: str
    entidad_id: uuid.UUID
    mensaje: str
    fecha_aviso: date
    roles: frozenset[UserRole] = ADMINISTRACION
    usuarios: set[uuid.UUID] = field(default_factory=set)  # además de los roles (técnico asignado, responsable)


def _dias(n: int) -> str:
    return "hoy" if n == 0 else "mañana" if n == 1 else f"en {n} días"


async def calcular(db: AsyncSession, hoy: date) -> list[Aviso]:
    """Avisos del día para la copropiedad del contexto RLS de la sesión."""
    avisos: list[Aviso] = []

    actividades = await db.execute(
        text(
            "SELECT s.id, s.dias_restantes, s.asignado_a_id, a.codigo_interno, a.nombre, p.nombre"
            "  FROM v_semaforo_actividades s JOIN activos a ON a.id = s.activo_id JOIN planes_preventivos p ON p.id = s.plan_id"
            " WHERE s.dias_restantes = ANY(:dias) OR s.dias_restantes < 0"
        ),
        {"dias": [*DIAS_AVISO_ACTIVIDAD, -1]},
    )
    vencidas_viejas = 0
    for act_id, dias, asignado, codigo, nombre, plan in actividades:
        usuarios = {asignado} if asignado else set()
        if dias in DIAS_AVISO_ACTIVIDAD:
            avisos.append(
                Aviso(
                    "actividad_proxima",
                    act_id,
                    f"{codigo} {nombre}: «{plan}» vence {_dias(dias)}",
                    hoy,
                    usuarios=usuarios,
                )
            )
        elif dias == -1:
            avisos.append(
                Aviso(
                    "actividad_vencida",
                    act_id,
                    f"{codigo} {nombre}: «{plan}» venció ayer sin ejecutarse",
                    hoy,
                    usuarios=usuarios,
                )
            )
        else:
            vencidas_viejas += 1
    if vencidas_viejas and hoy.weekday() == 0:  # resumen semanal, los lunes
        tenant = await db.scalar(text("SELECT app_tenant_id()"))
        avisos.append(
            Aviso(
                "resumen_vencidas",
                tenant,
                f"Hay {vencidas_viejas} mantenimientos vencidos hace más de un día sin ejecutar",
                hoy,
            )
        )

    for nov_id, codigo, nombre, prioridad, descripcion, reportada in await db.execute(
        text(
            "SELECT n.id, n.codigo, a.nombre, n.prioridad::text, n.descripcion, (n.fecha_reporte AT TIME ZONE 'America/Bogota')::date"
            "  FROM novedades n JOIN activos a ON a.id = n.activo_id"
            " WHERE n.estado = 'REPORTADA' AND n.fecha_atencion IS NULL"
            "   AND ((n.prioridad = 'CRITICA' AND n.fecha_reporte < now() - interval '24 hours')"
            "     OR (n.prioridad = 'ALTA' AND n.fecha_reporte < now() - interval '72 hours'))"
        )
    ):
        horas = "24 h" if prioridad == "CRITICA" else "72 h"
        avisos.append(
            Aviso(
                "novedad_sin_atender",
                nov_id,
                f"{codigo} ({prioridad.lower()}) en {nombre}, sin atender en más de {horas}: {descripcion[:120]}",
                reportada,
            )
        )

    for rec_id, nombre, descripcion, responsable in await db.execute(
        text(
            "SELECT r.id, a.nombre, r.descripcion, r.responsable_id FROM recomendaciones_tecnicas r JOIN activos a ON a.id = r.activo_id"
            " WHERE r.prioridad = 'ALTA' AND r.estado IN ('PENDIENTE', 'EN_PROCESO') AND r.fecha_limite = :ayer"
        ),
        {"ayer": hoy - timedelta(days=1)},
    ):
        avisos.append(
            Aviso(
                "recomendacion_vencida",
                rec_id,
                f"{nombre}: {descripcion[:140]}",
                hoy,
                usuarios={responsable} if responsable else set(),
            )
        )

    for activo_id, codigo, nombre, garantia in await db.execute(
        text(
            "SELECT id, codigo_interno, nombre, fecha_vencimiento_garantia FROM activos"
            " WHERE estado <> 'DADO_DE_BAJA' AND fecha_vencimiento_garantia = :fecha"
        ),
        {"fecha": hoy + timedelta(days=DIAS_AVISO_GARANTIA)},
    ):
        avisos.append(Aviso("garantia", activo_id, f"{codigo} {nombre}: la garantía vence el {garantia:%d/%m/%Y}", hoy))

    for cid, razon, fin, valor in await db.execute(
        text(
            "SELECT id, razon_social, vigencia_contrato_fin, valor_contrato FROM contratistas"
            " WHERE activo AND vigencia_contrato_fin = ANY(:fechas)"
        ),
        {"fechas": [hoy + timedelta(days=d) for d in DIAS_AVISO_CONTRATO]},
    ):
        valor_txt = f" (valor anual {pesos(valor)})" if valor else ""
        avisos.append(
            Aviso(
                "contrato",
                cid,
                f"{razon}: el contrato vence el {fin:%d/%m/%Y}{valor_txt}",
                hoy,
                roles=frozenset({UserRole.ADMIN, UserRole.CONTABILIDAD}),
            )
        )
    return avisos


async def registrar_nuevos(db: AsyncSession, tenant_id: uuid.UUID, avisos: list[Aviso]) -> list[Aviso]:
    """Deja solo los avisos que no se habían enviado (clave única en notificaciones_mantenimiento)."""
    nuevos = []
    for a in avisos:
        fila = await db.execute(
            insert(_TABLA)
            .values(
                id=uuid.uuid4(), tenant_id=tenant_id, tipo=a.tipo, entidad_id=a.entidad_id, fecha_aviso=a.fecha_aviso
            )
            .on_conflict_do_nothing(index_elements=["tipo", "entidad_id", "fecha_aviso"])
            .returning(_TABLA.c.id)
        )
        if fila.first() is not None:
            nuevos.append(a)
    return nuevos


def agrupar_por_destinatario(
    avisos: list[Aviso], personal: list[tuple[uuid.UUID, str, UserRole]]
) -> dict[str, list[tuple[str, str]]]:
    """{correo: [(sección, mensaje)]} — un solo correo por persona con todos sus avisos."""
    por_correo: dict[str, list[tuple[str, str]]] = {}
    for a in avisos:
        for user_id, correo, rol in personal:
            if rol in a.roles or user_id in a.usuarios:
                por_correo.setdefault(correo, []).append((SECCIONES[a.tipo], a.mensaje))
    return por_correo


def _tabla():  # type: ignore[no-untyped-def]
    from sqlalchemy import Column, Date, MetaData, Table, Text
    from sqlalchemy.dialects.postgresql import UUID

    return Table(
        "notificaciones_mantenimiento",
        MetaData(),
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("tenant_id", UUID(as_uuid=True)),
        Column("tipo", Text),
        Column("entidad_id", UUID(as_uuid=True)),
        Column("fecha_aviso", Date),
    )


_TABLA = _tabla()
