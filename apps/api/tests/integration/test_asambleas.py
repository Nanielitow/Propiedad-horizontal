"""Fase 1 de asambleas: padrón, asistencia con poderes, quórum, votaciones y reglas de la base."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import Circular, PadronAsamblea
from app.models.enums import (
    ConvocatoriaAsamblea,
    EstadoAsamblea,
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
    AsistenciaIn,
    CerrarIn,
    ConvocarIn,
    PuntoIn,
    VotoPortalIn,
    VotoSalaIn,
)
from app.schemas.unidades import PersonaIn, UnidadIn, VinculoIn
from app.services.asambleas import servicio as s
from app.services.comun import ValidacionError
from app.services.unidades import gestion
from tests.integration.conftest import Mundo

A = UserRole.ADMIN
AUX = UserRole.AUXILIAR
D = Decimal


@pytest.fixture
async def conjunto(mundo: Mundo) -> dict[str, uuid.UUID]:
    """Cinco unidades: 101 (30 %, propietaria con cuenta), 102 (25 %), 103 (20 %), 104 (15 %), 105 (10 %)."""
    await mundo.usuario("ANA", "RESIDENTE")
    admin = await mundo.como(A)
    ids = {}
    for numero, coef in (("101", "30"), ("102", "25"), ("103", "20"), ("104", "15"), ("105", "10")):
        u = await gestion.crear_unidad(mundo.db, admin, UnidadIn(tower="1", number=numero, coefficient=D(coef)))
        ids[numero] = u.id
        persona = PersonaIn(
            nombre_completo=f"Propietario {numero}", user_id=mundo.usuarios["ANA"] if numero == "101" else None
        )
        await gestion.vincular(mundo.db, admin, u.id, VinculoIn(persona=persona, relacion=RelacionUnidad.PROPIETARIO))
    return ids


async def _asamblea(m: Mundo, **extra: object) -> uuid.UUID:
    admin = await m.como(A)
    a = await s.crear(
        m.db,
        admin,
        AsambleaIn(
            titulo="Asamblea ordinaria 2027",
            fecha_hora=datetime.now(UTC) + timedelta(days=20),
            modalidad=extra.pop("modalidad", ModalidadAsamblea.MIXTA),  # type: ignore[arg-type]
            puntos=[
                PuntoIn(titulo="Verificación del quórum"),
                PuntoIn(titulo="Aprobación del presupuesto 2027", tipo=TipoPunto.VOTACION),
                PuntoIn(titulo="Reforma del reglamento", tipo=TipoPunto.VOTACION, mayoria=MayoriaPunto.CALIFICADA_70),
                PuntoIn(
                    titulo="Elección del consejo",
                    tipo=TipoPunto.VOTACION,
                    mayoria=MayoriaPunto.ELECCION,
                    opciones=["Plancha 1", "Plancha 2"],
                ),
            ],
            **extra,  # type: ignore[arg-type]
        ),
    )
    return a.id


async def _asistir(m: Mundo, aid: uuid.UUID, unidad: uuid.UUID, nombre: str = "Asistente", **extra: object) -> None:
    aux = await m.como(AUX)
    await s.registrar_asistencia(m.db, aux, aid, AsistenciaIn(unidad_id=unidad, asistente_nombre=nombre, **extra))  # type: ignore[arg-type]


async def _puntos(m: Mundo, aid: uuid.UUID) -> list:  # type: ignore[type-arg]
    from app.models import PuntoAsamblea

    return list(
        await m.db.scalars(select(PuntoAsamblea).where(PuntoAsamblea.asamblea_id == aid).order_by(PuntoAsamblea.orden))
    )


async def test_convocar_y_abrir_con_padron(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    aid = await _asamblea(mundo)
    admin = await mundo.como(A)
    a, aviso = await s.convocar(mundo.db, admin, aid, ConvocarIn(enviar_correo=False))
    assert aviso is None  # 20 días de anticipación
    c = await mundo.db.get(Circular, a.circular_id)
    assert c is not None and c.importante and "Elección del consejo" in c.cuerpo
    a = await s.abrir(mundo.db, admin, aid, AbrirIn(presidente="Elena Vargas", secretario="Laura Gómez"))
    assert a.estado == EstadoAsamblea.EN_CURSO and a.coeficiente_total == D("100")
    padron = {
        p.etiqueta: p for p in await mundo.db.scalars(select(PadronAsamblea).where(PadronAsamblea.asamblea_id == aid))
    }
    assert len(padron) == 5 and padron["1-101"].votante_user_ids == [mundo.usuarios["ANA"]]
    # El padrón queda fijo: no entra otra unidad aunque se cree después
    async with mundo.db.begin_nested():
        u = await gestion.crear_unidad(mundo.db, admin, UnidadIn(tower="1", number="106", coefficient=D("5")))
    with pytest.raises(DBAPIError, match="padrón ya está fijado"):
        async with mundo.db.begin_nested():
            mundo.db.add(
                PadronAsamblea(
                    asamblea_id=aid, unidad_id=u.id, tenant_id=mundo.tenant, etiqueta="1-106", coeficiente=D("5")
                )
            )
            await mundo.db.flush()


async def test_quorum_poderes_y_votacion_simple(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    aid = await _asamblea(mundo)
    admin = await mundo.como(A)
    a = await s.abrir(mundo.db, admin, aid, AbrirIn(presidente="Elena Vargas", secretario="Laura Gómez"))
    _, presupuesto, reforma, eleccion = await _puntos(mundo, aid)

    await _asistir(mundo, aid, conjunto["102"], "Propietario 102")
    await _asistir(mundo, aid, conjunto["103"], "Propietario 103")
    admin = await mundo.como(A)
    with pytest.raises(ValidacionError, match="sin quórum"):
        await s.abrir_votacion(mundo.db, admin, presupuesto.id)  # 45 % presente
    # Un apoderado con dos poderes; el tercero se rechaza
    await _asistir(
        mundo, aid, conjunto["104"], "Pedro Apoderado", tipo=TipoAsistente.APODERADO, asistente_documento="79.111.222"
    )
    await _asistir(
        mundo, aid, conjunto["105"], "Pedro Apoderado", tipo=TipoAsistente.APODERADO, asistente_documento="79111222"
    )
    with pytest.raises(ValidacionError, match="máximo es 2 poderes"):
        await _asistir(
            mundo, aid, conjunto["101"], "Pedro Apoderado", tipo=TipoAsistente.APODERADO, asistente_documento="79111222"
        )
    with pytest.raises(ValidacionError, match="ya está registrada"):
        await _asistir(mundo, aid, conjunto["102"], "Otra persona")
    q = await s.quorum(mundo.db, a)
    assert q.hay_quorum and q.presente == D("70") and q.unidades_presentes == 4

    admin = await mundo.como(A)
    await s.abrir_votacion(mundo.db, admin, presupuesto.id)
    with pytest.raises(ValidacionError, match="Cierre primero"):
        await s.abrir_votacion(mundo.db, admin, reforma.id)  # una votación a la vez
    aux = await mundo.como(AUX)
    for numero, opcion in (("102", "sí"), ("103", "No"), ("104", "Sí"), ("105", "Abstención")):
        await s.votar_en_sala(mundo.db, aux, presupuesto.id, VotoSalaIn(unidad_id=conjunto[numero], opcion=opcion))
    with pytest.raises(ValidacionError, match="no se cambia"):
        await s.votar_en_sala(mundo.db, aux, presupuesto.id, VotoSalaIn(unidad_id=conjunto["102"], opcion="No"))
    with pytest.raises(ValidacionError, match="no está registrada como presente"):
        await s.votar_en_sala(mundo.db, aux, presupuesto.id, VotoSalaIn(unidad_id=conjunto["101"], opcion="Sí"))
    admin = await mundo.como(A)
    p = await s.cerrar_punto(mundo.db, admin, presupuesto.id)
    # Sí = 25 + 15 = 40 de 70 presentes (> 35): aprobado
    assert p.aprobado is True and p.resultado and p.resultado["por_opcion"]["Sí"] == "40.0000"

    # Reforma: aunque todos los presentes voten sí (70 %), el umbral es 70 del total: aprueba justo
    await s.abrir_votacion(mundo.db, admin, reforma.id)
    aux = await mundo.como(AUX)
    for numero in ("102", "103", "104"):
        await s.votar_en_sala(mundo.db, aux, reforma.id, VotoSalaIn(unidad_id=conjunto[numero], opcion="Sí"))
    admin = await mundo.como(A)
    r = await s.cerrar_punto(mundo.db, admin, reforma.id)
    assert r.aprobado is False  # 60 % del conjunto < 70 %
    del eleccion


async def test_voto_desde_el_portal(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    aid = await _asamblea(mundo, convocatoria=ConvocatoriaAsamblea.SEGUNDA)
    admin = await mundo.como(A)
    await s.abrir(mundo.db, admin, aid, AbrirIn(presidente="Elena Vargas", secretario="Laura Gómez"))
    _, presupuesto, _, eleccion = await _puntos(mundo, aid)
    ana = await mundo.como(UserRole.RESIDENTE, "ANA")
    with pytest.raises(ValidacionError):
        await s.votar_desde_portal(mundo.db, ana, eleccion.id, VotoPortalIn(opcion="Plancha 1"))  # no está abierta
    nuevas = await s.asistir_desde_portal(mundo.db, ana, aid)
    assert [x.virtual for x in nuevas] == [True]
    await _asistir(mundo, aid, conjunto["105"], "Propietario 105")  # segunda convocatoria: dos unidades bastan
    admin = await mundo.como(A)
    await s.abrir_votacion(mundo.db, admin, eleccion.id)
    ana = await mundo.como(UserRole.RESIDENTE, "ANA")
    votos = await s.votar_desde_portal(mundo.db, ana, eleccion.id, VotoPortalIn(opcion="plancha 1"))
    assert [(v.opcion, v.coeficiente, v.desde_portal) for v in votos] == [("Plancha 1", D("30.0000"), True)]
    aux = await mundo.como(AUX)
    await s.votar_en_sala(mundo.db, aux, eleccion.id, VotoSalaIn(unidad_id=conjunto["105"], opcion="Plancha 2"))
    admin = await mundo.como(A)
    p = await s.cerrar_punto(mundo.db, admin, eleccion.id)
    assert p.resultado and p.resultado["ganador"] == "Plancha 1"
    del presupuesto


async def test_cierre_e_inmutabilidad(mundo: Mundo, conjunto: dict[str, uuid.UUID]) -> None:
    aid = await _asamblea(mundo, modalidad=ModalidadAsamblea.PRESENCIAL)
    admin = await mundo.como(A)
    await s.abrir(mundo.db, admin, aid, AbrirIn(presidente="Elena Vargas", secretario="Laura Gómez"))
    ana = await mundo.como(UserRole.RESIDENTE, "ANA")
    with pytest.raises(ValidacionError, match="presencial"):
        await s.asistir_desde_portal(mundo.db, ana, aid)
    for numero in ("101", "102", "103"):
        await _asistir(mundo, aid, conjunto[numero])
    admin = await mundo.como(A)
    verificacion, presupuesto, _, _ = await _puntos(mundo, aid)
    await s.cerrar_punto(mundo.db, admin, verificacion.id)  # informativo: queda tratado
    await s.abrir_votacion(mundo.db, admin, presupuesto.id)
    with pytest.raises(ValidacionError, match="Cierre primero la votación"):
        await s.cerrar(mundo.db, admin, aid, CerrarIn())
    await s.cerrar_punto(mundo.db, admin, presupuesto.id)
    a = await s.cerrar(mundo.db, admin, aid, CerrarIn(observaciones="Se levantó la sesión a las 12:40 p. m."))
    assert a.estado == EstadoAsamblea.CERRADA and a.cerrada_at
    with pytest.raises(DBAPIError, match="no se modifica"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(
                text("UPDATE asambleas SET titulo = 'Otro título distinto' WHERE id = :id"), {"id": aid}
            )
    with pytest.raises(DBAPIError, match="permission denied|No se permite eliminar"):
        async with mundo.db.begin_nested():
            await mundo.db.execute(text("DELETE FROM asamblea_votos WHERE asamblea_id = :id"), {"id": aid})
