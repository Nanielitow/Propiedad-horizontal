"""Datos de demostración de asambleas (Conjunto Residencial Los Pinos).

Con los MISMOS casos de uso que la API:
  - la asamblea ordinaria de marzo de 2026, CERRADA: padrón de las 50 unidades, asistencia
    del ~80 % de los coeficientes (con apoderados; Carlos Pérez asistió desde el portal),
    estados financieros y presupuesto (mayoría simple), la cuota extraordinaria de la
    impermeabilización (mayoría calificada del 70 %) y la elección del consejo;
  - la asamblea ordinaria de 2027, PROGRAMADA y enlazada a la convocatoria ya publicada
    como circular (demo del portal).

Las fechas que la base fija con now() se llevan a su fecha simulada al final, con la conexión
del dueño y sin triggers (solo para la demo).

Uso: python -m app.scripts.demo asambleas   (requiere `unidades`, `cartera` y `portal`; no repite)
"""

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import Asamblea, Circular, Membership, PadronAsamblea, PuntoAsamblea, Tenant, User
from app.models.enums import MayoriaPunto, ModalidadAsamblea, TipoAsistente, TipoPunto, UserRole
from app.schemas.asambleas import (
    AbrirIn,
    AsambleaIn,
    AsistenciaIn,
    CerrarIn,
    PuntoIn,
    PuntoUpdate,
    VotoPortalIn,
    VotoSalaIn,
)
from app.services.asambleas import servicio as s
from app.services.comun import TZ, ActorSimple

TENANT = "los-pinos"
rng = random.Random(675)  # noqa: S311 - datos de demo reproducibles
R = UserRole

PUNTOS_2026 = [
    PuntoIn(titulo="Verificación del quórum e instalación"),
    PuntoIn(titulo="Elección del presidente y secretario de la asamblea"),
    PuntoIn(titulo="Informe de gestión de la administración 2025", descripcion="La administradora presentó el informe de gestión, mantenimientos ejecutados y estado de la cartera."),
    PuntoIn(titulo="Aprobación de los estados financieros 2025", tipo=TipoPunto.VOTACION, mayoria=MayoriaPunto.SIMPLE),
    PuntoIn(titulo="Aprobación del presupuesto 2026", tipo=TipoPunto.VOTACION, mayoria=MayoriaPunto.SIMPLE, descripcion="Presupuesto de gastos de $504.000.000 anuales ($42.000.000 mensuales)."),
    PuntoIn(
        titulo="Cuota extraordinaria para la impermeabilización de cubiertas",
        tipo=TipoPunto.VOTACION,
        mayoria=MayoriaPunto.CALIFICADA_70,
        descripcion="$30.000.000 repartidos por coeficiente en tres cuotas mensuales (supera cuatro veces las expensas necesarias mensuales: art. 46 Ley 675).",
    ),
    PuntoIn(titulo="Elección del consejo de administración 2026-2027", tipo=TipoPunto.VOTACION, mayoria=MayoriaPunto.ELECCION, opciones=["Plancha 1 (Elena Vargas)", "Plancha 2 (Jorge Londoño)"]),
    PuntoIn(titulo="Proposiciones y varios"),
]  # fmt: skip

PUNTOS_2027 = [
    PuntoIn(titulo="Verificación del quórum e instalación"),
    PuntoIn(titulo="Elección del presidente y secretario de la asamblea"),
    PuntoIn(titulo="Informe de gestión 2026"),
    PuntoIn(titulo="Aprobación de los estados financieros 2026", tipo=TipoPunto.VOTACION),
    PuntoIn(titulo="Aprobación del presupuesto 2027", tipo=TipoPunto.VOTACION),
    PuntoIn(titulo="Elección del consejo de administración y del revisor fiscal", tipo=TipoPunto.VOTACION, mayoria=MayoriaPunto.ELECCION, opciones=["Plancha 1", "Plancha 2"]),
    PuntoIn(titulo="Proposiciones y varios"),
]  # fmt: skip

# Tendencia de voto por punto (probabilidad de cada opción)
TENDENCIA = {
    "Aprobación de los estados financieros 2025": [("Sí", 0.82), ("No", 0.08), ("Abstención", 0.10)],
    "Aprobación del presupuesto 2026": [("Sí", 0.70), ("No", 0.22), ("Abstención", 0.08)],
    "Cuota extraordinaria para la impermeabilización de cubiertas": [("Sí", 0.93), ("No", 0.05), ("Abstención", 0.02)],
    "Elección del consejo de administración 2026-2027": [
        ("Plancha 1 (Elena Vargas)", 0.62),
        ("Plancha 2 (Jorge Londoño)", 0.38),
    ],
}
CONCLUSIONES = {
    "Elección del presidente y secretario de la asamblea": "Se eligió por unanimidad a Elena Vargas como presidente y a Laura Gómez (administradora) como secretaria.",
    "Informe de gestión de la administración 2025": "La asamblea recibió el informe. Se solicitó publicar el plan de mantenimiento 2026 en la plataforma.",
    "Proposiciones y varios": "Se propuso instalar un bicicletero cubierto; el consejo evaluará cotizaciones.",
}


async def generar() -> None:
    async with SessionLocal() as db:
        tenant_id = await db.scalar(select(Tenant.id).where(Tenant.slug == TENANT))
        if tenant_id is None:
            raise SystemExit("No existe la copropiedad de demo: ejecute primero python -m app.scripts.seed")
        await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
        if await db.scalar(select(func.count()).select_from(Asamblea)):
            print("Ya hay asambleas en la demo: no se generan de nuevo.")
            return
        correos = {
            "admin": "admin@lospinos.demo",
            "recepcion": "recepcion@lospinos.demo",
            "residente": "residente@lospinos.demo",
        }
        u = {k: await db.scalar(select(User.id).where(User.email == v)) for k, v in correos.items()}
        miembros = set(await db.scalars(select(Membership.user_id).where(Membership.tenant_id == tenant_id)))
        if None in u.values() or not set(u.values()) <= miembros:
            raise SystemExit("Faltan usuarios de la demo: ejecute python -m app.scripts.seed")
        admin = ActorSimple(tenant_id, u["admin"], R.ADMIN)  # type: ignore[arg-type]
        aux = ActorSimple(tenant_id, u["recepcion"], R.AUXILIAR)  # type: ignore[arg-type]
        carlos = ActorSimple(tenant_id, u["residente"], R.RESIDENTE)  # type: ignore[arg-type]

        async def como(a: ActorSimple) -> ActorSimple:
            await set_rls_context(db, tenant_id=tenant_id, user_id=a.user_id, role=a.role.value)
            return a

        # --- Asamblea de marzo de 2026 (cerrada) ---------------------------------------------
        fecha_2026 = datetime(2026, 3, 14, 8, 0, tzinfo=TZ)
        await como(admin)
        a = await s.crear(
            db, admin,
            AsambleaIn(titulo="Asamblea general ordinaria 2026", modalidad=ModalidadAsamblea.MIXTA, fecha_hora=fecha_2026, lugar="Salón social", puntos=PUNTOS_2026),
        )  # fmt: skip
        await s.abrir(db, admin, a.id, AbrirIn(presidente="Elena Vargas", secretario="Laura Gómez"))
        padron = list(await db.scalars(select(PadronAsamblea).where(PadronAsamblea.asamblea_id == a.id)))
        # Carlos asiste desde el portal; los demás en la sala (algunos con poder)
        await como(carlos)
        await s.asistir_desde_portal(db, carlos, a.id)
        await como(aux)
        apoderados = ["79.345.120", "52.880.411", "1.020.455.789"]
        nombres_apoderados = ["Mauricio Botero", "Claudia Arango", "Sebastián Quintero"]
        poderes = dict.fromkeys(apoderados, 0)
        asistentes: list[uuid.UUID] = []
        for p in padron:
            if carlos.user_id in (p.votante_user_ids or []):
                asistentes.append(p.unidad_id)
                continue
            if rng.random() > 0.80:
                continue
            libres = [d for d in apoderados if poderes[d] < 2]
            if libres and rng.random() < 0.12:
                doc = rng.choice(libres)
                poderes[doc] += 1
                await s.registrar_asistencia(
                    db, aux, a.id,
                    AsistenciaIn(unidad_id=p.unidad_id, tipo=TipoAsistente.APODERADO, asistente_nombre=nombres_apoderados[apoderados.index(doc)], asistente_documento=doc),
                )  # fmt: skip
            else:
                nombre = (p.propietarios or "Propietario").split(",")[0].strip()
                await s.registrar_asistencia(
                    db, aux, a.id, AsistenciaIn(unidad_id=p.unidad_id, asistente_nombre=nombre)
                )
            asistentes.append(p.unidad_id)

        puntos = list(
            await db.scalars(
                select(PuntoAsamblea).where(PuntoAsamblea.asamblea_id == a.id).order_by(PuntoAsamblea.orden)
            )
        )
        for pt in puntos:
            await como(admin)
            if pt.tipo == TipoPunto.INFORMATIVO:
                if pt.titulo in CONCLUSIONES:
                    await s.editar_punto(db, admin, pt.id, PuntoUpdate(conclusion=CONCLUSIONES[pt.titulo]))
                await s.cerrar_punto(db, admin, pt.id)
                continue
            await s.abrir_votacion(db, admin, pt.id)
            opciones, pesos = zip(*TENDENCIA[pt.titulo], strict=True)
            for uid in asistentes:
                opcion = rng.choices(opciones, pesos)[0]
                p = next(x for x in padron if x.unidad_id == uid)
                if carlos.user_id in (p.votante_user_ids or []):
                    await como(carlos)
                    await s.votar_desde_portal(
                        db, carlos, pt.id, VotoPortalIn(opcion=opcion if "Plancha" not in opcion else opciones[0])
                    )
                    await como(aux)
                else:
                    await como(aux)
                    await s.votar_en_sala(db, aux, pt.id, VotoSalaIn(unidad_id=uid, opcion=opcion))
            await como(admin)
            await s.cerrar_punto(db, admin, pt.id)
        await s.cerrar(
            db,
            admin,
            a.id,
            CerrarIn(observaciones="El acta será revisada por la comisión verificadora designada por la asamblea."),
        )
        cerrada_id = a.id

        # --- Asamblea de 2027 (programada, convocada con la circular del portal) -------------------
        fecha_2027 = datetime(2027, 3, 13, 8, 0, tzinfo=TZ)
        b = await s.crear(
            db, admin,
            AsambleaIn(titulo="Asamblea general ordinaria 2027", modalidad=ModalidadAsamblea.MIXTA, fecha_hora=fecha_2027, lugar="Salón social", puntos=PUNTOS_2027),
        )  # fmt: skip
        circular = await db.scalar(
            select(Circular.id).where(Circular.titulo.ilike("%asamblea general ordinaria 2027%"))
        )
        if circular:
            b.circular_id = circular
        await db.commit()

    _ajustar_fechas(cerrada_id, fecha_2026)
    print("Asambleas de demo: ordinaria 2026 cerrada con votaciones; ordinaria 2027 programada y convocada.")


def _ajustar_fechas(asamblea_id: uuid.UUID, inicio: datetime) -> None:
    from app.services.demo import _owner_engine

    t0 = inicio.astimezone(UTC) + timedelta(minutes=20)
    with _owner_engine().begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(
            text(
                "UPDATE asambleas SET created_at = :c, abierta_at = :a, cerrada_at = :z, updated_at = :z WHERE id = :id"
            ),
            {"c": inicio - timedelta(days=25), "a": t0, "z": t0 + timedelta(hours=4, minutes=15), "id": asamblea_id},
        )
        conn.execute(
            text(
                "WITH x AS (SELECT id, row_number() OVER (ORDER BY llegada_at) AS n FROM asamblea_asistencias WHERE asamblea_id = :id)"
                " UPDATE asamblea_asistencias a SET llegada_at = :t - interval '25 minutes' + (x.n * interval '40 seconds') FROM x WHERE a.id = x.id"
            ),
            {"t": t0, "id": asamblea_id},
        )
        conn.execute(
            text(
                "WITH x AS (SELECT id, orden FROM asamblea_puntos WHERE asamblea_id = :id)"
                " UPDATE asamblea_puntos p SET abierto_at = CASE WHEN abierto_at IS NULL THEN NULL ELSE :t + (x.orden * interval '28 minutes') END,"
                " cerrado_at = :t + (x.orden * interval '28 minutes') + interval '12 minutes' FROM x WHERE p.id = x.id"
            ),
            {"t": t0, "id": asamblea_id},
        )
        conn.execute(
            text(
                "UPDATE asamblea_votos v SET created_at = p.abierto_at + interval '3 minutes'"
                " FROM asamblea_puntos p WHERE v.punto_id = p.id AND v.asamblea_id = :id"
            ),
            {"id": asamblea_id},
        )


def main() -> None:
    asyncio.run(generar())
