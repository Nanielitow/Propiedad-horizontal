"""Motor de reportes del módulo de recaudos.

Cada informe se arma UNA vez como un `Reporte` neutro (resumen + tablas) y de
ahí se dibuja en pantalla (JSON), en Excel y en PDF (app/services/recaudos/
exportar.py): los tres formatos muestran siempre las mismas cifras.

Las consultas corren con el contexto RLS de quien pide el informe: un auxiliar
que pide el arqueo de caja solo ve su propio efectivo.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    AlertaRecaudo,
    AuditoriaRecaudo,
    CierreCaja,
    ConceptoRecaudo,
    Consignacion,
    ConsignacionRecaudo,
    EntregaInterna,
    Recaudo,
    RecaudoItem,
    RecaudoParqueadero,
    Reserva,
    Tenant,
    User,
    ZonaSocial,
)
from app.models.enums import EstadoConsignacion, EstadoRecaudo, MedioPago, UserRole
from app.services.recaudos.dominio import TZ, Actor, R, ValidacionError, exigir, pesos

E = EstadoRecaudo
TipoColumna = Literal["texto", "dinero", "entero", "fecha", "fechahora", "porcentaje"]
TipoReporte = Literal["general", "parqueadero", "zonas", "aseo", "caja", "auditoria"]

PERMISOS: dict[str, frozenset[UserRole]] = {
    "general": frozenset({R.ADMIN, R.CONTABILIDAD}),
    "parqueadero": frozenset({R.ADMIN, R.CONTABILIDAD}),
    "zonas": frozenset({R.ADMIN, R.CONTABILIDAD}),
    "aseo": frozenset({R.ADMIN, R.CONTABILIDAD}),
    "caja": frozenset({R.ADMIN, R.CONTABILIDAD, R.AUXILIAR}),  # el auxiliar, solo su caja (RLS)
    "auditoria": frozenset({R.ADMIN, R.CONTABILIDAD}),
}
TITULOS: dict[str, str] = {
    "general": "Informe general de ingresos",
    "parqueadero": "Informe de parqueadero de visitantes",
    "zonas": "Informe de alquiler de zonas sociales",
    "aseo": "Informe de aseo de áreas sociales",
    "caja": "Informe de caja (arqueo)",
    "auditoria": "Informe de trazabilidad y auditoría",
    "corte": "Corte mensual consolidado",
}
ESTADO_TXT = {
    E.RECAUDADO_EN_CAJA: "En caja",
    E.ENTREGADO_ADMINISTRACION: "En administración",
    E.PENDIENTE_VERIFICACION: "Por verificar",
    E.CONSIGNADO: "Consignado",
    E.VERIFICADO: "Verificado",
    E.ANULADO: "Anulado",
}
MEDIO_TXT = {
    MedioPago.EFECTIVO: "Efectivo",
    MedioPago.TRANSFERENCIA: "Transferencia",
    MedioPago.CONSIGNACION: "Consignación",
}
MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
LIMITE_FILAS = 5000


@dataclass
class Columna:
    titulo: str
    tipo: TipoColumna = "texto"


@dataclass
class Tabla:
    titulo: str
    columnas: list[Columna]
    filas: list[list[Any]]
    totales: list[Any] | None = None
    nota: str | None = None


@dataclass
class Reporte:
    tipo: str
    titulo: str
    copropiedad: str
    desde: date
    hasta: date
    generado: datetime
    resumen: list[tuple[str, str]] = field(default_factory=list)
    tablas: list[Tabla] = field(default_factory=list)

    @property
    def periodo(self) -> str:
        if self.desde.day == 1 and self.hasta == _fin_de_mes(self.desde):
            return f"{MESES[self.desde.month - 1].capitalize()} de {self.desde.year}"
        return f"{_fecha(self.desde)} al {_fecha(self.hasta)}"

    @property
    def nombre_archivo(self) -> str:
        return f"{self.tipo}-{self.desde.isoformat()}-a-{self.hasta.isoformat()}"


def _fecha(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _fin_de_mes(d: date) -> date:
    return (date(d.year + (d.month == 12), d.month % 12 + 1, 1)) - timedelta(days=1)


def _inicio(d: date) -> datetime:
    return datetime.combine(d, time.min, TZ)


def _nombre(n: str | None) -> str:
    return (n or "").split(" (")[0]


def mes_actual() -> tuple[date, date]:
    hoy = datetime.now(TZ).date()
    return hoy.replace(day=1), _fin_de_mes(hoy)


def _validar_rango(desde: date, hasta: date) -> None:
    if hasta < desde:
        raise ValidacionError("La fecha final es anterior a la inicial")
    if (hasta - desde).days > 400:
        raise ValidacionError("El periodo máximo de un informe es de un año")


async def _copropiedad(db: AsyncSession, tenant_id: uuid.UUID) -> str:
    return await db.scalar(select(Tenant.name).where(Tenant.id == tenant_id)) or ""


def _en_rango(desde: date, hasta: date) -> list[Any]:
    return [Recaudo.fecha_recaudo >= _inicio(desde), Recaudo.fecha_recaudo < _inicio(hasta + timedelta(days=1))]


# --- 1. Informe general --------------------------------------------------------------


async def _general(db: AsyncSession, desde: date, hasta: date) -> tuple[list[tuple[str, str]], list[Tabla]]:
    recaudos = list(await db.scalars(select(Recaudo).where(*_en_rango(desde, hasta))))
    activos = [r for r in recaudos if r.estado != E.ANULADO]
    anulados = [r for r in recaudos if r.estado == E.ANULADO]
    total = sum((r.valor_recibido for r in activos), Decimal(0))
    pendiente = sum(
        (
            r.valor_recibido
            for r in activos
            if r.estado in (E.RECAUDADO_EN_CAJA, E.ENTREGADO_ADMINISTRACION, E.PENDIENTE_VERIFICACION)
        ),
        Decimal(0),
    )

    por_concepto = list(
        await db.execute(
            select(ConceptoRecaudo.nombre, func.count(), func.sum(RecaudoItem.valor))
            .join(RecaudoItem, RecaudoItem.concepto_id == ConceptoRecaudo.id)
            .join(Recaudo, Recaudo.id == RecaudoItem.recaudo_id)
            .where(*_en_rango(desde, hasta), Recaudo.estado != E.ANULADO)
            .group_by(ConceptoRecaudo.nombre)
            .order_by(func.sum(RecaudoItem.valor).desc())
        )
    )
    medios: dict[MedioPago, list[Decimal]] = defaultdict(list)
    estados: dict[EstadoRecaudo, list[Decimal]] = defaultdict(list)
    for r in recaudos:
        estados[r.estado].append(r.valor_recibido)
        if r.estado != E.ANULADO:
            medios[r.medio_pago].append(r.valor_recibido)

    def pct(v: Decimal) -> Decimal:
        return (v / total * 100).quantize(Decimal("0.1")) if total else Decimal(0)

    resumen = [
        ("Total recaudado", pesos(total)),
        ("Movimientos", f"{len(activos):,}".replace(",", ".")),
        ("Pendiente por consignar o verificar", pesos(pendiente)),
        ("Consignado o verificado", pesos(total - pendiente)),
        ("Anulados (no suman)", f"{len(anulados)} por {pesos(sum((r.valor_recibido for r in anulados), Decimal(0)))}"),
    ]
    tablas = [
        Tabla(
            "Por concepto",
            [
                Columna("Concepto"),
                Columna("Rubros", "entero"),
                Columna("Total", "dinero"),
                Columna("Participación", "porcentaje"),
            ],
            [[n, c, v, pct(v)] for n, c, v in por_concepto],
            ["Total", sum(c for _, c, _ in por_concepto), total, Decimal(100) if total else Decimal(0)],
            "Los alquileres cuentan su alquiler y su aseo como rubros separados.",
        ),
        Tabla(
            "Por medio de pago",
            [
                Columna("Medio de pago"),
                Columna("Movimientos", "entero"),
                Columna("Total", "dinero"),
                Columna("Participación", "porcentaje"),
            ],
            [[MEDIO_TXT[m], len(v), sum(v, Decimal(0)), pct(sum(v, Decimal(0)))] for m, v in medios.items()],
            ["Total", len(activos), total, Decimal(100) if total else Decimal(0)],
        ),
        Tabla(
            "Por estado del dinero",
            [Columna("Estado"), Columna("Movimientos", "entero"), Columna("Total", "dinero")],
            [[ESTADO_TXT[e], len(estados[e]), sum(estados[e], Decimal(0))] for e in E if estados[e]],
        ),
    ]
    return resumen, tablas


# --- 2. Informes por concepto --------------------------------------------------------


async def _parqueadero(db: AsyncSession, desde: date, hasta: date) -> tuple[list[tuple[str, str]], list[Tabla]]:
    rows = list(
        await db.execute(
            select(Recaudo, RecaudoParqueadero)
            .join(RecaudoParqueadero, RecaudoParqueadero.recaudo_id == Recaudo.id)
            .where(*_en_rango(desde, hasta))
            .order_by(Recaudo.fecha_recaudo)
            .limit(LIMITE_FILAS)
        )
    )
    activos = [(r, p) for r, p in rows if r.estado != E.ANULADO]
    total = sum((r.valor_recibido for r, _ in activos), Decimal(0))
    minutos = [p.minutos_totales for _, p in activos]
    distintos_al_sugerido = sum(1 for r, p in activos if r.valor_recibido != p.tarifa_sugerida)
    resumen = [
        ("Vehículos", str(len(activos))),
        ("Total recaudado", pesos(total)),
        ("Permanencia promedio", f"{round(sum(minutos) / len(minutos)) if minutos else 0} min"),
        ("Placas distintas", str(len({p.placa_vehiculo for _, p in activos}))),
        ("Cobros distintos a la tarifa sugerida", str(distintos_al_sugerido)),
    ]
    tabla = Tabla(
        "Detalle de parqueadero",
        [
            Columna("N.°", "entero"),
            Columna("Placa"),
            Columna("Ingreso", "fechahora"),
            Columna("Salida", "fechahora"),
            Columna("Minutos", "entero"),
            Columna("Sugerido", "dinero"),
            Columna("Cobrado", "dinero"),
            Columna("Medio"),
            Columna("Estado"),
        ],
        [
            [
                r.consecutivo,
                p.placa_vehiculo,
                p.hora_ingreso,
                p.hora_salida,
                p.minutos_totales,
                p.tarifa_sugerida,
                r.valor_recibido,
                MEDIO_TXT[r.medio_pago],
                ESTADO_TXT[r.estado],
            ]
            for r, p in rows
        ],
        ["Total (sin anulados)", None, None, None, sum(minutos), None, total, None, None],
    )
    return resumen, [tabla]


async def _zonas(db: AsyncSession, desde: date, hasta: date) -> tuple[list[tuple[str, str]], list[Tabla]]:
    rows = list(
        await db.execute(
            select(Recaudo, Reserva, ZonaSocial.nombre)
            .join(Reserva, Reserva.id == Recaudo.reserva_id)
            .join(ZonaSocial, ZonaSocial.id == Reserva.zona_id)
            .where(*_en_rango(desde, hasta))
            .order_by(Recaudo.fecha_recaudo)
            .limit(LIMITE_FILAS)
        )
    )
    ids = [r.id for r, _, _ in rows]
    rubros: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    if ids:
        for rid, codigo, valor in await db.execute(
            select(RecaudoItem.recaudo_id, ConceptoRecaudo.codigo, RecaudoItem.valor)
            .join(ConceptoRecaudo, ConceptoRecaudo.id == RecaudoItem.concepto_id)
            .where(RecaudoItem.recaudo_id.in_(ids))
        ):
            rubros[rid]["aseo" if codigo == "ASEO" else "alquiler"] += valor
    activos = [(r, z) for r, _, z in rows if r.estado != E.ANULADO]
    tot_alq = sum((rubros[r.id]["alquiler"] for r, _ in activos), Decimal(0))
    tot_aseo = sum((rubros[r.id]["aseo"] for r, _ in activos), Decimal(0))
    por_zona: dict[str, Decimal] = defaultdict(Decimal)
    for r, z in activos:
        por_zona[z] += r.valor_recibido
    resumen = [
        ("Alquileres", str(len(activos))),
        ("Total alquiler", pesos(tot_alq)),
        ("Total aseo", pesos(tot_aseo)),
        ("Total recaudado", pesos(tot_alq + tot_aseo)),
    ]
    return resumen, [
        Tabla(
            "Detalle de alquileres",
            [
                Columna("N.°", "entero"),
                Columna("Pago", "fecha"),
                Columna("Zona"),
                Columna("Evento", "fecha"),
                Columna("Solicitante"),
                Columna("Alquiler", "dinero"),
                Columna("Aseo", "dinero"),
                Columna("Total", "dinero"),
                Columna("Estado"),
            ],
            [
                [
                    r.consecutivo,
                    r.fecha_recaudo,
                    z,
                    res.fecha_evento,
                    res.solicitante,
                    rubros[r.id]["alquiler"],
                    rubros[r.id]["aseo"],
                    r.valor_recibido,
                    ESTADO_TXT[r.estado],
                ]
                for r, res, z in rows
            ],
            ["Total (sin anulados)", None, None, None, None, tot_alq, tot_aseo, tot_alq + tot_aseo, None],
        ),
        Tabla("Por zona", [Columna("Zona"), Columna("Total", "dinero")], [[z, v] for z, v in sorted(por_zona.items())]),
    ]


async def _aseo(db: AsyncSession, desde: date, hasta: date) -> tuple[list[tuple[str, str]], list[Tabla]]:
    Principal = aliased(ConceptoRecaudo)
    rows = list(
        await db.execute(
            select(Recaudo, RecaudoItem.valor, Principal.codigo)
            .join(RecaudoItem, RecaudoItem.recaudo_id == Recaudo.id)
            .join(ConceptoRecaudo, ConceptoRecaudo.id == RecaudoItem.concepto_id)
            .join(Principal, Principal.id == Recaudo.concepto_id)
            .where(*_en_rango(desde, hasta), ConceptoRecaudo.codigo == "ASEO")
            .order_by(Recaudo.fecha_recaudo)
            .limit(LIMITE_FILAS)
        )
    )
    activos = [(r, v, c) for r, v, c in rows if r.estado != E.ANULADO]
    directo = sum((v for _, v, c in activos if c == "ASEO"), Decimal(0))
    con_alquiler = sum((v for _, v, c in activos if c != "ASEO"), Decimal(0))
    resumen = [
        ("Cobros de aseo", str(len(activos))),
        ("Aseo cobrado directamente", pesos(directo)),
        ("Aseo cobrado con alquileres", pesos(con_alquiler)),
        ("Total aseo", pesos(directo + con_alquiler)),
    ]
    return resumen, [
        Tabla(
            "Detalle de aseo",
            [
                Columna("N.°", "entero"),
                Columna("Fecha", "fecha"),
                Columna("Pagador"),
                Columna("Origen"),
                Columna("Valor", "dinero"),
                Columna("Estado"),
            ],
            [
                [
                    r.consecutivo,
                    r.fecha_recaudo,
                    r.nombre_pagador,
                    "Directo" if c == "ASEO" else "Con alquiler de zona",
                    v,
                    ESTADO_TXT[r.estado],
                ]
                for r, v, c in rows
            ],
            ["Total (sin anulados)", None, None, None, directo + con_alquiler, None],
        )
    ]


# --- 3. Informe de caja (arqueo) ------------------------------------------------------


async def _efectivo_en_custodia(db: AsyncSession, hasta_excl: date) -> Decimal:
    """Efectivo recibido antes de la fecha que aún no se había consignado en esa fecha."""
    recibido = await db.scalar(
        select(func.coalesce(func.sum(Recaudo.valor_recibido), 0)).where(
            Recaudo.medio_pago == MedioPago.EFECTIVO,
            Recaudo.estado != E.ANULADO,
            Recaudo.fecha_recaudo < _inicio(hasta_excl),
        )
    )
    consignado = await db.scalar(
        select(func.coalesce(func.sum(ConsignacionRecaudo.valor_aplicado), 0))
        .join(Consignacion, Consignacion.id == ConsignacionRecaudo.consignacion_id)
        .join(Recaudo, Recaudo.id == ConsignacionRecaudo.recaudo_id)
        .where(
            Consignacion.estado != EstadoConsignacion.RECHAZADA,
            Consignacion.fecha_consignacion < hasta_excl,
            Recaudo.estado != E.ANULADO,
        )
    )
    return Decimal(recibido) - Decimal(consignado)


async def _caja(db: AsyncSession, desde: date, hasta: date) -> tuple[list[tuple[str, str]], list[Tabla]]:
    inicial = await _efectivo_en_custodia(db, desde)
    final = await _efectivo_en_custodia(db, hasta + timedelta(days=1))
    ingresos = Decimal(
        await db.scalar(
            select(func.coalesce(func.sum(Recaudo.valor_recibido), 0)).where(
                *_en_rango(desde, hasta), Recaudo.medio_pago == MedioPago.EFECTIVO, Recaudo.estado != E.ANULADO
            )
        )
    )
    consignado = inicial + ingresos - final  # cuadra por construcción con las dos fotos de custodia

    cierres = list(
        await db.execute(
            select(CierreCaja, User.full_name)
            .join(User, User.id == CierreCaja.usuario_id)
            .where(CierreCaja.fin_turno >= _inicio(desde), CierreCaja.fin_turno < _inicio(hasta + timedelta(days=1)))
            .order_by(CierreCaja.fin_turno)
        )
    )
    faltantes = sum((-c.diferencia for c, _ in cierres if c.diferencia < 0), Decimal(0))
    sobrantes = sum((c.diferencia for c, _ in cierres if c.diferencia > 0), Decimal(0))
    Entrega, Recibe = aliased(User), aliased(User)
    entregas = list(
        await db.execute(
            select(EntregaInterna, Entrega.full_name, Recibe.full_name)
            .join(Entrega, Entrega.id == EntregaInterna.entregado_por_id)
            .join(Recibe, Recibe.id == EntregaInterna.recibido_por_id)
            .where(
                EntregaInterna.fecha_entrega >= _inicio(desde),
                EntregaInterna.fecha_entrega < _inicio(hasta + timedelta(days=1)),
            )
            .order_by(EntregaInterna.fecha_entrega)
        )
    )
    aplicado = (
        select(ConsignacionRecaudo.consignacion_id, func.sum(ConsignacionRecaudo.valor_aplicado).label("v"))
        .group_by(ConsignacionRecaudo.consignacion_id)
        .subquery()
    )
    consignaciones = list(
        await db.execute(
            select(Consignacion, func.coalesce(aplicado.c.v, 0))
            .outerjoin(aplicado, aplicado.c.consignacion_id == Consignacion.id)
            .where(Consignacion.fecha_consignacion >= desde, Consignacion.fecha_consignacion <= hasta)
            .order_by(Consignacion.fecha_consignacion, Consignacion.consecutivo)
        )
    )
    entregado = sum((e.valor_total for e, _, _ in entregas if e.estado.value == "CONFIRMADA"), Decimal(0))

    resumen = [
        ("Saldo inicial en custodia", pesos(inicial)),
        ("Ingresos en efectivo", pesos(ingresos)),
        ("Consignado en bancos", pesos(consignado)),
        ("Saldo final en custodia", pesos(final)),
        ("Entregas internas confirmadas", pesos(entregado)),
        ("Faltantes / sobrantes en cierres", f"{pesos(faltantes)} / {pesos(sobrantes)}"),
    ]
    return resumen, [
        Tabla(
            "Movimiento del efectivo",
            [Columna("Concepto"), Columna("Valor", "dinero")],
            [
                ["Saldo inicial en custodia (sin consignar)", inicial],
                ["(+) Ingresos en efectivo del periodo", ingresos],
                ["(−) Consignado en bancos", consignado],
            ],
            ["(=) Saldo final en custodia", final],
            "Las entregas internas trasladan efectivo de recepción a la administración sin cambiar el total en custodia.",
        ),
        Tabla(
            "Cierres de caja",
            [
                Columna("N.°", "entero"),
                Columna("Cierre", "fechahora"),
                Columna("Responsable"),
                Columna("Base", "dinero"),
                Columna("Esperado", "dinero"),
                Columna("Contado", "dinero"),
                Columna("Diferencia", "dinero"),
                Columna("Justificación"),
            ],
            [
                [
                    c.consecutivo,
                    c.fin_turno,
                    _nombre(n),
                    c.saldo_inicial,
                    c.saldo_esperado_sistema,
                    c.valor_fisico_contado,
                    c.diferencia,
                    c.observacion_justificacion or "",
                ]
                for c, n in cierres
            ],
        ),
        Tabla(
            "Entregas internas",
            [
                Columna("N.°", "entero"),
                Columna("Fecha", "fechahora"),
                Columna("Entrega"),
                Columna("Recibe"),
                Columna("Valor", "dinero"),
                Columna("Contado", "dinero"),
                Columna("Estado"),
            ],
            [
                [
                    e.consecutivo,
                    e.fecha_entrega,
                    _nombre(de),
                    _nombre(para),
                    e.valor_total,
                    e.valor_contado,
                    {"PENDIENTE_CONFIRMACION": "Por confirmar", "CONFIRMADA": "Confirmada", "RECHAZADA": "Rechazada"}[
                        e.estado.value
                    ],
                ]
                for e, de, para in entregas
            ],
        ),
        Tabla(
            "Consignaciones",
            [
                Columna("N.°", "entero"),
                Columna("Fecha", "fecha"),
                Columna("Banco"),
                Columna("Referencia"),
                Columna("Consignado", "dinero"),
                Columna("Recaudos", "dinero"),
                Columna("Estado"),
            ],
            [
                [
                    c.consecutivo,
                    c.fecha_consignacion,
                    c.banco_destino,
                    c.referencia_bancaria,
                    c.valor_consignado,
                    Decimal(v),
                    {
                        "REGISTRADA": "Por aprobar",
                        "APROBADA": "Aprobada",
                        "VERIFICADA": "Verificada",
                        "RECHAZADA": "Rechazada",
                    }[c.estado.value],
                ]
                for c, v in consignaciones
            ],
        ),
    ]


# --- 4. Trazabilidad y auditoría -------------------------------------------------------

_ACCION = {"CREACION": "Registro", "EDICION": "Edición", "CAMBIO_ESTADO": "Cambio de estado", "ANULACION": "Anulación"}
_ENTIDAD = {
    "recaudo": "Recaudo",
    "cierre_caja": "Cierre de caja",
    "entrega_interna": "Entrega",
    "consignacion": "Consignación",
    "concepto": "Concepto",
}
_ESTADO_POR_CODIGO: dict[Any, str] = {e.value: t for e, t in ESTADO_TXT.items()} | {
    "REGISTRADA": "Por aprobar",
    "APROBADA": "Aprobada",
    "VERIFICADA": "Verificada",
    "RECHAZADA": "Rechazada",
    "PENDIENTE_CONFIRMACION": "Por confirmar",
    "CONFIRMADA": "Confirmada",
}


def _cambio(a: AuditoriaRecaudo) -> str:
    if a.accion.value == "CREACION" or not a.valores_nuevos:
        valor = (a.valores_nuevos or {}).get("valor_recibido") or (a.valores_nuevos or {}).get("valor_consignado")
        return f"Valor {pesos(Decimal(str(valor)))}" if valor else ""
    partes = []
    for k, v in a.valores_nuevos.items():
        if k == "estado":
            antes = (a.valores_anteriores or {}).get(k)
            partes.append(f"estado {_ESTADO_POR_CODIGO.get(antes, antes)} → {_ESTADO_POR_CODIGO.get(v, v)}")
        elif not (k.endswith("_id") or k.endswith("_at")):
            partes.append(k.replace("_", " "))
    return "; ".join(partes)


async def _auditoria(db: AsyncSession, desde: date, hasta: date) -> tuple[list[tuple[str, str]], list[Tabla]]:
    rango = [
        AuditoriaRecaudo.fecha_hora >= _inicio(desde),
        AuditoriaRecaudo.fecha_hora < _inicio(hasta + timedelta(days=1)),
    ]
    eventos = list(
        await db.execute(
            select(AuditoriaRecaudo, User.full_name, Recaudo.consecutivo)
            .outerjoin(User, User.id == AuditoriaRecaudo.usuario_id)
            .outerjoin(Recaudo, Recaudo.id == AuditoriaRecaudo.recaudo_id)
            .where(*rango)
            .order_by(AuditoriaRecaudo.fecha_hora, AuditoriaRecaudo.id)
            .limit(LIMITE_FILAS)
        )
    )
    Anulo = aliased(User)
    anulaciones = list(
        await db.execute(
            select(Recaudo, Anulo.full_name)
            .join(Anulo, Anulo.id == Recaudo.anulado_por_id)
            .where(Recaudo.anulado_at >= _inicio(desde), Recaudo.anulado_at < _inicio(hasta + timedelta(days=1)))
            .order_by(Recaudo.anulado_at)
        )
    )
    con_soporte = await db.scalar(
        select(func.count()).where(*_en_rango(desde, hasta), Recaudo.soporte_key.is_not(None))
    )
    sin_soporte_banco = await db.scalar(
        select(func.count()).where(
            *_en_rango(desde, hasta),
            Recaudo.medio_pago != MedioPago.EFECTIVO,
            Recaudo.soporte_key.is_(None),
            Recaudo.estado != E.ANULADO,
        )
    )
    alertas = list(
        await db.execute(
            select(AlertaRecaudo.tipo, func.count(), func.count().filter(AlertaRecaudo.estado == "ABIERTA"))
            .where(
                AlertaRecaudo.created_at >= _inicio(desde),
                AlertaRecaudo.created_at < _inicio(hasta + timedelta(days=1)),
            )
            .group_by(AlertaRecaudo.tipo)
        )
    )
    resumen = [
        ("Eventos auditados", str(len(eventos))),
        ("Anulaciones", f"{len(anulaciones)} por {pesos(sum((r.valor_recibido for r, _ in anulaciones), Decimal(0)))}"),
        ("Recaudos con soporte adjunto", str(con_soporte)),
        ("Transferencias sin soporte adjunto", str(sin_soporte_banco)),
        ("Alertas generadas (abiertas)", f"{sum(n for _, n, _ in alertas)} ({sum(a for _, _, a in alertas)})"),
    ]
    tipos_alerta = {
        "DIFERENCIA_CIERRE": "Diferencia en cierre de caja",
        "DESCUADRE_CONSIGNACION": "Consignación descuadrada",
        "DESCUADRE_ENTREGA": "Entrega descuadrada",
        "TRANSFERENCIA_SIN_VERIFICAR": "Transferencia sin verificar",
        "ANULACION_POSTERIOR": "Anulación de dinero ya consignado",
    }
    return resumen, [
        Tabla(
            "Anulaciones",
            [
                Columna("N.°", "entero"),
                Columna("Anulado", "fechahora"),
                Columna("Valor", "dinero"),
                Columna("Anuló"),
                Columna("Motivo"),
            ],
            [[r.consecutivo, r.anulado_at, r.valor_recibido, _nombre(n), r.motivo_anulacion] for r, n in anulaciones],
        ),
        Tabla(
            "Alertas del periodo",
            [Columna("Tipo"), Columna("Generadas", "entero"), Columna("Abiertas", "entero")],
            [[tipos_alerta[t.value], n, a] for t, n, a in alertas],
        ),
        Tabla(
            "Historial de movimientos",
            [
                Columna("Fecha", "fechahora"),
                Columna("Usuario"),
                Columna("Registro"),
                Columna("Acción"),
                Columna("Detalle"),
                Columna("Motivo"),
            ],
            [
                [
                    a.fecha_hora,
                    _nombre(n) or "Sistema",
                    f"{_ENTIDAD.get(a.entidad, a.entidad)}{f' #{c}' if c else ''}",
                    _ACCION[a.accion.value],
                    _cambio(a),
                    a.motivo or "",
                ]
                for a, n, c in eventos
            ],
            nota=f"Máximo {LIMITE_FILAS} eventos por informe." if len(eventos) >= LIMITE_FILAS else None,
        ),
    ]


# --- Punto de entrada --------------------------------------------------------------------

_CONSTRUCTORES = {
    "general": _general,
    "parqueadero": _parqueadero,
    "zonas": _zonas,
    "aseo": _aseo,
    "caja": _caja,
    "auditoria": _auditoria,
}


async def generar_reporte(db: AsyncSession, actor: Actor, tipo: str, desde: date, hasta: date) -> Reporte:
    if tipo not in _CONSTRUCTORES:
        raise ValidacionError(f"Tipo de informe desconocido: {tipo}")
    exigir(actor, PERMISOS[tipo], f"generar el {TITULOS[tipo].lower()}")
    _validar_rango(desde, hasta)
    resumen, tablas = await _CONSTRUCTORES[tipo](db, desde, hasta)
    titulo = TITULOS[tipo]
    if tipo == "caja" and actor.role == R.AUXILIAR:
        titulo += " · solo su caja"
    return Reporte(
        tipo=tipo,
        titulo=titulo,
        copropiedad=await _copropiedad(db, actor.tenant_id),
        desde=desde,
        hasta=hasta,
        generado=datetime.now(TZ),
        resumen=resumen,
        tablas=tablas,
    )


# --- 5. Corte mensual consolidado (lo genera SYSTEM; lo lee también el Consejo) -------


async def reporte_corte(db: AsyncSession, tenant_id: uuid.UUID, anio: int, mes: int) -> tuple[Reporte, dict[str, Any]]:
    """Resumen ejecutivo del mes para el Consejo. Devuelve el reporte y los KPIs (JSON del corte)."""
    desde = date(anio, mes, 1)
    hasta = _fin_de_mes(desde)
    datos: dict[str, Any] = await db.scalar(text("SELECT resumen_recaudos(:a, :m)"), {"a": anio, "m": mes})
    res_general, tablas_general = await _general(db, desde, hasta)
    res_caja, _ = await _caja(db, desde, hasta)
    res_auditoria, tablas_auditoria = await _auditoria(db, desde, hasta)
    cierres = list(
        await db.execute(
            select(
                CierreCaja.consecutivo,
                CierreCaja.fin_turno,
                User.full_name,
                CierreCaja.diferencia,
                CierreCaja.observacion_justificacion,
            )
            .join(User, User.id == CierreCaja.usuario_id)
            .where(
                CierreCaja.fin_turno >= _inicio(desde),
                CierreCaja.fin_turno < _inicio(hasta + timedelta(days=1)),
                CierreCaja.diferencia != 0,
            )
            .order_by(CierreCaja.fin_turno)
        )
    )
    resumen = [
        ("Total recaudado en el mes", pesos(Decimal(str(datos["total_mes"])))),
        ("Acumulado del año", pesos(Decimal(str(datos["total_anio"])))),
        ("Movimientos", str(datos["cantidad_mes"])),
        *[kv for kv in res_caja if kv[0] in ("Saldo final en custodia", "Consignado en bancos")],
        (
            "Transferencias por verificar",
            f"{datos['transferencias_pendientes']['cantidad']} por {pesos(Decimal(str(datos['transferencias_pendientes']['total'])))}",
        ),
        *[kv for kv in res_auditoria if kv[0] in ("Anulaciones", "Alertas generadas (abiertas)")],
    ]
    tablas = [
        *tablas_general[:2],
        Tabla(
            "Cierres de caja con diferencia",
            [
                Columna("N.°", "entero"),
                Columna("Cierre", "fechahora"),
                Columna("Responsable"),
                Columna("Diferencia", "dinero"),
                Columna("Justificación"),
            ],
            [[n, f, _nombre(u), d, j or ""] for n, f, u, d, j in cierres],
            nota="Diferencias entre el efectivo esperado y el contado al cerrar cada turno.",
        ),
        *tablas_auditoria[:2],
    ]
    reporte = Reporte(
        tipo="corte",
        titulo=f"{TITULOS['corte']} · {MESES[mes - 1]} de {anio}",
        copropiedad=await _copropiedad(db, tenant_id),
        desde=desde,
        hasta=hasta,
        generado=datetime.now(TZ),
        resumen=resumen,
        tablas=tablas,
    )
    kpis = {
        "total_mes": str(datos["total_mes"]),
        "total_anio": str(datos["total_anio"]),
        "cantidad_mes": datos["cantidad_mes"],
        "por_concepto": datos["por_concepto"],
        "por_medio": datos["por_medio"],
        "efectivo_en_custodia": next(v for k, v in res_caja if k == "Saldo final en custodia"),
        "transferencias_pendientes": datos["transferencias_pendientes"],
        "cierres_con_diferencia": len(cierres),
        "resumen": dict(res_general[:1] + resumen),
    }
    return reporte, kpis
