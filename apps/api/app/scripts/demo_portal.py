"""Datos de demostración del portal del residente (Conjunto Residencial Los Pinos).

Con los MISMOS casos de uso que la API:
  - reglas de las zonas sociales (salón con aprobación y paz y salvo; BBQ con aprobación
    automática) y una cancha múltiple sin costo;
  - 14 PQRS de los últimos tres meses en todos los estados: radicadas por Carlos Pérez
    desde el portal y por recepción a nombre de otros residentes (presencial, correo,
    teléfono), con notas internas, respuestas, calificaciones, dos vencidas y una
    convertida en novedad de mantenimiento;
  - 6 circulares publicadas (una importante: convocatoria a asamblea) y un borrador;
  - reservas de Carlos: una confirmada, una solicitada esperando aprobación.

Las fechas que la base fija con now() (radicación, mensajes, publicación) se llevan a su
fecha simulada al final, con la conexión del dueño y sin triggers (solo para la demo).

Uso: python -m app.scripts.demo portal   (requiere `unidades` y `activos`; no repite)
"""

import asyncio
import uuid
from datetime import datetime, time, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import Activo, Membership, Pqrs, Tenant, Unit, User, ZonaSocial
from app.models.enums import CanalPqrs, CategoriaCircular, CategoriaPqrs, EstadoPqrs, PrioridadPqrs, TipoPqrs, UserRole
from app.schemas.portal import (
    CalificacionIn,
    CircularIn,
    GestionPqrsIn,
    MensajeIn,
    NovedadDesdePqrsIn,
    PqrsIn,
    ReglasZonaIn,
    ReservaPortalIn,
    RespuestaIn,
)
from app.schemas.recaudos import ZonaCreate
from app.services.comun import TZ, ActorSimple, hoy_bogota
from app.services.portal import circulares, pqrs, reservas
from app.services.portal.dominio import sumar_dias_habiles
from app.services.recaudos import catalogos

TENANT = "los-pinos"
R = UserRole

# (días atrás, canal, a nombre de, unidad, tipo, categoría, asunto, descripción, desenlace)
PQRS = [
    (88, "PORTAL", None, "1-502", TipoPqrs.PETICION, CategoriaPqrs.ADMINISTRACION, "Copia del reglamento de propiedad horizontal",
     "Solicito copia digital del reglamento vigente y del manual de convivencia.", "calificada:5"),
    (75, "PRESENCIAL", "Gloria Restrepo", "2-304", TipoPqrs.QUEJA, CategoriaPqrs.CONVIVENCIA, "Perro sin correa en zonas comunes",
     "El residente del 2-404 pasea su perro sin correa por el sendero y el parque infantil.", "calificada:4"),
    (70, "CORREO", "Hernando Castro", "1-203", TipoPqrs.RECLAMO, CategoriaPqrs.CARTERA, "Cobro doble de la cuota de agosto",
     "En el estado de cuenta aparece dos veces la cuota de agosto. Adjunto el comprobante de pago.", "cerrada"),
    (62, "TELEFONO", "Mónica Salazar", "2-102", TipoPqrs.RECLAMO, CategoriaPqrs.MANTENIMIENTO, "Filtración en el techo del baño",
     "Desde las lluvias de la semana pasada hay una mancha de humedad que crece en el techo del baño.", "novedad"),
    (55, "PORTAL", None, "1-502", TipoPqrs.SUGERENCIA, CategoriaPqrs.ZONAS_COMUNES, "Bicicletero en el parqueadero de visitantes",
     "Sugiero instalar un bicicletero cubierto: varios residentes usan bicicleta y no hay dónde dejarlas.", "calificada:3"),
    (48, "PRESENCIAL", "Andrés Rubio", "1-104", TipoPqrs.QUEJA, CategoriaPqrs.SEGURIDAD, "Portería no anuncia domicilios",
     "En la noche dejan subir domiciliarios sin anunciarlos por citófono.", "respondida"),
    (40, "CORREO", "Patricia Ospina", "2-301", TipoPqrs.PETICION, CategoriaPqrs.PARQUEADEROS, "Cambio de parqueadero asignado",
     "Solicito cambiar mi parqueadero por uno cubierto; estoy dispuesta a pagar la diferencia.", "desistida"),
    (33, "TELEFONO", "Jorge Londoño", "1-401", TipoPqrs.QUEJA, CategoriaPqrs.ASEO, "Shut de basuras con malos olores",
     "El shut de la torre 1 huele mal desde hace días; parece que no lo están lavando.", "vencida"),
    (29, "PORTAL", None, "1-502", TipoPqrs.FELICITACION, CategoriaPqrs.ASEO, "Excelente trabajo en la poda de jardines",
     "Felicitaciones al equipo de mantenimiento por el arreglo de los jardines de la entrada.", "calificada:5"),
    (22, "PRESENCIAL", "Natalia Gutiérrez", "2-203", TipoPqrs.QUEJA, CategoriaPqrs.CONVIVENCIA, "Ruido de obra fuera del horario",
     "En el 2-303 hacen remodelación los domingos desde las 7 de la mañana.", "vencida"),
    (12, "CORREO", "Ricardo Mejía", "2-501", TipoPqrs.PETICION, CategoriaPqrs.CARTERA, "Acuerdo de pago de la deuda",
     "Solicito un acuerdo de pago en seis cuotas para ponerme al día con la administración.", "tramite"),
    (6, "PORTAL", None, "1-502", TipoPqrs.RECLAMO, CategoriaPqrs.ZONAS_COMUNES, "Máquina del gimnasio dañada",
     "La caminadora del gimnasio se detiene a los pocos minutos de uso.", "tramite"),
    (3, "PRESENCIAL", "Liliana Torres", "1-304", TipoPqrs.PETICION, CategoriaPqrs.ADMINISTRACION, "Certificado de residencia",
     "Necesito un certificado de residencia para un trámite bancario.", "radicada"),
    (1, "TELEFONO", "Óscar Zapata", "2-404", TipoPqrs.QUEJA, CategoriaPqrs.SEGURIDAD, "Puerta vehicular queda abierta",
     "La puerta del sótano se queda abierta varios minutos después de que entra un carro.", "radicada"),
]  # fmt: skip

RESPUESTAS = {
    CategoriaPqrs.ADMINISTRACION: "Le enviamos el documento solicitado a su correo. Quedamos atentos a cualquier inquietud.",
    CategoriaPqrs.CONVIVENCIA: "Se envió comunicación escrita al residente recordando el manual de convivencia. Si se repite, se aplicará la sanción prevista.",
    CategoriaPqrs.CARTERA: "Revisamos el estado de cuenta: el cargo duplicado fue corregido y su saldo quedó al día.",
    CategoriaPqrs.ZONAS_COMUNES: "Gracias por su aporte. La propuesta se presentará al consejo en la próxima reunión.",
    CategoriaPqrs.SEGURIDAD: "Se dio la instrucción al supervisor de la empresa de vigilancia y se reforzará en la próxima capacitación.",
    CategoriaPqrs.ASEO: "Muchas gracias por su mensaje; se lo transmitimos al equipo.",
}

CIRCULARES = [
    (60, CategoriaCircular.CARTERA, False, [], "Recordatorio: descuento por pronto pago",
     "Les recordamos que quienes paguen la cuota de administración **antes del día 5** de cada mes reciben un **5 % de descuento**.\n\nPueden pagar por transferencia a la cuenta de ahorros 123-456789-01 de Bancolombia e informar el pago en la plataforma."),
    (45, CategoriaCircular.CONVIVENCIA, False, [], "Tenencia responsable de mascotas",
     "Recordamos que en las zonas comunes las mascotas deben ir **con correa** y los dueños deben recoger sus excrementos (Ley 746 de 2002 y manual de convivencia, capítulo 6)."),
    (30, CategoriaCircular.MANTENIMIENTO, False, [], "Fumigación de zonas comunes",
     "El sábado se realizará la fumigación semestral de zonas comunes, shuts y sótanos de **8:00 a 11:00 a. m.**\n\nPor favor mantengan a niños y mascotas dentro de los apartamentos durante ese horario."),
    (18, CategoriaCircular.SERVICIOS, True, ["2"], "Corte de agua en la torre 2",
     "Por el cambio de la válvula principal, el **jueves** no habrá servicio de agua en la torre 2 de **8:00 a. m. a 2:00 p. m.**\n\nRecomendamos almacenar agua el día anterior."),
    (9, CategoriaCircular.SEGURIDAD, False, [], "Nuevo protocolo de domicilios",
     "A partir del lunes, todos los domicilios se recibirán en portería. Ningún domiciliario podrá subir a los apartamentos sin anuncio previo por citófono."),
    (4, CategoriaCircular.CONVOCATORIA, True, [], "Convocatoria a la asamblea general ordinaria 2027",
     "Se convoca a todos los copropietarios a la **asamblea general ordinaria** el sábado 13 de marzo de 2027 a las 8:00 a. m. en el salón social.\n\n**Orden del día:** verificación del quórum, informe de gestión, estados financieros 2026, presupuesto 2027, elección del consejo de administración y del revisor fiscal.\n\nSi no puede asistir, puede otorgar poder a otra persona (máximo dos poderes por asistente)."),
]  # fmt: skip


class Demo:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID, usuarios: dict[str, uuid.UUID]) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.u = usuarios
        self.hoy = hoy_bogota()
        self.fechas: dict[uuid.UUID, int] = {}  # pqrs -> días atrás
        self.fechas_circular: dict[uuid.UUID, int] = {}

    async def como(self, clave: str, rol: UserRole) -> ActorSimple:
        await set_rls_context(self.db, tenant_id=self.tenant_id, user_id=self.u[clave], role=rol.value)
        return ActorSimple(self.tenant_id, self.u[clave], rol)

    async def unidad(self, etiqueta: str) -> uuid.UUID | None:
        torre, numero = etiqueta.split("-")
        return await self.db.scalar(select(Unit.id).where(Unit.tower == torre, Unit.number == numero))

    async def zonas(self) -> dict[str, uuid.UUID]:
        admin = await self.como("admin", R.ADMIN)
        existentes = {z.nombre: z.id for z in await self.db.scalars(select(ZonaSocial))}
        if "Cancha múltiple" not in existentes:
            z = await catalogos.crear_zona(self.db, admin, ZonaCreate(nombre="Cancha múltiple"))
            existentes["Cancha múltiple"] = z.id
        reglas = {
            "Salón social": ReglasZonaIn(descripcion="Salón para 60 personas con cocineta, mesas y sillas.", capacidad=60,
                                         reglas="Música hasta las 11 p. m. La entrega se hace con inventario. Se cobra el aseo.",
                                         hora_apertura=time(9), hora_cierre=time(23), anticipacion_min_dias=3,
                                         max_reservas_mes_unidad=1, requiere_paz_y_salvo=True, requiere_aprobacion=True),
            "Zona BBQ": ReglasZonaIn(descripcion="Kiosko con asador a carbón y dos mesas.", capacidad=20,
                                     reglas="Traer el carbón. Dejar el asador limpio.", hora_apertura=time(10), hora_cierre=time(21),
                                     anticipacion_min_dias=1, max_reservas_mes_unidad=2, requiere_paz_y_salvo=False, requiere_aprobacion=False),
            "Cancha múltiple": ReglasZonaIn(descripcion="Cancha de microfútbol y baloncesto.", capacidad=24, hora_apertura=time(7),
                                            hora_cierre=time(21), anticipacion_min_dias=0, anticipacion_max_dias=14,
                                            max_reservas_mes_unidad=4, requiere_paz_y_salvo=False, requiere_aprobacion=False),
        }  # fmt: skip
        for nombre, r in reglas.items():
            if nombre in existentes:
                await reservas.configurar_zona(self.db, admin, existentes[nombre], r)
        return existentes

    async def pqrs(self) -> None:
        tecnico_activo = await self.db.scalar(
            select(Activo.id).where(Activo.nombre.ilike("%cubierta%")).limit(1)
        ) or await self.db.scalar(select(Activo.id).limit(1))
        for dias, canal, a_nombre, etiqueta, tipo, categoria, asunto, descripcion, desenlace in PQRS:
            unidad = await self.unidad(etiqueta)
            if canal == "PORTAL":
                actor = await self.como("residente", R.RESIDENTE)
                p = await pqrs.radicar(
                    self.db,
                    actor,
                    PqrsIn(tipo=tipo, categoria=categoria, asunto=asunto, descripcion=descripcion, unidad_id=unidad),
                )
            else:
                actor = await self.como("recepcion", R.AUXILIAR)
                p = await pqrs.radicar(
                    self.db,
                    actor,
                    PqrsIn(
                        tipo=tipo, categoria=categoria, asunto=asunto, descripcion=descripcion, unidad_id=unidad,
                        canal=CanalPqrs(canal), solicitante_nombre=a_nombre, solicitante_contacto=f"{a_nombre.split()[0].lower()}@correo.demo",
                        prioridad=PrioridadPqrs.ALTA if categoria in (CategoriaPqrs.SEGURIDAD, CategoriaPqrs.MANTENIMIENTO) else None,
                    ),
                )  # fmt: skip
            self.fechas[p.id] = dias
            await self._desenlace(p, desenlace, canal, categoria, tecnico_activo)

    async def _desenlace(
        self, p: Pqrs, desenlace: str, canal: str, categoria: CategoriaPqrs, activo: uuid.UUID | None
    ) -> None:
        if desenlace == "radicada":
            return
        aux = await self.como("recepcion", R.AUXILIAR)
        if categoria == CategoriaPqrs.CARTERA:
            await pqrs.gestionar(self.db, aux, p.id, GestionPqrsIn(asignado_a_id=self.u["contabilidad"]))
            actor = await self.como("contabilidad", R.CONTABILIDAD)
        else:
            actor = aux
        await pqrs.comentar(
            self.db, actor, p.id, MensajeIn(texto="Revisado con el supervisor; se programa la atención.", interno=True)
        )
        if desenlace in ("tramite", "vencida"):
            await pqrs.comentar(self.db, actor, p.id, MensajeIn(texto="Recibimos su solicitud y la estamos revisando."))
            return
        if desenlace == "desistida":
            await pqrs.desistir(self.db, aux, p.id, "La residente informó que ya no necesita el cambio")
            return
        if desenlace == "novedad" and activo:
            admin = await self.como("admin", R.ADMIN)
            await pqrs.convertir_en_novedad(
                self.db, admin, p.id, NovedadDesdePqrsIn(activo_id=activo, prioridad="ALTA")
            )
            await pqrs.responder(
                self.db, admin, p.id,
                RespuestaIn(texto="Se programó la impermeabilización del sector de la cubierta afectado. El contratista visitará su apartamento esta semana."),
            )  # fmt: skip
            return
        await pqrs.responder(
            self.db, actor, p.id, RespuestaIn(texto=RESPUESTAS.get(categoria, RESPUESTAS[CategoriaPqrs.ASEO]))
        )
        if desenlace.startswith("calificada") and canal == "PORTAL":
            residente = await self.como("residente", R.RESIDENTE)
            await pqrs.calificar(self.db, residente, p.id, CalificacionIn(calificacion=int(desenlace.split(":")[1])))
        elif desenlace.startswith(("calificada", "cerrada")):
            admin = await self.como("admin", R.ADMIN)
            await pqrs.gestionar(self.db, admin, p.id, GestionPqrsIn(estado=EstadoPqrs.CERRADA))

    async def circulares(self) -> None:
        admin = await self.como("admin", R.ADMIN)
        for dias, categoria, importante, torres, titulo, cuerpo in CIRCULARES:
            c = await circulares.crear(
                self.db,
                admin,
                CircularIn(
                    titulo=titulo,
                    cuerpo=cuerpo,
                    categoria=categoria,
                    importante=importante,
                    torres=torres,
                    enviar_correo=False,
                ),
            )
            await circulares.publicar(self.db, admin, c.id)
            self.fechas_circular[c.id] = dias
        await circulares.crear(
            self.db, admin,
            CircularIn(titulo="Cierre de la piscina por mantenimiento", cuerpo="La piscina estará cerrada del 1 al 15 de diciembre por el mantenimiento anual del sistema de filtración.", categoria=CategoriaCircular.MANTENIMIENTO),
        )  # fmt: skip
        # Carlos leyó las más antiguas
        residente = await self.como("residente", R.RESIDENTE)
        for cid, dias in self.fechas_circular.items():
            if dias > 20:
                await circulares.marcar_leida(self.db, residente, cid)

    async def reservas(self, zonas: dict[str, uuid.UUID]) -> None:
        residente = await self.como("residente", R.RESIDENTE)
        unidad = await self.unidad("1-502")
        if unidad is None:
            return
        await reservas.solicitar(
            self.db, residente,
            ReservaPortalIn(zona_id=zonas["Zona BBQ"], unidad_id=unidad, fecha_evento=self.hoy + timedelta(days=4), hora_inicio=time(12), hora_fin=time(17), numero_asistentes=12, observaciones="Cumpleaños de Samuel"),
        )  # fmt: skip
        await reservas.solicitar(
            self.db, residente,
            ReservaPortalIn(zona_id=zonas["Salón social"], unidad_id=unidad, fecha_evento=self.hoy + timedelta(days=24), hora_inicio=time(15), hora_fin=time(22), numero_asistentes=45, observaciones="Novena de aguinaldos de la torre 1"),
        )  # fmt: skip

    def ajustar_fechas(self) -> None:
        from app.services.demo import _owner_engine, sin_triggers

        with _owner_engine().begin() as conn, sin_triggers(conn):
            for pid, dias in self.fechas.items():
                creada = datetime.combine(self.hoy - timedelta(days=dias), time(9, 30), TZ)
                limite = sumar_dias_habiles(creada.date(), 15)
                conn.execute(
                    text(
                        "UPDATE pqrs SET created_at = :c, updated_at = :c + interval '2 days', fecha_limite = :l,"
                        " respondida_at = CASE WHEN respondida_at IS NULL THEN NULL ELSE :c + interval '4 days' END,"
                        " cerrada_at = CASE WHEN cerrada_at IS NULL THEN NULL ELSE :c + interval '6 days' END WHERE id = :id"
                    ),
                    {"c": creada, "l": limite, "id": pid},
                )
                conn.execute(
                    text(
                        "WITH m AS (SELECT id, row_number() OVER (ORDER BY created_at) AS n FROM pqrs_mensajes WHERE pqrs_id = :id)"
                        " UPDATE pqrs_mensajes pm SET created_at = :c + (m.n || ' days')::interval FROM m WHERE pm.id = m.id"
                    ),
                    {"c": creada, "id": pid},
                )
            for cid, dias in self.fechas_circular.items():
                pub = datetime.combine(self.hoy - timedelta(days=dias), time(8), TZ)
                conn.execute(
                    text("UPDATE circulares SET created_at = :p, publicada_at = :p, updated_at = :p WHERE id = :id"),
                    {"p": pub, "id": cid},
                )
                conn.execute(
                    text("UPDATE circular_lecturas SET leida_at = :p + interval '1 day' WHERE circular_id = :id"),
                    {"p": pub, "id": cid},
                )


async def generar() -> None:
    async with SessionLocal() as db:
        tenant_id = await db.scalar(select(Tenant.id).where(Tenant.slug == TENANT))
        if tenant_id is None:
            raise SystemExit("No existe la copropiedad de demo: ejecute primero python -m app.scripts.seed")
        await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
        if await db.scalar(select(func.count()).select_from(Pqrs)):
            print("Ya hay datos del portal en la demo: no se generan de nuevo.")
            return
        correos = {
            "admin": "admin@lospinos.demo",
            "residente": "residente@lospinos.demo",
            "recepcion": "recepcion@lospinos.demo",
            "contabilidad": "contabilidad@lospinos.demo",
        }
        usuarios = {k: await db.scalar(select(User.id).where(User.email == v)) for k, v in correos.items()}
        if None in usuarios.values():
            raise SystemExit("Faltan usuarios de la demo: ejecute python -m app.scripts.seed")
        miembros = set(await db.scalars(select(Membership.user_id).where(Membership.tenant_id == tenant_id)))
        assert set(usuarios.values()) <= miembros
        demo = Demo(db, tenant_id, usuarios)  # type: ignore[arg-type]
        zonas = await demo.zonas()
        await demo.pqrs()
        await demo.circulares()
        await demo.reservas(zonas)
        await db.commit()
    demo.ajustar_fechas()
    print(
        f"Portal de demo: {len(PQRS)} PQRS, {len(CIRCULARES)} circulares publicadas, reglas en {len(zonas)} zonas, 2 reservas de Carlos."
    )


def main() -> None:
    asyncio.run(generar())
