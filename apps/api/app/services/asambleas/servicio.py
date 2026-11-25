"""Casos de uso de la asamblea: preparar, convocar, abrir (padrón), asistencia y poderes,
quórum en vivo, votaciones ponderadas por coeficiente y cierre."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import any_, func, literal, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Asamblea,
    AsistenciaAsamblea,
    CarteraConfig,
    PadronAsamblea,
    Persona,
    PuntoAsamblea,
    UnidadPersona,
    Unit,
    User,
    VotoAsamblea,
)
from app.models.enums import (
    CategoriaCircular,
    EstadoAsamblea,
    EstadoPunto,
    MayoriaPunto,
    ModalidadAsamblea,
    RelacionUnidad,
    TipoAsistente,
    TipoPunto,
    UserRole,
)
from app.schemas.asambleas import (
    AbrirIn,
    AsambleaIn,
    AsambleaUpdate,
    AsistenciaIn,
    CancelarIn,
    CerrarIn,
    ConvocarIn,
    PuntoIn,
    PuntoUpdate,
    VotoPortalIn,
    VotoSalaIn,
)
from app.schemas.portal import CircularIn
from app.services.asambleas import dominio as d
from app.services.cartera import comun as cartera
from app.services.comun import (
    TZ,
    Actor,
    NoEncontrado,
    PermisoDenegado,
    ValidacionError,
    exigir,
    fijar_motivo,
    hoy_bogota,
)
from app.services.portal import circulares

R = UserRole
EA = EstadoAsamblea
EP = EstadoPunto


async def obtener(db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID) -> Asamblea:
    a = await db.get(Asamblea, asamblea_id)
    if a is None or a.tenant_id != actor.tenant_id:
        raise NoEncontrado("Asamblea no encontrada")
    return a


async def punto(db: AsyncSession, actor: Actor, punto_id: uuid.UUID) -> PuntoAsamblea:
    p = await db.get(PuntoAsamblea, punto_id)
    if p is None or p.tenant_id != actor.tenant_id:
        raise NoEncontrado("Punto del orden del día no encontrado")
    return p


def _exigir_estado(a: Asamblea, *estados: EstadoAsamblea) -> None:
    if a.estado not in estados:
        nombres = {
            EA.PROGRAMADA: "programada",
            EA.EN_CURSO: "en curso",
            EA.CERRADA: "cerrada",
            EA.CANCELADA: "cancelada",
        }
        raise ValidacionError(f"La asamblea está {nombres[a.estado]}")


# --- Preparación ---------------------------------------------------------------------------


def _punto(actor: Actor, a: Asamblea, orden: int, data: PuntoIn) -> PuntoAsamblea:
    return PuntoAsamblea(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        asamblea_id=a.id,
        orden=orden,
        titulo=data.titulo,
        descripcion=data.descripcion,
        tipo=data.tipo,
        mayoria=data.mayoria,
        opciones=d.normalizar_opciones(data.opciones, data.mayoria) if data.tipo == TipoPunto.VOTACION else [],
    )


async def crear(db: AsyncSession, actor: Actor, data: AsambleaIn) -> Asamblea:
    exigir(actor, d.PUEDE_GESTIONAR, "programar asambleas")
    a = Asamblea(
        id=uuid.uuid4(), tenant_id=actor.tenant_id, creada_por_id=actor.user_id, **data.model_dump(exclude={"puntos"})
    )
    db.add(a)
    await db.flush()
    for i, p in enumerate(data.puntos, start=1):
        db.add(_punto(actor, a, i, p))
    await db.flush()
    return a


async def editar(db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID, data: AsambleaUpdate) -> Asamblea:
    exigir(actor, d.PUEDE_GESTIONAR, "editar asambleas")
    a = await obtener(db, actor, asamblea_id)
    _exigir_estado(a, EA.PROGRAMADA)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None or k in ("lugar", "observaciones"):
            setattr(a, k, v)
    await db.flush()
    return a


async def agregar_punto(db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID, data: PuntoIn) -> PuntoAsamblea:
    exigir(actor, d.PUEDE_GESTIONAR, "editar el orden del día")
    a = await obtener(db, actor, asamblea_id)
    _exigir_estado(a, EA.PROGRAMADA, EA.EN_CURSO)
    ultimo = await db.scalar(select(func.max(PuntoAsamblea.orden)).where(PuntoAsamblea.asamblea_id == a.id)) or 0
    p = _punto(actor, a, ultimo + 1, data)
    db.add(p)
    await db.flush()
    return p


async def editar_punto(db: AsyncSession, actor: Actor, punto_id: uuid.UUID, data: PuntoUpdate) -> PuntoAsamblea:
    exigir(actor, d.PUEDE_GESTIONAR, "editar el orden del día")
    p = await punto(db, actor, punto_id)
    a = await obtener(db, actor, p.asamblea_id)
    _exigir_estado(a, EA.PROGRAMADA, EA.EN_CURSO)
    cambios = data.model_dump(exclude_unset=True)
    if p.estado != EP.PENDIENTE and set(cambios) - {"conclusion"}:
        raise ValidacionError("Del punto ya tratado solo se puede escribir la conclusión para el acta")
    for k, v in cambios.items():
        setattr(p, k, v)
    await db.flush()
    return p


async def quitar_punto(db: AsyncSession, actor: Actor, punto_id: uuid.UUID) -> None:
    exigir(actor, d.PUEDE_GESTIONAR, "editar el orden del día")
    p = await punto(db, actor, punto_id)
    if p.estado != EP.PENDIENTE:
        raise ValidacionError("Solo se quitan puntos que aún no se han tratado")
    a = await obtener(db, actor, p.asamblea_id)
    _exigir_estado(a, EA.PROGRAMADA, EA.EN_CURSO)
    await db.delete(p)
    await db.flush()
    # Renumerar (la restricción de orden único es diferida al final de la transacción)
    restantes = list(
        await db.scalars(select(PuntoAsamblea).where(PuntoAsamblea.asamblea_id == a.id).order_by(PuntoAsamblea.orden))
    )
    for i, x in enumerate(restantes, start=1):
        x.orden = i
    await db.flush()


async def convocar(
    db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID, data: ConvocarIn
) -> tuple[Asamblea, str | None]:
    """Publica la convocatoria como circular importante con el orden del día (y aviso por correo)."""
    exigir(actor, d.PUEDE_GESTIONAR, "convocar asambleas")
    a = await obtener(db, actor, asamblea_id)
    _exigir_estado(a, EA.PROGRAMADA)
    if a.circular_id is not None:
        raise ValidacionError("La asamblea ya fue convocada")
    puntos = list(
        await db.scalars(select(PuntoAsamblea).where(PuntoAsamblea.asamblea_id == a.id).order_by(PuntoAsamblea.orden))
    )
    if not puntos:
        raise ValidacionError("Agregue el orden del día antes de convocar")
    local = a.fecha_hora.astimezone(TZ)
    meses = [
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
    cuando = f"{local.day} de {meses[local.month - 1]} de {local.year} a las {local:%I:%M %p}".replace(
        "AM", "a. m."
    ).replace("PM", "p. m.")
    modo = {
        ModalidadAsamblea.PRESENCIAL: "presencial",
        ModalidadAsamblea.VIRTUAL: "virtual (por la plataforma)",
        ModalidadAsamblea.MIXTA: "mixta (presencial y por la plataforma)",
    }[a.modalidad]
    cuerpo = "\n\n".join(
        x
        for x in [
            f"Se convoca a todos los copropietarios a la **asamblea general {a.tipo.value.lower()}** {modo}, el **{cuando}**"
            + (f" en {a.lugar}" if a.lugar else "")
            + ".",
            data.mensaje,
            "**Orden del día:**\n" + "\n".join(f"{p.orden}. {p.titulo}" for p in puntos),
            f"Si no puede asistir, puede otorgar poder por escrito a otra persona (máximo {a.max_poderes_por_apoderado} poderes por asistente)."
            + (
                " También puede asistir y votar desde la plataforma, en la sección Asambleas."
                if a.modalidad != ModalidadAsamblea.PRESENCIAL
                else ""
            ),
        ]
        if x
    )
    c = await circulares.crear(
        db,
        actor,
        CircularIn(
            titulo=f"Convocatoria: {a.titulo}",
            cuerpo=cuerpo,
            categoria=CategoriaCircular.CONVOCATORIA,
            importante=True,
            enviar_correo=data.enviar_correo,
        ),
    )
    await circulares.publicar(db, actor, c.id)
    a.circular_id = c.id
    await db.flush()
    return a, d.aviso_convocatoria(local.date(), hoy_bogota())


async def cancelar(db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID, data: CancelarIn) -> Asamblea:
    exigir(actor, d.PUEDE_GESTIONAR, "cancelar asambleas")
    a = await obtener(db, actor, asamblea_id)
    _exigir_estado(a, EA.PROGRAMADA)
    a.estado = EA.CANCELADA
    a.observaciones = f"Cancelada: {data.motivo}" + (f"\n{a.observaciones}" if a.observaciones else "")
    await db.flush()
    return a


# --- Apertura: padrón ------------------------------------------------------------------------


async def abrir(db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID, data: AbrirIn) -> Asamblea:
    """Fija el padrón (unidades con coeficiente y sus propietarios) y pone la asamblea en curso."""
    exigir(actor, d.PUEDE_GESTIONAR, "instalar la asamblea")
    a = await obtener(db, actor, asamblea_id)
    _exigir_estado(a, EA.PROGRAMADA)
    unidades = list(await db.scalars(select(Unit).where(Unit.activa.is_(True), Unit.coefficient.is_not(None))))
    if len(unidades) < 2:
        raise ValidacionError("Registre las unidades con su coeficiente antes de instalar la asamblea")
    filas = await db.execute(
        select(UnidadPersona.unidad_id, Persona.nombre_completo, Persona.user_id)
        .join(Persona, Persona.id == UnidadPersona.persona_id)
        .where(UnidadPersona.fecha_fin.is_(None), UnidadPersona.relacion == RelacionUnidad.PROPIETARIO)
    )
    propietarios: dict[uuid.UUID, list[tuple[str, uuid.UUID | None]]] = {}
    for uid, nombre, user in filas.all():
        propietarios.setdefault(uid, []).append((nombre, user))
    con_cartera = await db.get(CarteraConfig, actor.tenant_id) is not None
    hoy = hoy_bogota()
    total = Decimal(0)
    for u in unidades:
        prop = propietarios.get(u.id, [])
        al_dia = None
        if con_cartera:
            al_dia = (await cartera.saldo_unidad(db, u.id, vencido_a=hoy)) == 0
        db.add(
            PadronAsamblea(
                asamblea_id=a.id,
                unidad_id=u.id,
                tenant_id=actor.tenant_id,
                etiqueta=u.etiqueta,
                coeficiente=u.coefficient,
                propietarios=", ".join(n for n, _ in prop) or None,
                votante_user_ids=[usr for _, usr in prop if usr],
                al_dia=al_dia,
            )
        )
        total += u.coefficient or 0
    await db.flush()
    a.coeficiente_total = total
    a.presidente = data.presidente
    a.secretario = data.secretario
    a.abierta_at = datetime.now(UTC)
    a.estado = EA.EN_CURSO
    await db.flush()
    return a


# --- Asistencia y quórum ---------------------------------------------------------------------


async def quorum(db: AsyncSession, a: Asamblea) -> d.Quorum:
    presente, unidades = (
        await db.execute(
            select(func.coalesce(func.sum(PadronAsamblea.coeficiente), 0), func.count())
            .select_from(AsistenciaAsamblea)
            .join(
                PadronAsamblea,
                (PadronAsamblea.asamblea_id == AsistenciaAsamblea.asamblea_id)
                & (PadronAsamblea.unidad_id == AsistenciaAsamblea.unidad_id),
            )
            .where(AsistenciaAsamblea.asamblea_id == a.id, AsistenciaAsamblea.retiro_at.is_(None))
        )
    ).one()
    total_unidades = (
        await db.scalar(select(func.count()).select_from(PadronAsamblea).where(PadronAsamblea.asamblea_id == a.id)) or 0
    )
    return d.Quorum(Decimal(presente), a.coeficiente_total or Decimal(0), unidades, total_unidades, a.convocatoria)


async def _padron(db: AsyncSession, a: Asamblea, unidad_id: uuid.UUID) -> PadronAsamblea:
    p = await db.get(PadronAsamblea, (a.id, unidad_id))
    if p is None:
        raise ValidacionError("La unidad no está en el padrón de la asamblea (sin coeficiente o inactiva)")
    return p


async def _asistencia_vigente(db: AsyncSession, a: Asamblea, unidad_id: uuid.UUID) -> AsistenciaAsamblea | None:
    return await db.scalar(
        select(AsistenciaAsamblea).where(
            AsistenciaAsamblea.asamblea_id == a.id,
            AsistenciaAsamblea.unidad_id == unidad_id,
            AsistenciaAsamblea.retiro_at.is_(None),
        )
    )


async def registrar_asistencia(
    db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID, data: AsistenciaIn
) -> AsistenciaAsamblea:
    exigir(actor, d.PUEDE_REGISTRAR_ASISTENCIA, "registrar la asistencia")
    a = await obtener(db, actor, asamblea_id)
    _exigir_estado(a, EA.EN_CURSO)
    p = await _padron(db, a, data.unidad_id)
    if await _asistencia_vigente(db, a, data.unidad_id):
        raise ValidacionError(f"La unidad {p.etiqueta} ya está registrada como presente")
    documento = "".join(c for c in (data.asistente_documento or "") if c.isalnum()).upper() or None
    if data.tipo == TipoAsistente.APODERADO:
        poderes = await db.scalar(
            select(func.count())
            .select_from(AsistenciaAsamblea)
            .where(
                AsistenciaAsamblea.asamblea_id == a.id,
                AsistenciaAsamblea.retiro_at.is_(None),
                AsistenciaAsamblea.tipo == TipoAsistente.APODERADO,
                AsistenciaAsamblea.asistente_documento == documento,
            )
        )
        if (poderes or 0) >= a.max_poderes_por_apoderado:
            raise ValidacionError(
                f"{data.asistente_nombre} ya representa {poderes} unidad(es): el máximo es {a.max_poderes_por_apoderado} poderes"
            )
    x = AsistenciaAsamblea(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        asamblea_id=a.id,
        unidad_id=data.unidad_id,
        tipo=data.tipo,
        asistente_nombre=data.asistente_nombre,
        asistente_documento=documento,
        poder_soporte_key=data.poder_soporte_key,
        registrada_por_id=actor.user_id,
    )
    db.add(x)
    await db.flush()
    return x


async def _unidades_del_votante(db: AsyncSession, actor: Actor, a: Asamblea) -> list[PadronAsamblea]:
    return list(
        await db.scalars(
            select(PadronAsamblea).where(
                PadronAsamblea.asamblea_id == a.id,
                literal(actor.user_id, PGUUID(as_uuid=True)) == any_(PadronAsamblea.votante_user_ids),
            )
        )
    )


async def asistir_desde_portal(db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID) -> list[AsistenciaAsamblea]:
    """El propietario con cuenta se registra como presente (virtual) por todas sus unidades."""
    if actor.role != R.RESIDENTE:
        raise PermisoDenegado("Desde el portal asisten los propietarios")
    a = await obtener(db, actor, asamblea_id)
    _exigir_estado(a, EA.EN_CURSO)
    if a.modalidad == ModalidadAsamblea.PRESENCIAL:
        raise ValidacionError("Esta asamblea es presencial: regístrese en la mesa de entrada")
    mias = await _unidades_del_votante(db, actor, a)
    if not mias:
        raise ValidacionError("Su cuenta no figura como propietario en el padrón de esta asamblea")
    usuario = await db.get(User, actor.user_id)
    nuevas = []
    for p in mias:
        if await _asistencia_vigente(db, a, p.unidad_id):
            continue
        x = AsistenciaAsamblea(
            id=uuid.uuid4(),
            tenant_id=actor.tenant_id,
            asamblea_id=a.id,
            unidad_id=p.unidad_id,
            tipo=TipoAsistente.PROPIETARIO,
            asistente_nombre=(usuario.full_name.split(" (")[0] if usuario else "Propietario"),
            user_id=actor.user_id,
            virtual=True,
        )
        db.add(x)
        nuevas.append(x)
    await db.flush()
    return nuevas


async def retirar(db: AsyncSession, actor: Actor, asistencia_id: uuid.UUID) -> AsistenciaAsamblea:
    """Quien se retira deja de contar para el quórum (los votos ya emitidos se conservan)."""
    x = await db.get(AsistenciaAsamblea, asistencia_id)
    if x is None or x.tenant_id != actor.tenant_id:
        raise NoEncontrado("Asistencia no encontrada")
    if actor.role not in d.PUEDE_REGISTRAR_ASISTENCIA and x.user_id != actor.user_id:
        raise PermisoDenegado("Solo el personal o el propio asistente registran el retiro")
    if x.retiro_at is not None:
        raise ValidacionError("Ya se registró el retiro")
    x.retiro_at = datetime.now(UTC)
    await db.flush()
    return x


# --- Votaciones ------------------------------------------------------------------------------


async def abrir_votacion(db: AsyncSession, actor: Actor, punto_id: uuid.UUID) -> PuntoAsamblea:
    exigir(actor, d.PUEDE_GESTIONAR, "abrir votaciones")
    p = await punto(db, actor, punto_id)
    a = await obtener(db, actor, p.asamblea_id)
    _exigir_estado(a, EA.EN_CURSO)
    if p.tipo != TipoPunto.VOTACION:
        raise ValidacionError("Este punto es informativo: márquelo como tratado")
    if p.estado != EP.PENDIENTE:
        raise ValidacionError("La votación de este punto ya se abrió")
    otra = await db.scalar(
        select(PuntoAsamblea.titulo).where(PuntoAsamblea.asamblea_id == a.id, PuntoAsamblea.estado == EP.EN_VOTACION)
    )
    if otra:
        raise ValidacionError(f"Cierre primero la votación abierta: «{otra}»")
    q = await quorum(db, a)
    if not q.hay_quorum:
        raise ValidacionError(f"No se puede decidir sin quórum. {q.mensaje}")
    p.estado = EP.EN_VOTACION
    p.abierto_at = datetime.now(UTC)
    await db.flush()
    return p


def _validar_opcion(p: PuntoAsamblea, opcion: str) -> str:
    for o in p.opciones:
        if o.lower() == opcion.strip().lower():
            return o
    raise ValidacionError(f"Opción no válida. Opciones: {', '.join(p.opciones)}")


async def votar_en_sala(db: AsyncSession, actor: Actor, punto_id: uuid.UUID, data: VotoSalaIn) -> VotoAsamblea:
    """El personal registra el voto de una unidad presente (votación en la sala)."""
    exigir(actor, d.PUEDE_REGISTRAR_ASISTENCIA, "registrar votos")
    p = await punto(db, actor, punto_id)
    a = await obtener(db, actor, p.asamblea_id)
    return await _votar(db, actor, a, p, data.unidad_id, _validar_opcion(p, data.opcion), portal=False)


async def votar_desde_portal(
    db: AsyncSession, actor: Actor, punto_id: uuid.UUID, data: VotoPortalIn
) -> list[VotoAsamblea]:
    if actor.role != R.RESIDENTE:
        raise PermisoDenegado("Desde el portal votan los propietarios")
    p = await punto(db, actor, punto_id)
    a = await obtener(db, actor, p.asamblea_id)
    opcion = _validar_opcion(p, data.opcion)
    mias = [x for x in await _unidades_del_votante(db, actor, a) if data.unidad_id in (None, x.unidad_id)]
    if not mias:
        raise ValidacionError("No figura como propietario de esa unidad en el padrón")
    votos = []
    for x in mias:
        if not await _asistencia_vigente(db, a, x.unidad_id):
            continue
        votos.append(await _votar(db, actor, a, p, x.unidad_id, opcion, portal=True))
    if not votos:
        raise ValidacionError("Primero registre su asistencia a la asamblea")
    return votos


async def _votar(
    db: AsyncSession, actor: Actor, a: Asamblea, p: PuntoAsamblea, unidad_id: uuid.UUID, opcion: str, *, portal: bool
) -> VotoAsamblea:
    _exigir_estado(a, EA.EN_CURSO)
    if p.estado != EP.EN_VOTACION:
        raise ValidacionError("La votación de este punto no está abierta")
    padron = await _padron(db, a, unidad_id)
    if not await _asistencia_vigente(db, a, unidad_id):
        raise ValidacionError(f"La unidad {padron.etiqueta} no está registrada como presente")
    ya = await db.scalar(
        select(VotoAsamblea.opcion).where(VotoAsamblea.punto_id == p.id, VotoAsamblea.unidad_id == unidad_id)
    )
    if ya:
        raise ValidacionError(f"La unidad {padron.etiqueta} ya votó «{ya}» en este punto: el voto no se cambia")
    v = VotoAsamblea(
        id=uuid.uuid4(),
        tenant_id=actor.tenant_id,
        asamblea_id=a.id,
        punto_id=p.id,
        unidad_id=unidad_id,
        opcion=opcion,
        emitido_por_id=actor.user_id,
        desde_portal=portal,
    )
    db.add(v)
    await db.flush()
    return v


async def calcular_resultado(db: AsyncSession, a: Asamblea, p: PuntoAsamblea) -> d.Resultado:
    votos = [
        (o, Decimal(c))
        for o, c in (
            await db.execute(select(VotoAsamblea.opcion, VotoAsamblea.coeficiente).where(VotoAsamblea.punto_id == p.id))
        ).all()
    ]
    q = await quorum(db, a)
    presente = p.coeficiente_presente if p.estado == EP.CERRADO and p.coeficiente_presente is not None else q.presente
    return d.resultado(p.mayoria or MayoriaPunto.SIMPLE, p.opciones, votos, presente=presente, total=q.total)


async def cerrar_punto(db: AsyncSession, actor: Actor, punto_id: uuid.UUID) -> PuntoAsamblea:
    """Cierra la votación (y fija el resultado con el quórum de ese momento) o marca tratado un punto informativo."""
    exigir(actor, d.PUEDE_GESTIONAR, "cerrar puntos")
    p = await punto(db, actor, punto_id)
    a = await obtener(db, actor, p.asamblea_id)
    _exigir_estado(a, EA.EN_CURSO)
    if p.estado == EP.CERRADO:
        raise ValidacionError("El punto ya está cerrado")
    if p.tipo == TipoPunto.VOTACION:
        if p.estado != EP.EN_VOTACION:
            raise ValidacionError("Abra la votación antes de cerrarla")
        r = await calcular_resultado(db, a, p)
        p.coeficiente_presente = r.presente
        p.resultado = r.a_json()
        p.aprobado = r.aprobado
        if not p.conclusion:
            p.conclusion = r.explicacion
    p.estado = EP.CERRADO
    p.cerrado_at = datetime.now(UTC)
    await db.flush()
    return p


async def cerrar(db: AsyncSession, actor: Actor, asamblea_id: uuid.UUID, data: CerrarIn) -> Asamblea:
    exigir(actor, d.PUEDE_GESTIONAR, "cerrar la asamblea")
    a = await obtener(db, actor, asamblea_id)
    _exigir_estado(a, EA.EN_CURSO)
    abierta = await db.scalar(
        select(PuntoAsamblea.titulo).where(PuntoAsamblea.asamblea_id == a.id, PuntoAsamblea.estado == EP.EN_VOTACION)
    )
    if abierta:
        raise ValidacionError(f"Cierre primero la votación de «{abierta}»")
    await fijar_motivo(db, None)
    if data.observaciones:
        a.observaciones = data.observaciones
    a.estado = EA.CERRADA
    a.cerrada_at = datetime.now(UTC)
    await db.flush()
    return a
