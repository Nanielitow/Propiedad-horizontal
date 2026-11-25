"""Consultas del censo: listado de unidades, ficha, directorio, placas y "mi unidad".

La RLS ya decide qué FILAS ve cada rol; aquí se decide qué CAMPOS: coeficientes
y matrícula solo para quien ve datos prediales; documento, correo y notas solo
para administración y contabilidad (o la propia persona).
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import Select, String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditoriaUnidad,
    ConceptoRecaudo,
    Persona,
    Recaudo,
    UnidadPersona,
    Unit,
    User,
    Vehiculo,
)
from app.models.enums import OcupacionUnidad, RelacionUnidad, TipoUnidad, UserRole
from app.schemas.unidades_out import (
    AuditoriaOut,
    CoeficientesOut,
    PersonaDetalle,
    PersonaOut,
    PersonaRef,
    PersonaResumen,
    PersonasPagina,
    PlacaOut,
    RecaudoUnidad,
    ResumenUnidades,
    UnidadDetalle,
    UnidadesPagina,
    UnidadRef,
    UnidadResumen,
    VehiculoOut,
    VinculoOut,
)
from app.services.comun import Actor, NoEncontrado, exigir
from app.services.unidades import dominio as d
from app.services.unidades.gestion import estado_coeficientes

R = UserRole
VE_RECAUDOS = frozenset({R.ADMIN, R.AUXILIAR, R.CONTABILIDAD})
_ORDEN_RELACION = {RelacionUnidad.PROPIETARIO: 0, RelacionUnidad.ARRENDATARIO: 1, RelacionUnidad.RESIDENTE: 2}


@dataclass(frozen=True)
class FiltroUnidades:
    torre: str | None = None
    tipo: TipoUnidad | None = None
    ocupacion: OcupacionUnidad | None = None
    texto: str | None = None  # unidad, nombre, documento, teléfono o placa
    incluir_inactivas: bool = False
    solo_principales: bool = False  # oculta parqueaderos/depósitos anexos
    sin_propietario: bool = False


# --- Piezas ---------------------------------------------------------------------


def _ref(u: Unit) -> UnidadRef:
    return UnidadRef(id=u.id, etiqueta=u.etiqueta, tipo=u.tipo)


def _ve_sensibles(actor: Actor, p: Persona) -> bool:
    return actor.role in d.PUEDE_VER_DATOS_SENSIBLES or (p.user_id is not None and p.user_id == actor.user_id)


def persona_out(actor: Actor, p: Persona) -> PersonaOut:
    s = _ve_sensibles(actor, p)
    return PersonaOut(
        id=p.id,
        nombre_completo=p.nombre_completo,
        telefono=p.telefono,
        telefono_alterno=p.telefono_alterno,
        tipo_documento=p.tipo_documento if s else None,
        numero_documento=p.numero_documento if s else None,
        email=p.email if s else None,
        notas=p.notas if actor.role in d.PUEDE_VER_DATOS_SENSIBLES else None,
        tiene_cuenta=p.user_id is not None,
        autoriza_datos_at=p.autoriza_datos_at if s else None,
        activa=p.activa,
    )


def _persona_ref(p: Persona) -> PersonaRef:
    return PersonaRef(id=p.id, nombre=p.nombre_completo, telefono=p.telefono)


def _vinculo_out(actor: Actor, v: UnidadPersona, u: Unit, p: Persona) -> VinculoOut:
    return VinculoOut(
        id=v.id,
        unidad=_ref(u),
        persona=persona_out(actor, p),
        relacion=v.relacion,
        porcentaje_propiedad=v.porcentaje_propiedad,
        es_contacto_principal=v.es_contacto_principal,
        responsable_pago=v.responsable_pago,
        reside=v.reside,
        fecha_inicio=v.fecha_inicio,
        fecha_fin=v.fecha_fin,
        motivo_cierre=v.motivo_cierre if actor.role in d.PUEDE_VER_DIRECTORIO else None,
    )


def _vehiculo_out(v: Vehiculo, u: Unit, p: Persona | None) -> VehiculoOut:
    return VehiculoOut(
        id=v.id,
        unidad=_ref(u),
        persona=_persona_ref(p) if p else None,
        placa=v.placa,
        tipo=v.tipo,
        marca=v.marca,
        color=v.color,
        activo=v.activo,
    )


def orden_unidad(u: Unit) -> tuple[str, int, int, str]:
    """'2-301' antes que '2-1001' (orden natural) y los números con letras ('PQ-01') al final de la torre."""
    digitos = "".join(c for c in u.number if c.isdigit())
    return (u.tower.zfill(4), 0 if u.number[:1].isdigit() else 1, int(digitos) if digitos else 0, u.number)


async def _vigentes_con_persona(
    db: AsyncSession, unidad_ids: Iterable[uuid.UUID] | None = None
) -> list[tuple[UnidadPersona, Persona]]:
    q = (
        select(UnidadPersona, Persona)
        .join(Persona, Persona.id == UnidadPersona.persona_id)
        .where(UnidadPersona.fecha_fin.is_(None))
    )
    if unidad_ids is not None:
        q = q.where(UnidadPersona.unidad_id.in_(list(unidad_ids)))
    return [(v, p) for v, p in (await db.execute(q)).all()]


def _resumen(
    actor: Actor,
    u: Unit,
    por_id: dict[uuid.UUID, Unit],
    anexos: dict[uuid.UUID, list[Unit]],
    vinculos: list[tuple[UnidadPersona, Persona]],
    vehiculos: int,
) -> UnidadResumen:
    prediales = actor.role in d.PUEDE_VER_DATOS_PREDIALES
    principal = por_id.get(u.unidad_principal_id) if u.unidad_principal_id else None
    ordenados = sorted(vinculos, key=lambda vp: (_ORDEN_RELACION.get(vp[0].relacion, 9), vp[1].nombre_completo))
    contacto = next((p for v, p in ordenados if v.es_contacto_principal), None)
    pago = next((p for v, p in ordenados if v.responsable_pago), None)
    return UnidadResumen(
        id=u.id,
        etiqueta=u.etiqueta,
        tower=u.tower,
        number=u.number,
        tipo=u.tipo,
        ocupacion=u.ocupacion,
        activa=u.activa,
        coefficient=u.coefficient if prediales else None,
        area_m2=u.area_m2 if prediales else None,
        unidad_principal=_ref(principal) if principal else None,
        anexos=[_ref(a) for a in sorted(anexos.get(u.id, []), key=orden_unidad)],
        propietarios=[_persona_ref(p) for v, p in ordenados if v.relacion == RelacionUnidad.PROPIETARIO],
        contacto=_persona_ref(contacto) if contacto else None,
        responsable_pago=_persona_ref(pago) if pago else None,
        residentes=sum(1 for v, _ in vinculos if v.reside),
        vehiculos=vehiculos if actor.role in d.PUEDE_VER_VEHICULOS else None,
    )


def _texto_unidades(q: Select[tuple[Unit]], texto: str) -> Select[tuple[Unit]]:
    patron = f"%{texto.strip()}%"
    try:
        placa: str | None = d.normalizar_placa(texto)
    except ValueError:
        placa = None
    por_persona = (
        select(UnidadPersona.unidad_id)
        .join(Persona, Persona.id == UnidadPersona.persona_id)
        .where(
            UnidadPersona.fecha_fin.is_(None),
            or_(
                func.unaccent(Persona.nombre_completo).ilike(func.unaccent(patron)),
                Persona.numero_documento.ilike(patron),
                Persona.telefono.ilike(patron),
            ),
        )
    )
    condiciones = [
        (Unit.tower + "-" + Unit.number).ilike(patron),
        Unit.number.ilike(patron),
        Unit.matricula_inmobiliaria.ilike(patron),
        Unit.id.in_(por_persona),
    ]
    if placa:
        condiciones.append(Unit.id.in_(select(Vehiculo.unidad_id).where(Vehiculo.placa == placa, Vehiculo.activo)))
    return q.where(or_(*condiciones))


# --- Unidades -------------------------------------------------------------------


async def listar_unidades(
    db: AsyncSession, actor: Actor, f: FiltroUnidades, *, page: int = 1, page_size: int = 50
) -> UnidadesPagina:
    exigir(actor, d.PUEDE_VER_UNIDADES, "consultar el censo de unidades")
    todas = list(await db.scalars(select(Unit)))
    por_id = {u.id: u for u in todas}
    anexos: dict[uuid.UUID, list[Unit]] = defaultdict(list)
    for u in todas:
        if u.unidad_principal_id and (u.activa or f.incluir_inactivas):
            anexos[u.unidad_principal_id].append(u)

    q = select(Unit)
    if not f.incluir_inactivas:
        q = q.where(Unit.activa.is_(True))
    if f.torre is not None:
        q = q.where(Unit.tower == d.normalizar_torre(f.torre))
    if f.tipo:
        q = q.where(Unit.tipo == f.tipo)
    if f.ocupacion:
        q = q.where(Unit.ocupacion == f.ocupacion)
    if f.solo_principales:
        q = q.where(Unit.unidad_principal_id.is_(None))
    if f.texto and f.texto.strip():
        if actor.role in d.PUEDE_VER_DIRECTORIO:
            q = _texto_unidades(q, f.texto)
        else:  # sin acceso al directorio, solo busca por la unidad
            q = q.where((Unit.tower + "-" + Unit.number).ilike(f"%{f.texto.strip()}%"))
    if f.sin_propietario:
        q = q.where(
            Unit.unidad_principal_id.is_(None),
            ~Unit.id.in_(
                select(UnidadPersona.unidad_id).where(
                    UnidadPersona.fecha_fin.is_(None), UnidadPersona.relacion == RelacionUnidad.PROPIETARIO
                )
            ),
        )
    filtradas = sorted(await db.scalars(q), key=orden_unidad)
    total = len(filtradas)
    pagina = filtradas[(page - 1) * page_size : page * page_size]
    ids = [u.id for u in pagina]

    vinculos: dict[uuid.UUID, list[tuple[UnidadPersona, Persona]]] = defaultdict(list)
    if actor.role in d.PUEDE_VER_DIRECTORIO:
        for v, p in await _vigentes_con_persona(db, ids):
            vinculos[v.unidad_id].append((v, p))
    vehiculos: dict[uuid.UUID, int] = {}
    if actor.role in d.PUEDE_VER_VEHICULOS:
        vehiculos = dict(
            (
                await db.execute(
                    select(Vehiculo.unidad_id, func.count())
                    .where(Vehiculo.unidad_id.in_(ids), Vehiculo.activo)
                    .group_by(Vehiculo.unidad_id)
                )
            ).all()
        )
    return UnidadesPagina(
        items=[_resumen(actor, u, por_id, anexos, vinculos[u.id], vehiculos.get(u.id, 0)) for u in pagina],
        total=total,
        page=page,
        page_size=page_size,
    )


async def resumen(db: AsyncSession, actor: Actor) -> ResumenUnidades:
    exigir(actor, d.PUEDE_VER_UNIDADES, "consultar el censo de unidades")
    activas = list(await db.scalars(select(Unit).where(Unit.activa.is_(True))))
    principales = [u for u in activas if u.unidad_principal_id is None]
    por_tipo: dict[str, int] = defaultdict(int)
    por_ocupacion: dict[str, int] = defaultdict(int)
    for u in activas:
        por_tipo[u.tipo.value] += 1
    for u in principales:
        por_ocupacion[u.ocupacion.value] += 1

    sin_prop = sin_pago = 0
    personas = vehiculos = None
    if actor.role in d.PUEDE_VER_DIRECTORIO:
        vig = await _vigentes_con_persona(db)
        con_prop = {v.unidad_id for v, _ in vig if v.relacion == RelacionUnidad.PROPIETARIO}
        con_pago = {v.unidad_id for v, _ in vig if v.responsable_pago}
        sin_prop = sum(1 for u in principales if u.id not in con_prop)
        sin_pago = sum(1 for u in principales if u.id not in con_pago)
        personas = await db.scalar(select(func.count()).select_from(Persona).where(Persona.activa))
    if actor.role in d.PUEDE_VER_VEHICULOS:
        vehiculos = await db.scalar(select(func.count()).select_from(Vehiculo).where(Vehiculo.activo))

    coef = None
    if actor.role in d.PUEDE_VER_DATOS_PREDIALES:
        e = await estado_coeficientes(db, actor)
        coef = CoeficientesOut(
            suma=e.suma,
            diferencia=e.diferencia,
            cuadra=e.cuadra,
            unidades_con_coeficiente=e.unidades_con_coeficiente,
            unidades_sin_coeficiente=e.unidades_sin_coeficiente,
            mensaje=e.mensaje,
        )
    torres = sorted({u.tower for u in activas if u.tower}, key=lambda t: (len(t), t))
    return ResumenUnidades(
        total=len(activas),
        por_tipo=dict(por_tipo),
        por_ocupacion=dict(por_ocupacion),
        sin_propietario=sin_prop,
        sin_responsable_pago=sin_pago,
        personas=personas,
        vehiculos=vehiculos,
        torres=torres,
        coeficientes=coef,
    )


async def ficha_unidad(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID) -> UnidadDetalle:
    u = await db.get(Unit, unidad_id)  # la RLS devuelve None al residente si no es suya
    if u is None or u.tenant_id != actor.tenant_id:
        raise NoEncontrado("Unidad no encontrada")
    if actor.role != R.RESIDENTE:  # el residente llega aquí solo con su unidad (RLS)
        exigir(actor, d.PUEDE_VER_UNIDADES, "consultar unidades")
    relacionadas = list(
        await db.scalars(select(Unit).where(or_(Unit.unidad_principal_id == u.id, Unit.id == u.unidad_principal_id)))
    )
    por_id = {x.id: x for x in [u, *relacionadas]}
    anexos = {u.id: [x for x in relacionadas if x.unidad_principal_id == u.id]}

    todas = list(
        (
            await db.execute(
                select(UnidadPersona, Persona)
                .join(Persona, Persona.id == UnidadPersona.persona_id)
                .where(UnidadPersona.unidad_id == u.id)
                .order_by(UnidadPersona.fecha_inicio.desc())
            )
        ).all()
    )
    vigentes = [(v, p) for v, p in todas if v.fecha_fin is None]
    ordenados = sorted(vigentes, key=lambda vp: (_ORDEN_RELACION.get(vp[0].relacion, 9), vp[1].nombre_completo))
    historial = (
        [_vinculo_out(actor, v, u, p) for v, p in todas if v.fecha_fin is not None]
        if actor.role in d.PUEDE_VER_DIRECTORIO
        else []
    )

    ids_vehiculos = [u.id, *(a.id for a in anexos[u.id])]
    vehiculos = list(
        (
            await db.execute(
                select(Vehiculo, Persona)
                .outerjoin(Persona, Persona.id == Vehiculo.persona_id)
                .where(Vehiculo.unidad_id.in_(ids_vehiculos), Vehiculo.activo)
                .order_by(Vehiculo.placa)
            )
        ).all()
    )

    recaudos: list[RecaudoUnidad] = []
    if actor.role in VE_RECAUDOS:
        filas = await db.execute(
            select(Recaudo, ConceptoRecaudo.nombre)
            .join(ConceptoRecaudo, ConceptoRecaudo.id == Recaudo.concepto_id)
            .where(Recaudo.unidad_id == u.id)
            .order_by(Recaudo.fecha_recaudo.desc())
            .limit(10)
        )
        recaudos = [
            RecaudoUnidad(
                id=r.id,
                consecutivo=r.consecutivo,
                fecha_recaudo=r.fecha_recaudo,
                concepto=nombre,
                valor=r.valor_recibido,
                estado=r.estado.value,
            )
            for r, nombre in filas.all()
        ]

    auditoria: list[AuditoriaOut] = []
    if actor.role in d.PUEDE_VER_AUDITORIA:
        filas_a = await db.execute(
            select(AuditoriaUnidad, User.full_name)
            .outerjoin(User, User.id == AuditoriaUnidad.usuario_id)
            .where(AuditoriaUnidad.unidad_id == u.id)
            .order_by(AuditoriaUnidad.fecha_hora.desc(), AuditoriaUnidad.id.desc())
            .limit(30)
        )
        auditoria = [
            AuditoriaOut(
                fecha_hora=a.fecha_hora,
                entidad=a.entidad,
                accion=a.accion,
                usuario=nombre,
                motivo=a.motivo,
                cambios=a.valores_nuevos,
            )
            for a, nombre in filas_a.all()
        ]

    base = _resumen(actor, u, por_id, anexos, vigentes, len(vehiculos))
    prediales = actor.role in d.PUEDE_VER_DATOS_PREDIALES or actor.role == R.RESIDENTE
    if actor.role == R.RESIDENTE:  # su propia unidad: ve su coeficiente y área
        base.coefficient, base.area_m2 = u.coefficient, u.area_m2
    return UnidadDetalle(
        **base.model_dump(),
        matricula_inmobiliaria=u.matricula_inmobiliaria if prediales else None,
        observaciones=u.observaciones if actor.role in d.PUEDE_VER_DIRECTORIO else None,
        ocupacion_sugerida=d.ocupacion_sugerida(d.VinculoResumen(v.relacion, v.reside) for v, _ in vigentes),
        vinculos=[_vinculo_out(actor, v, u, p) for v, p in ordenados],
        historial=historial,
        vehiculos_lista=[_vehiculo_out(v, por_id.get(v.unidad_id, u), p) for v, p in vehiculos],
        recaudos=recaudos,
        auditoria=auditoria,
        created_at=u.created_at,
        updated_at=u.updated_at,
    )


async def mi_unidad(db: AsyncSession, actor: Actor) -> list[UnidadDetalle]:
    """Las unidades principales donde la persona con esta cuenta tiene un vínculo vigente."""
    ids = list(
        await db.scalars(
            select(UnidadPersona.unidad_id)
            .join(Persona, Persona.id == UnidadPersona.persona_id)
            .join(Unit, Unit.id == UnidadPersona.unidad_id)
            .where(
                Persona.user_id == actor.user_id, UnidadPersona.fecha_fin.is_(None), Unit.unidad_principal_id.is_(None)
            )
            .distinct()
        )
    )
    return [await ficha_unidad(db, actor, i) for i in ids]


# --- Personas -------------------------------------------------------------------


async def directorio(
    db: AsyncSession,
    actor: Actor,
    *,
    texto: str | None = None,
    relacion: RelacionUnidad | None = None,
    incluir_inactivas: bool = False,
    sin_unidad: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> PersonasPagina:
    exigir(actor, d.PUEDE_VER_DIRECTORIO, "consultar el directorio")
    q = select(Persona)
    if not incluir_inactivas:
        q = q.where(Persona.activa)
    if texto and texto.strip():
        patron = f"%{texto.strip()}%"
        condiciones = [
            func.unaccent(Persona.nombre_completo).ilike(func.unaccent(patron)),
            Persona.telefono.ilike(patron),
        ]
        if actor.role in d.PUEDE_VER_DATOS_SENSIBLES:
            condiciones += [Persona.numero_documento.ilike(patron), cast(Persona.email, String).ilike(patron)]
        q = q.where(or_(*condiciones))
    vigentes = select(UnidadPersona.persona_id).where(UnidadPersona.fecha_fin.is_(None))
    if relacion:
        q = q.where(Persona.id.in_(vigentes.where(UnidadPersona.relacion == relacion)))
    if sin_unidad:
        q = q.where(~Persona.id.in_(vigentes))
    total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
    personas = list(
        await db.scalars(
            q.order_by(func.lower(Persona.nombre_completo)).offset((page - 1) * page_size).limit(page_size)
        )
    )
    ids = [p.id for p in personas]
    unidades: dict[uuid.UUID, list[UnidadRef]] = defaultdict(list)
    relaciones: dict[uuid.UUID, list[RelacionUnidad]] = defaultdict(list)
    filas = await db.execute(
        select(UnidadPersona, Unit)
        .join(Unit, Unit.id == UnidadPersona.unidad_id)
        .where(UnidadPersona.persona_id.in_(ids), UnidadPersona.fecha_fin.is_(None))
    )
    for v, u in sorted(filas.all(), key=lambda vu: orden_unidad(vu[1])):
        if all(r.id != u.id for r in unidades[v.persona_id]):
            unidades[v.persona_id].append(_ref(u))
        if v.relacion not in relaciones[v.persona_id]:
            relaciones[v.persona_id].append(v.relacion)
    return PersonasPagina(
        items=[
            PersonaResumen(**persona_out(actor, p).model_dump(), unidades=unidades[p.id], relaciones=relaciones[p.id])
            for p in personas
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def ficha_persona(db: AsyncSession, actor: Actor, persona_id: uuid.UUID) -> PersonaDetalle:
    p = await db.get(Persona, persona_id)
    if p is None or p.tenant_id != actor.tenant_id:
        raise NoEncontrado("Persona no encontrada")
    filas = await db.execute(
        select(UnidadPersona, Unit)
        .join(Unit, Unit.id == UnidadPersona.unidad_id)
        .where(UnidadPersona.persona_id == p.id)
        .order_by(UnidadPersona.fecha_fin.desc().nulls_first(), UnidadPersona.fecha_inicio.desc())
    )
    vinculos = [_vinculo_out(actor, v, u, p) for v, u in filas.all()]
    vehiculos: list[VehiculoOut] = []
    if actor.role in d.PUEDE_VER_VEHICULOS or p.user_id == actor.user_id:
        fv = await db.execute(
            select(Vehiculo, Unit).join(Unit, Unit.id == Vehiculo.unidad_id).where(Vehiculo.persona_id == p.id)
        )
        vehiculos = [_vehiculo_out(v, u, p) for v, u in fv.all()]
    return PersonaDetalle(**persona_out(actor, p).model_dump(), vinculos=vinculos, vehiculos=vehiculos)


# --- Vehículos ------------------------------------------------------------------


async def buscar_placa(db: AsyncSession, actor: Actor, placa: str) -> PlacaOut:
    """La usa recepción al registrar un parqueadero: ¿residente o visitante?"""
    exigir(actor, d.PUEDE_VER_VEHICULOS, "consultar vehículos")
    normal = d.normalizar_placa(placa)
    fila = (
        await db.execute(
            select(Vehiculo, Unit, Persona)
            .join(Unit, Unit.id == Vehiculo.unidad_id)
            .outerjoin(Persona, Persona.id == Vehiculo.persona_id)
            .where(Vehiculo.placa == normal, Vehiculo.activo)
        )
    ).first()
    if fila is None:
        return PlacaOut(placa=normal, registrada=False, vehiculo=None)
    v, u, p = fila
    return PlacaOut(placa=normal, registrada=True, vehiculo=_vehiculo_out(v, u, p))


async def vehiculos_de_unidad(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID) -> list[VehiculoOut]:
    u = await db.get(Unit, unidad_id)
    if u is None or u.tenant_id != actor.tenant_id:
        raise NoEncontrado("Unidad no encontrada")
    filas = await db.execute(
        select(Vehiculo, Persona)
        .outerjoin(Persona, Persona.id == Vehiculo.persona_id)
        .where(Vehiculo.unidad_id == u.id)
        .order_by(Vehiculo.activo.desc(), Vehiculo.placa)
    )
    return [_vehiculo_out(v, u, p) for v, p in filas.all()]
