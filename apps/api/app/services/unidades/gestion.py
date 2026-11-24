"""Casos de uso del censo: unidades, personas, vínculos y vehículos.

Nada se borra: las unidades, personas y vehículos se desactivan, y los vínculos
se cierran con fecha (historial de propietarios y arrendatarios). La base lo
impone con triggers; aquí se validan las reglas con mensajes claros.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Membership, Persona, UnidadPersona, Unit, Vehiculo
from app.models.enums import RelacionUnidad
from app.schemas.unidades import (
    CerrarVinculoIn,
    PersonaIn,
    PersonaUpdate,
    UnidadIn,
    UnidadUpdate,
    VehiculoIn,
    VehiculoUpdate,
    VinculoIn,
    VinculoUpdate,
)
from app.services.comun import Actor, NoEncontrado, ValidacionError, exigir, fijar_motivo, hoy_bogota
from app.services.unidades import dominio as d
from app.services.unidades.dominio import PUEDE_GESTIONAR

# --- Lecturas básicas (la RLS decide qué filas ve cada rol) -----------------------


async def obtener_unidad(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID) -> Unit:
    u = await db.get(Unit, unidad_id)
    if u is None or u.tenant_id != actor.tenant_id:
        raise NoEncontrado("Unidad no encontrada")
    return u


async def obtener_persona(db: AsyncSession, actor: Actor, persona_id: uuid.UUID) -> Persona:
    p = await db.get(Persona, persona_id)
    if p is None or p.tenant_id != actor.tenant_id:
        raise NoEncontrado("Persona no encontrada")
    return p


async def obtener_vinculo(db: AsyncSession, actor: Actor, vinculo_id: uuid.UUID) -> UnidadPersona:
    v = await db.get(UnidadPersona, vinculo_id)
    if v is None or v.tenant_id != actor.tenant_id:
        raise NoEncontrado("Vínculo no encontrado")
    return v


async def obtener_vehiculo(db: AsyncSession, actor: Actor, vehiculo_id: uuid.UUID) -> Vehiculo:
    v = await db.get(Vehiculo, vehiculo_id)
    if v is None or v.tenant_id != actor.tenant_id:
        raise NoEncontrado("Vehículo no encontrado")
    return v


def _activa(u: Unit) -> None:
    if not u.activa:
        raise ValidacionError(f"La unidad {u.etiqueta} está desactivada")


# --- Unidades -------------------------------------------------------------------


async def _validar_unidad(db: AsyncSession, actor: Actor, datos: dict[str, object], propia: Unit | None) -> None:
    torre = datos.get("tower", propia.tower if propia else "")
    numero = datos.get("number", propia.number if propia else None)
    if "tower" in datos or "number" in datos:
        q = select(Unit.id).where(Unit.tenant_id == actor.tenant_id, Unit.tower == torre, Unit.number == numero)
        if propia is not None:
            q = q.where(Unit.id != propia.id)
        if await db.scalar(q):
            raise ValidacionError(f"Ya existe la unidad {d.etiqueta(str(torre), str(numero))}")
    if datos.get("matricula_inmobiliaria"):
        q = select(Unit).where(
            Unit.tenant_id == actor.tenant_id, Unit.matricula_inmobiliaria == datos["matricula_inmobiliaria"]
        )
        if propia is not None:
            q = q.where(Unit.id != propia.id)
        otra = await db.scalar(q)
        if otra is not None:
            raise ValidacionError(
                f"La matrícula {datos['matricula_inmobiliaria']} ya está en la unidad {otra.etiqueta}"
            )
    principal_id = datos.get("unidad_principal_id")
    if principal_id:
        if propia is not None and principal_id == propia.id:
            raise ValidacionError("Una unidad no puede ser anexo de sí misma")
        principal = await obtener_unidad(db, actor, principal_id)  # type: ignore[arg-type]
        _activa(principal)
        if principal.unidad_principal_id is not None:
            raise ValidacionError(f"{principal.etiqueta} es un anexo: elija la unidad principal")
        if propia is not None and await db.scalar(
            select(func.count()).select_from(Unit).where(Unit.unidad_principal_id == propia.id)
        ):
            raise ValidacionError(f"{propia.etiqueta} tiene anexos: no puede ser anexo de otra unidad")


async def crear_unidad(db: AsyncSession, actor: Actor, data: UnidadIn) -> Unit:
    exigir(actor, PUEDE_GESTIONAR, "registrar unidades")
    datos = data.model_dump()
    await _validar_unidad(db, actor, datos, None)
    await fijar_motivo(db, None)
    u = Unit(id=uuid.uuid4(), tenant_id=actor.tenant_id, **datos)
    db.add(u)
    await db.flush()
    return u


async def editar_unidad(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID, data: UnidadUpdate) -> Unit:
    exigir(actor, PUEDE_GESTIONAR, "editar unidades")
    u = await obtener_unidad(db, actor, unidad_id)
    _activa(u)
    cambios = data.model_dump(exclude_unset=True, exclude={"motivo"})
    for obligatorio in ("number", "tipo", "ocupacion"):
        if obligatorio in cambios and cambios[obligatorio] is None:
            raise ValidacionError("El número, el tipo y la ocupación no pueden quedar vacíos")
    if "tower" in cambios and cambios["tower"] is None:
        cambios["tower"] = ""
    cambios = {k: v for k, v in cambios.items() if getattr(u, k) != v}
    if not cambios:
        raise ValidacionError("No hay cambios para guardar")
    await _validar_unidad(db, actor, cambios, u)
    if "coefficient" in cambios and u.coefficient is not None and not data.motivo:
        # El coeficiente define votos y cuotas: cambiarlo exige explicar por qué
        raise ValidacionError("Indique el motivo del cambio de coeficiente (p. ej. reforma del reglamento)")
    await fijar_motivo(db, data.motivo)
    for campo, valor in cambios.items():
        setattr(u, campo, valor)
    await db.flush()
    await fijar_motivo(db, None)
    return u


async def desactivar_unidad(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID, motivo: str) -> Unit:
    """Reemplaza al borrado (p. ej. unidad creada por error o fusionada con otra)."""
    exigir(actor, PUEDE_GESTIONAR, "desactivar unidades")
    u = await obtener_unidad(db, actor, unidad_id)
    _activa(u)
    vinculos = await db.scalar(
        select(func.count())
        .select_from(UnidadPersona)
        .where(UnidadPersona.unidad_id == u.id, UnidadPersona.fecha_fin.is_(None))
    )
    if vinculos:
        raise ValidacionError(f"{u.etiqueta} tiene {vinculos} persona(s) vinculada(s): cierre primero esos vínculos")
    anexos = await db.scalar(
        select(func.count()).select_from(Unit).where(Unit.unidad_principal_id == u.id, Unit.activa.is_(True))
    )
    if anexos:
        raise ValidacionError(f"{u.etiqueta} tiene {anexos} anexo(s) activo(s): desactívelos o reasígnelos primero")
    await fijar_motivo(db, motivo)
    u.activa = False
    await db.flush()
    await fijar_motivo(db, None)
    return u


async def reactivar_unidad(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID, motivo: str) -> Unit:
    exigir(actor, PUEDE_GESTIONAR, "reactivar unidades")
    u = await obtener_unidad(db, actor, unidad_id)
    if u.activa:
        raise ValidacionError(f"La unidad {u.etiqueta} ya está activa")
    await fijar_motivo(db, motivo)
    u.activa = True
    await db.flush()
    await fijar_motivo(db, None)
    return u


# --- Personas -------------------------------------------------------------------


async def _validar_persona(db: AsyncSession, actor: Actor, datos: dict[str, object], propia: Persona | None) -> None:
    tipo = datos.get("tipo_documento", propia.tipo_documento if propia else None)
    numero = datos.get("numero_documento", propia.numero_documento if propia else None)
    if (tipo is None) != (numero is None):
        raise ValidacionError("Indique el tipo y el número de documento, o ninguno de los dos")
    if numero and ("tipo_documento" in datos or "numero_documento" in datos):
        q = select(Persona).where(
            Persona.tenant_id == actor.tenant_id, Persona.tipo_documento == tipo, Persona.numero_documento == numero
        )
        if propia is not None:
            q = q.where(Persona.id != propia.id)
        otra = await db.scalar(q)
        if otra is not None:
            raise ValidacionError(f"Ya existe una persona con {tipo} {numero}: {otra.nombre_completo}")
    if datos.get("user_id"):
        miembro = await db.scalar(
            select(Membership.id).where(Membership.tenant_id == actor.tenant_id, Membership.user_id == datos["user_id"])
        )
        if miembro is None:
            raise ValidacionError("La cuenta de usuario no pertenece a esta copropiedad")
        q = select(Persona).where(Persona.tenant_id == actor.tenant_id, Persona.user_id == datos["user_id"])
        if propia is not None:
            q = q.where(Persona.id != propia.id)
        otra = await db.scalar(q)
        if otra is not None:
            raise ValidacionError(f"Esa cuenta ya está enlazada a {otra.nombre_completo}")


def _datos_persona(data: PersonaIn | PersonaUpdate, propia: Persona | None) -> dict[str, object]:
    datos = data.model_dump(exclude_unset=True, exclude={"motivo", "autoriza_datos"})
    if data.autoriza_datos is True and (propia is None or propia.autoriza_datos_at is None):
        datos["autoriza_datos_at"] = datetime.now(UTC)
    elif data.autoriza_datos is False and propia is not None and propia.autoriza_datos_at is not None:
        datos["autoriza_datos_at"] = None  # revocó la autorización
    if "email" in datos and datos["email"] is not None:
        datos["email"] = str(datos["email"]).lower()
    return datos


async def crear_persona(db: AsyncSession, actor: Actor, data: PersonaIn) -> Persona:
    exigir(actor, PUEDE_GESTIONAR, "registrar personas")
    datos = _datos_persona(data, None)
    await _validar_persona(db, actor, datos, None)
    await fijar_motivo(db, None)
    p = Persona(id=uuid.uuid4(), tenant_id=actor.tenant_id, **datos)
    db.add(p)
    await db.flush()
    return p


async def editar_persona(db: AsyncSession, actor: Actor, persona_id: uuid.UUID, data: PersonaUpdate) -> Persona:
    exigir(actor, PUEDE_GESTIONAR, "editar personas")
    p = await obtener_persona(db, actor, persona_id)
    if not p.activa:
        raise ValidacionError(f"{p.nombre_completo} está desactivada")
    datos = _datos_persona(data, p)
    if "nombre_completo" in datos and not datos["nombre_completo"]:
        raise ValidacionError("El nombre es obligatorio")
    datos = {k: v for k, v in datos.items() if getattr(p, k) != v}
    if not datos:
        raise ValidacionError("No hay cambios para guardar")
    await _validar_persona(db, actor, datos, p)
    await fijar_motivo(db, data.motivo)
    for campo, valor in datos.items():
        setattr(p, campo, valor)
    await db.flush()
    await fijar_motivo(db, None)
    return p


async def desactivar_persona(db: AsyncSession, actor: Actor, persona_id: uuid.UUID, motivo: str) -> Persona:
    exigir(actor, PUEDE_GESTIONAR, "desactivar personas")
    p = await obtener_persona(db, actor, persona_id)
    if not p.activa:
        raise ValidacionError(f"{p.nombre_completo} ya está desactivada")
    vigentes = await db.scalar(
        select(func.count())
        .select_from(UnidadPersona)
        .where(UnidadPersona.persona_id == p.id, UnidadPersona.fecha_fin.is_(None))
    )
    if vigentes:
        raise ValidacionError(f"{p.nombre_completo} tiene {vigentes} vínculo(s) vigente(s): ciérrelos primero")
    await fijar_motivo(db, motivo)
    p.activa = False
    await db.flush()
    await fijar_motivo(db, None)
    return p


# --- Vínculos -------------------------------------------------------------------


async def _vigentes(db: AsyncSession, unidad_id: uuid.UUID) -> list[UnidadPersona]:
    return list(
        await db.scalars(
            select(UnidadPersona).where(UnidadPersona.unidad_id == unidad_id, UnidadPersona.fecha_fin.is_(None))
        )
    )


async def _liberar(db: AsyncSession, vigentes: list[UnidadPersona], campo: str, excepto: uuid.UUID | None) -> None:
    """Contacto principal y responsable de pago son únicos por unidad: el nuevo reemplaza al anterior."""
    cambio = False
    for v in vigentes:
        if v.id != excepto and getattr(v, campo):
            setattr(v, campo, False)
            cambio = True
    if cambio:
        await db.flush()  # antes del INSERT/UPDATE del nuevo, por los índices únicos parciales


async def vincular(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID, data: VinculoIn) -> UnidadPersona:
    exigir(actor, PUEDE_GESTIONAR, "vincular personas a unidades")
    u = await obtener_unidad(db, actor, unidad_id)
    _activa(u)
    if data.persona is not None:
        persona = await crear_persona(db, actor, data.persona)
    else:
        persona = await obtener_persona(db, actor, data.persona_id)  # type: ignore[arg-type]
        if not persona.activa:
            raise ValidacionError(f"{persona.nombre_completo} está desactivada")

    hoy = hoy_bogota()
    inicio = data.fecha_inicio or hoy
    if inicio > hoy:
        raise ValidacionError("La fecha de inicio no puede estar en el futuro")
    vigentes = await _vigentes(db, u.id)
    if any(v.persona_id == persona.id and v.relacion == data.relacion for v in vigentes):
        raise ValidacionError(f"{persona.nombre_completo} ya figura como {data.relacion.lower()} de {u.etiqueta}")
    if data.porcentaje_propiedad is not None:
        try:
            d.validar_porcentajes_propiedad(
                [v.porcentaje_propiedad for v in vigentes if v.relacion == RelacionUnidad.PROPIETARIO]
                + [data.porcentaje_propiedad]
            )
        except ValueError as e:
            raise ValidacionError(str(e)) from None

    contacto = data.es_contacto_principal
    if contacto is None:  # automático: el primero en llegar, si la unidad no tiene
        contacto = not any(v.es_contacto_principal for v in vigentes)
    pago = data.responsable_pago
    if pago is None:  # automático: el primer propietario (la ley obliga al propietario)
        pago = data.relacion == RelacionUnidad.PROPIETARIO and not any(v.responsable_pago for v in vigentes)
    if pago and data.relacion == RelacionUnidad.AUTORIZADO:
        raise ValidacionError("Un autorizado no puede ser el responsable del pago")
    if contacto:
        await _liberar(db, vigentes, "es_contacto_principal", None)
    if pago:
        await _liberar(db, vigentes, "responsable_pago", None)

    await fijar_motivo(db, None)
    v = UnidadPersona(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        unidad_id=u.id,
        persona_id=persona.id,
        relacion=data.relacion,
        porcentaje_propiedad=data.porcentaje_propiedad,
        es_contacto_principal=contacto,
        responsable_pago=pago,
        reside=data.reside,
        fecha_inicio=inicio,
    )
    db.add(v)
    await db.flush()
    return v


async def editar_vinculo(db: AsyncSession, actor: Actor, vinculo_id: uuid.UUID, data: VinculoUpdate) -> UnidadPersona:
    exigir(actor, PUEDE_GESTIONAR, "editar vínculos")
    v = await obtener_vinculo(db, actor, vinculo_id)
    if not v.vigente:
        raise ValidacionError("El vínculo está cerrado y forma parte del historial")
    cambios = {k: val for k, val in data.model_dump(exclude_unset=True).items() if getattr(v, k) != val}
    for campo in ("es_contacto_principal", "responsable_pago", "reside"):
        if campo in cambios and cambios[campo] is None:
            raise ValidacionError("Indique sí o no")
    if not cambios:
        raise ValidacionError("No hay cambios para guardar")
    if cambios.get("porcentaje_propiedad") is not None and v.relacion != RelacionUnidad.PROPIETARIO:
        raise ValidacionError("El porcentaje de propiedad solo aplica a propietarios")
    if cambios.get("responsable_pago") and v.relacion == RelacionUnidad.AUTORIZADO:
        raise ValidacionError("Un autorizado no puede ser el responsable del pago")
    vigentes = await _vigentes(db, v.unidad_id)
    if "porcentaje_propiedad" in cambios:
        try:
            d.validar_porcentajes_propiedad(
                [o.porcentaje_propiedad for o in vigentes if o.relacion == RelacionUnidad.PROPIETARIO and o.id != v.id]
                + [cambios["porcentaje_propiedad"]]
            )
        except ValueError as e:
            raise ValidacionError(str(e)) from None
    if cambios.get("es_contacto_principal"):
        await _liberar(db, vigentes, "es_contacto_principal", v.id)
    if cambios.get("responsable_pago"):
        await _liberar(db, vigentes, "responsable_pago", v.id)
    await fijar_motivo(db, None)
    for campo, valor in cambios.items():
        setattr(v, campo, valor)
    await db.flush()
    return v


async def cerrar_vinculo(db: AsyncSession, actor: Actor, vinculo_id: uuid.UUID, data: CerrarVinculoIn) -> UnidadPersona:
    """Venta, fin del arriendo, mudanza: el vínculo queda en el historial con su fecha de fin."""
    exigir(actor, PUEDE_GESTIONAR, "cerrar vínculos")
    v = await obtener_vinculo(db, actor, vinculo_id)
    if not v.vigente:
        raise ValidacionError("El vínculo ya está cerrado")
    hoy = hoy_bogota()
    fin: date = data.fecha_fin or hoy
    if fin > hoy:
        raise ValidacionError("La fecha de fin no puede estar en el futuro")
    if fin < v.fecha_inicio:
        raise ValidacionError(f"La fecha de fin es anterior al inicio del vínculo ({v.fecha_inicio:%d/%m/%Y})")
    await fijar_motivo(db, data.motivo)
    v.fecha_fin = fin
    v.motivo_cierre = data.motivo
    await db.flush()
    await fijar_motivo(db, None)
    await db.refresh(v)  # el trigger apaga contacto y responsable de pago
    return v


# --- Vehículos ------------------------------------------------------------------


async def _validar_vehiculo(
    db: AsyncSession, actor: Actor, unidad_id: uuid.UUID, datos: dict[str, object], propio: Vehiculo | None
) -> None:
    if datos.get("placa"):
        q = select(Vehiculo).where(
            Vehiculo.tenant_id == actor.tenant_id, Vehiculo.placa == datos["placa"], Vehiculo.activo.is_(True)
        )
        if propio is not None:
            q = q.where(Vehiculo.id != propio.id)
        otro = await db.scalar(q)
        if otro is not None:
            unidad = await db.get(Unit, otro.unidad_id)
            raise ValidacionError(
                f"La placa {datos['placa']} ya está registrada en {unidad.etiqueta if unidad else 'otra unidad'}"
            )
    if datos.get("persona_id"):
        vinculada = await db.scalar(
            select(UnidadPersona.id).where(
                UnidadPersona.unidad_id == unidad_id,
                UnidadPersona.persona_id == datos["persona_id"],
                UnidadPersona.fecha_fin.is_(None),
            )
        )
        if vinculada is None:
            raise ValidacionError("El dueño del vehículo debe estar vinculado a la unidad")


async def registrar_vehiculo(db: AsyncSession, actor: Actor, unidad_id: uuid.UUID, data: VehiculoIn) -> Vehiculo:
    exigir(actor, PUEDE_GESTIONAR, "registrar vehículos")
    u = await obtener_unidad(db, actor, unidad_id)
    _activa(u)
    datos = data.model_dump()
    await _validar_vehiculo(db, actor, u.id, datos, None)
    await fijar_motivo(db, None)
    v = Vehiculo(id=uuid.uuid4(), tenant_id=actor.tenant_id, unidad_id=u.id, **datos)
    db.add(v)
    await db.flush()
    return v


async def editar_vehiculo(db: AsyncSession, actor: Actor, vehiculo_id: uuid.UUID, data: VehiculoUpdate) -> Vehiculo:
    exigir(actor, PUEDE_GESTIONAR, "editar vehículos")
    v = await obtener_vehiculo(db, actor, vehiculo_id)
    if not v.activo:
        raise ValidacionError(f"El vehículo {v.placa} está dado de baja")
    cambios = {k: val for k, val in data.model_dump(exclude_unset=True).items() if getattr(v, k) != val}
    if "placa" in cambios and not cambios["placa"]:
        raise ValidacionError("La placa es obligatoria")
    if "tipo" in cambios and cambios["tipo"] is None:
        raise ValidacionError("El tipo de vehículo es obligatorio")
    if not cambios:
        raise ValidacionError("No hay cambios para guardar")
    await _validar_vehiculo(db, actor, v.unidad_id, cambios, v)
    await fijar_motivo(db, None)
    for campo, valor in cambios.items():
        setattr(v, campo, valor)
    await db.flush()
    return v


async def retirar_vehiculo(db: AsyncSession, actor: Actor, vehiculo_id: uuid.UUID, motivo: str) -> Vehiculo:
    exigir(actor, PUEDE_GESTIONAR, "retirar vehículos")
    v = await obtener_vehiculo(db, actor, vehiculo_id)
    if not v.activo:
        raise ValidacionError(f"El vehículo {v.placa} ya estaba retirado")
    await fijar_motivo(db, motivo)
    v.activo = False
    await db.flush()
    await fijar_motivo(db, None)
    return v


# --- Coeficientes ---------------------------------------------------------------


async def estado_coeficientes(db: AsyncSession, actor: Actor) -> d.EstadoCoeficientes:
    exigir(actor, d.PUEDE_VER_DATOS_PREDIALES, "consultar coeficientes")
    filas = await db.scalars(select(Unit.coefficient).where(Unit.tenant_id == actor.tenant_id, Unit.activa.is_(True)))
    return d.estado_coeficientes(filas)
