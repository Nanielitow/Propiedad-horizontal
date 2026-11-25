"""Datos de demostración del módulo de activos y mantenimiento (Conjunto Residencial Los Pinos).

Un año de operación construido con los MISMOS casos de uso que la API (validaciones,
triggers y auditoría), así los datos son coherentes por construcción:
  - 6 contratistas y 25 activos de las 4 categorías (uno dado de baja);
  - planes preventivos aprobados hace un año y ejecutados casi siempre a tiempo
    (algunos vencidos a propósito, para que el semáforo tenga rojos);
  - un plan por horas de uso con horómetro y otro "desde la última ejecución";
  - correctivos con su novedad cerrada, una novedad descartada y novedades abiertas
    (una crítica con el equipo fuera de servicio, otra pendiente de cotización
    vinculada a la comparación de cotizaciones de la demo);
  - recomendaciones técnicas en todos sus estados.

Los registros quedan con fecha de hoy en las columnas que la base fija con now()
(reporte de novedades, creación de mantenimientos, auditoría). Al final se
ajustan a su fecha simulada con la conexión del dueño de la base, sin triggers:
es solo para que la demo cuente bien los tiempos, la API nunca puede hacerlo.

Uso: python -m app.scripts.demo activos   (requiere `seed`; no repite si ya hay activos)
"""

import asyncio
import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import (
    ActividadProgramada,
    Activo,
    CategoriaActivo,
    Document,
    Membership,
    PlanPreventivo,
    QuoteComparison,
    Tenant,
    User,
)
from app.models.enums import (
    BaseCalculo,
    Criticidad,
    EstadoActividad,
    EstadoActivo,
    EstadoNovedad,
    EstadoRecomendacion,
    Periodicidad,
    PrioridadNovedad,
    PrioridadRecomendacion,
    TipoDocumentoActivo,
    TipoMantenimiento,
    UserRole,
)
from app.schemas.activos import (
    ActivoIn,
    ActivoUpdate,
    BajaIn,
    ContratistaIn,
    ItemChecklist,
    MantenimientoIn,
    NovedadAvance,
    NovedadIn,
    PlanIn,
    RecomendacionNueva,
    RecomendacionUpdate,
    ReprogramacionIn,
    VinculoDocumentoIn,
)
from app.services.activos import activos, catalogo, mantenimientos, novedades, planes, recomendaciones
from app.services.activos.dominio import siguiente_fecha
from app.services.comun import TZ, ActorSimple, hoy_bogota

TENANT = "los-pinos"
rng = random.Random(20261123)  # noqa: S311  (determinista a propósito: la demo sale igual cada vez)
R = UserRole
N = EstadoNovedad
P = Periodicidad

TECNICO_INTERNO = "Pedro Ramírez"

# clave: (razón social, NIT, especialidades, técnico que firma, días al fin del contrato, valor anual, periodicidad)
CONTRATISTAS = {
    "asc": ("Ascensores Andinos S.A.S.", "900111222-3", ["Ascensores"], "Jhon Pérez", 45, 28_800_000, "Mensual"),
    "hid": (
        "Hidráulicas del Norte Ltda.",
        "900333444-5",
        ["Motobombas", "Redes hidráulicas"],
        "Óscar Duarte",
        200,
        9_600_000,
        "Bimestral",
    ),
    "ene": (
        "Energía y Plantas S.A.S.",
        "900555666-7",
        ["Plantas eléctricas", "Tableros eléctricos"],
        "Luis Herrera",
        120,
        7_200_000,
        "Trimestral",
    ),
    "seg": (
        "Seguridad Electrónica Total S.A.S.",
        "900777888-9",
        ["CCTV", "Control de acceso", "Citofonía", "Puertas automáticas"],
        "Diana Castro",
        260,
        10_800_000,
        "Trimestral",
    ),
    "inc": (
        "Protección Contra Incendio Bogotá",
        "900999000-1",
        ["Extintores", "Detección de incendios"],
        "Mauricio León",
        90,
        4_800_000,
        "Semestral",
    ),
    "civ": (
        "Mantenimientos Civiles JR",
        "79888777-2",
        ["Fachadas", "Cubiertas", "Impermeabilización", "Lavado de tanques"],
        "Rubén Jiménez",
        None,
        None,
        "Por servicio",
    ),
}


@dataclass(frozen=True)
class A:
    clave: str
    nombre: str
    categoria: str
    subtipo: str
    ubicacion: str
    criticidad: Criticidad
    anios: int  # años desde la instalación
    vida_util: int
    marca: str | None = None
    modelo: str | None = None
    esp: dict[str, str] = field(default_factory=dict)
    mantenedor: str | None = None
    garantia_dias: int | None = None  # días hasta el fin de la garantía (desde hoy)


EM, ST, RI, IN = "ELECTROMECANICOS", "SEGURIDAD_TECNOLOGIA", "REDES_INSTALACIONES", "INFRAESTRUCTURA"
ALTA, MEDIA, BAJA = Criticidad.ALTA, Criticidad.MEDIA, Criticidad.BAJA
ASCENSOR = {
    "Capacidad": "8 personas / 630 kg",
    "Paradas": "13",
    "Velocidad": "1 m/s",
    "Tracción": "Sin cuarto de máquinas",
}
MOTOBOMBA = {"Potencia": "5 HP", "Caudal": "120 L/min", "Presión de trabajo": "60 PSI"}
ACTIVOS = [
    A(
        "asc1",
        "Ascensor torre 1",
        EM,
        "Ascensor",
        "Torre 1 · Foso y cuarto de control",
        ALTA,
        8,
        25,
        "Schindler",
        "3300",
        ASCENSOR,
        "asc",
    ),
    A(
        "asc2",
        "Ascensor torre 2",
        EM,
        "Ascensor",
        "Torre 2 · Foso y cuarto de control",
        ALTA,
        8,
        25,
        "Schindler",
        "3300",
        ASCENSOR,
        "asc",
    ),
    A(
        "mb1",
        "Motobomba de presión 1",
        EM,
        "Motobomba",
        "Sótano 1 · Cuarto de bombas",
        ALTA,
        6,
        15,
        "Pedrollo",
        "CPm 680",
        MOTOBOMBA,
        "hid",
    ),
    A(
        "mb2",
        "Motobomba de presión 2",
        EM,
        "Motobomba",
        "Sótano 1 · Cuarto de bombas",
        ALTA,
        6,
        15,
        "Pedrollo",
        "CPm 680",
        MOTOBOMBA,
        "hid",
    ),
    A(
        "eyec",
        "Bomba eyectora de aguas lluvias",
        EM,
        "Bomba eyectora",
        "Sótano 2 · Pozo eyector",
        ALTA,
        9,
        12,
        "Barnes",
        "4SE",
        {"Potencia": "2 HP"},
        "hid",
    ),
    A(
        "planta",
        "Planta eléctrica de emergencia",
        EM,
        "Planta eléctrica",
        "Sótano 1 · Cuarto eléctrico",
        ALTA,
        7,
        20,
        "Cummins",
        "C80D6",
        {"Potencia": "80 kVA", "Combustible": "ACPM", "Autonomía": "8 h", "Transferencia": "Automática"},
        "ene",
    ),
    A(
        "vent",
        "Ventilación mecánica del sótano",
        EM,
        "Ventilación mecánica",
        "Sótanos 1 y 2",
        MEDIA,
        8,
        15,
        "Soler & Palau",
        "CMB/4",
        {"Extractores": "4"},
    ),
    A(
        "gym",
        "Equipos del gimnasio",
        EM,
        "Equipos de gimnasio",
        "Club house · Gimnasio",
        BAJA,
        1,
        8,
        "Life Fitness",
        "Serie Integrity",
        {"Equipos": "2 caminadoras, 1 elíptica, 1 multifuerza"},
        garantia_dias=30,
    ),
    A(
        "piscina",
        "Sistema de filtración de la piscina",
        EM,
        "Piscina / turco / sauna",
        "Club house · Cuarto de máquinas",
        MEDIA,
        8,
        12,
        "Hayward",
        "Pro Series",
        {"Filtro": "Arena sílice", "Volumen": "85 m³"},
    ),
    A(
        "cctv",
        "Circuito cerrado de televisión (32 cámaras)",
        ST,
        "CCTV",
        "Portería · Cuarto de monitoreo",
        ALTA,
        3,
        8,
        "Hikvision",
        "DS-7732NI",
        {"Cámaras": "32", "Grabación": "15 días"},
        "seg",
    ),
    A(
        "acceso",
        "Control de acceso vehicular",
        ST,
        "Control de acceso",
        "Portería vehicular",
        ALTA,
        3,
        10,
        "ZKTeco",
        "ProBG",
        {"Lectores": "2 de largo alcance (tags)"},
        "seg",
    ),
    A(
        "citof",
        "Citofonía IP",
        ST,
        "Citofonía",
        "Portería y 96 apartamentos",
        MEDIA,
        1,
        10,
        "Commax",
        "CIOT",
        {"Extensiones": "96"},
        "seg",
        garantia_dias=300,
    ),
    A("citof_viejo", "Citofonía análoga (antigua)", ST, "Citofonía", "Portería", BAJA, 8, 8, "Commax", "DP-2S"),
    A(
        "incendio",
        "Detección y alarma contra incendio",
        ST,
        "Detección y alarma contra incendios",
        "Torres 1 y 2 · Zonas comunes",
        ALTA,
        8,
        15,
        "Notifier",
        "NFS-320",
        {"Detectores": "84", "Estaciones manuales": "12"},
        "inc",
    ),
    A(
        "puerta",
        "Puerta vehicular automática",
        ST,
        "Control de puertas",
        "Acceso vehicular",
        ALTA,
        5,
        10,
        "FAAC",
        "C720",
        {"Tipo": "Corrediza", "Motor": "Industrial"},
        "seg",
    ),
    A(
        "tanque",
        "Tanque de reserva de agua potable",
        RI,
        "Tanque de agua",
        "Sótano 1 · Cuarto de tanques",
        ALTA,
        8,
        30,
        None,
        None,
        {"Capacidad": "60 m³", "Material": "Concreto"},
    ),
    A(
        "tablero",
        "Tablero eléctrico general",
        RI,
        "Tablero eléctrico",
        "Sótano 1 · Subestación",
        ALTA,
        8,
        25,
        "Schneider",
        "Prisma G",
        {"Corriente": "400 A"},
        "ene",
    ),
    A("red_hid", "Red hidráulica de zonas comunes", RI, "Red hidráulica", "Torres 1 y 2", MEDIA, 8, 40),
    A("aguas", "Red de aguas lluvias y canales", RI, "Aguas lluvias", "Cubiertas y bajantes", MEDIA, 8, 30),
    A(
        "fachada1",
        "Fachada torre 1",
        IN,
        "Fachada",
        "Torre 1",
        MEDIA,
        8,
        50,
        None,
        None,
        {"Acabado": "Ladrillo a la vista"},
    ),
    A(
        "fachada2",
        "Fachada torre 2",
        IN,
        "Fachada",
        "Torre 2",
        MEDIA,
        8,
        50,
        None,
        None,
        {"Acabado": "Ladrillo a la vista"},
    ),
    A(
        "cubierta1",
        "Cubierta torre 1",
        IN,
        "Cubierta / terraza",
        "Torre 1 · Piso 13",
        ALTA,
        8,
        20,
        None,
        None,
        {"Área": "420 m²", "Impermeabilización": "Manto asfáltico"},
    ),
    A(
        "cubierta2",
        "Cubierta torre 2",
        IN,
        "Cubierta / terraza",
        "Torre 2 · Piso 13",
        ALTA,
        8,
        20,
        None,
        None,
        {"Área": "420 m²", "Impermeabilización": "Manto asfáltico"},
    ),
    A(
        "parque",
        "Parqueadero y pisos del sótano",
        IN,
        "Parqueadero",
        "Sótanos 1 y 2",
        MEDIA,
        8,
        30,
        None,
        None,
        {"Cupos": "110"},
    ),
    A("plazoleta", "Plazoleta y zonas verdes", IN, "Plazoleta", "Primer piso", BAJA, 8, 30),
]


@dataclass(frozen=True)
class Plan:
    clave: str
    activo: str
    nombre: str
    periodicidad: Periodicidad
    costo: int
    contratista: str | None = None
    checklist: tuple[str, ...] = ()
    base: BaseCalculo = BaseCalculo.CALENDARIO_FIJO
    intervalo_horas: int | None = None
    desfase: int | None = None  # días desde hace un año hasta su inicio (None: aleatorio en el primer mes)
    vencer_ultima: bool = False  # deja sin ejecutar su última fecha pasada (rojo en el semáforo)


CHECK_ASCENSOR = (
    "Revisión de frenos",
    "Lubricación de guías",
    "Prueba de puertas y sensores",
    "Revisión de cables",
    "Prueba del botón de emergencia",
)
PLANES = [
    Plan("asc1_m", "asc1", "Mantenimiento preventivo mensual", P.MENSUAL, 1_200_000, "asc", CHECK_ASCENSOR),
    Plan("asc2_m", "asc2", "Mantenimiento preventivo mensual", P.MENSUAL, 1_200_000, "asc", CHECK_ASCENSOR),
    Plan("asc1_a", "asc1", "Inspección anual para certificación (NTC 5926)", P.ANUAL, 950_000, "asc", desfase=405),
    Plan("asc2_a", "asc2", "Inspección anual para certificación (NTC 5926)", P.ANUAL, 950_000, "asc", desfase=410),
    Plan(
        "mb1_b",
        "mb1",
        "Revisión bimestral del equipo de presión",
        P.BIMESTRAL,
        320_000,
        "hid",
        ("Presión de arranque y parada", "Revisión de sellos", "Limpieza de válvulas"),
    ),
    Plan(
        "mb2_b",
        "mb2",
        "Revisión bimestral del equipo de presión",
        P.BIMESTRAL,
        320_000,
        "hid",
        ("Presión de arranque y parada", "Revisión de sellos", "Limpieza de válvulas"),
    ),
    Plan(
        "mb1_h",
        "mb1",
        "Cambio de sellos mecánicos y rodamientos",
        P.POR_HORAS_USO,
        380_000,
        intervalo_horas=500,
        desfase=0,
    ),
    Plan("eyec_t", "eyec", "Limpieza del pozo y revisión de la bomba", P.TRIMESTRAL, 450_000, "hid"),
    Plan(
        "planta_q",
        "planta",
        "Prueba de arranque y revisión de niveles",
        P.QUINCENAL,
        0,
        None,
        ("Arranque en vacío 15 min", "Nivel de ACPM", "Nivel de aceite y refrigerante", "Voltaje de baterías"),
    ),
    Plan(
        "planta_t",
        "planta",
        "Mantenimiento preventivo trimestral",
        P.TRIMESTRAL,
        650_000,
        "ene",
        ("Cambio de filtros", "Prueba con carga", "Revisión de la transferencia"),
        vencer_ultima=True,
    ),
    Plan("vent_s", "vent", "Limpieza de extractores y revisión de motores", P.SEMESTRAL, 180_000),
    Plan("gym_t", "gym", "Lubricación y ajuste de equipos", P.TRIMESTRAL, 120_000),
    Plan(
        "piscina_m",
        "piscina",
        "Lavado de filtros y control químico",
        P.MENSUAL,
        150_000,
        None,
        ("Retrolavado del filtro", "Medición de pH y cloro", "Limpieza de prefiltro"),
    ),
    Plan(
        "cctv_t",
        "cctv",
        "Mantenimiento preventivo de cámaras y grabador",
        P.TRIMESTRAL,
        400_000,
        "seg",
        ("Limpieza de domos", "Revisión de discos", "Ajuste de enfoque"),
        vencer_ultima=True,
    ),
    Plan("acceso_s", "acceso", "Revisión de lectores y barreras", P.SEMESTRAL, 280_000, "seg"),
    Plan("citof_s", "citof", "Revisión de la central y extensiones", P.SEMESTRAL, 200_000, "seg"),
    Plan("incendio_s", "incendio", "Prueba de detectores y panel", P.SEMESTRAL, 600_000, "inc"),
    Plan(
        "incendio_a", "incendio", "Recarga y prueba hidrostática de extintores", P.ANUAL, 1_100_000, "inc", desfase=300
    ),
    Plan("puerta_t", "puerta", "Mantenimiento del motor y la cremallera", P.TRIMESTRAL, 250_000, "seg"),
    Plan(
        "tanque_s",
        "tanque",
        "Lavado y desinfección del tanque",
        P.SEMESTRAL,
        850_000,
        "civ",
        base=BaseCalculo.DESDE_ULTIMA_EJECUCION,
        desfase=20,
    ),
    Plan("tablero_a", "tablero", "Termografía y reapriete de conexiones", P.ANUAL, 700_000, "ene", desfase=150),
    Plan("aguas_t", "aguas", "Limpieza de canales y bajantes", P.TRIMESTRAL, 90_000, vencer_ultima=True),
    Plan("cubierta1_s", "cubierta1", "Inspección de cubierta e impermeabilización", P.SEMESTRAL, 350_000, "civ"),
    Plan("cubierta2_s", "cubierta2", "Inspección de cubierta e impermeabilización", P.SEMESTRAL, 350_000, "civ"),
    Plan("fachada1_a", "fachada1", "Inspección de fachada y juntas", P.ANUAL, 400_000, "civ", desfase=170),
    Plan("fachada2_a", "fachada2", "Inspección de fachada y juntas", P.ANUAL, 400_000, "civ", desfase=175),
]

# Recomendaciones del último mantenimiento de un plan:
# (descripción, prioridad, costo, días hasta el límite desde la ejecución, estado final)
RECOMENDACIONES: dict[str, list[tuple[str, PrioridadRecomendacion, int, int | None, EstadoRecomendacion]]] = {
    "asc1_m": [
        (
            "Cambiar los cables de tracción: desgaste del 60 %",
            PrioridadRecomendacion.ALTA,
            4_800_000,
            90,
            EstadoRecomendacion.PENDIENTE,
        )
    ],
    "asc2_m": [
        (
            "Modernizar botoneras de cabina a tecnología LED",
            PrioridadRecomendacion.BAJA,
            2_200_000,
            None,
            EstadoRecomendacion.PENDIENTE,
        )
    ],
    "mb2_b": [
        (
            "Instalar un tanque hidroacumulador adicional",
            PrioridadRecomendacion.MEDIA,
            1_800_000,
            120,
            EstadoRecomendacion.PENDIENTE,
        )
    ],
    "planta_t": [
        (
            "Cambiar las baterías de arranque (voltaje bajo)",
            PrioridadRecomendacion.ALTA,
            650_000,
            20,
            EstadoRecomendacion.PENDIENTE,
        )
    ],
    "cctv_t": [
        (
            "Ampliar el almacenamiento del grabador a 30 días",
            PrioridadRecomendacion.MEDIA,
            1_200_000,
            60,
            EstadoRecomendacion.EJECUTADA,
        )
    ],
    "incendio_s": [
        (
            "Reemplazar 6 detectores de humo con falla intermitente",
            PrioridadRecomendacion.ALTA,
            900_000,
            45,
            EstadoRecomendacion.EN_PROCESO,
        )
    ],
    "cubierta2_s": [
        (
            "Impermeabilizar toda la cubierta de la torre 2",
            PrioridadRecomendacion.ALTA,
            38_000_000,
            120,
            EstadoRecomendacion.PENDIENTE,
        )
    ],
    "fachada1_a": [
        (
            "Lavado e hidrofugado de las fachadas",
            PrioridadRecomendacion.MEDIA,
            24_000_000,
            None,
            EstadoRecomendacion.DESCARTADA_CON_JUSTIFICACION,
        )
    ],
    "tanque_s": [
        (
            "Cambiar el flotador mecánico del tanque",
            PrioridadRecomendacion.BAJA,
            180_000,
            30,
            EstadoRecomendacion.EJECUTADA,
        )
    ],
}

# Correctivos del año: (activo, días atrás, prioridad, descripción, contratista, diagnóstico, actividades, repuestos, mano de obra, repuestos $)
CORRECTIVOS = [
    (
        "asc1",
        290,
        PrioridadNovedad.ALTA,
        "El ascensor se detiene en el piso 7 y no abre las puertas",
        "asc",
        "Falla del operador de puertas",
        "Cambio del operador de puertas de cabina",
        "Operador de puertas",
        350_000,
        1_450_000,
    ),
    (
        "mb2",
        240,
        PrioridadNovedad.CRITICA,
        "La motobomba 2 no arranca: baja presión en los pisos altos",
        "hid",
        "Capacitor de arranque quemado",
        "Cambio de capacitor y prueba de presión",
        "Capacitor 60 µF",
        180_000,
        95_000,
    ),
    (
        "cctv",
        200,
        PrioridadNovedad.MEDIA,
        "Cuatro cámaras del parqueadero sin imagen",
        "seg",
        "Fuente de poder averiada",
        "Cambio de fuente de poder de 12 V",
        "Fuente 12 V 10 A",
        120_000,
        160_000,
    ),
    (
        "tablero",
        160,
        PrioridadNovedad.ALTA,
        "Se dispara el breaker de iluminación de zonas comunes",
        "ene",
        "Cortocircuito en el circuito del parqueadero",
        "Reparación del circuito y cambio de breaker",
        "Breaker 3x40 A",
        280_000,
        210_000,
    ),
    (
        "puerta",
        120,
        PrioridadNovedad.ALTA,
        "La puerta vehicular no cierra por completo",
        "seg",
        "Cremallera desalineada y fotocelda sucia",
        "Alineación de cremallera y limpieza de fotoceldas",
        None,
        150_000,
        0,
    ),
    (
        "piscina",
        75,
        PrioridadNovedad.MEDIA,
        "Fuga de agua en la bomba de la piscina",
        None,
        "Sello mecánico desgastado",
        "Cambio del sello mecánico",
        'Sello mecánico 1"',
        90_000,
        65_000,
    ),
    (
        "red_hid",
        40,
        PrioridadNovedad.ALTA,
        "Fuga en la tubería del piso 3 de la torre 1",
        "hid",
        "Unión de PVC fisurada",
        'Cambio de tramo y unión de 1"',
        "Tubería y uniones PVC",
        220_000,
        48_000,
    ),
]


def _momento(dia: date, hora: int, minuto: int = 0) -> datetime:
    return datetime.combine(dia, time(hora, minuto), TZ)


def _miles(valor: Decimal) -> Decimal:
    """Redondea a miles de pesos, como se cotiza."""
    return (valor / 1000).quantize(Decimal(1)) * 1000


class Demo:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID, usuarios: dict[UserRole, uuid.UUID]) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.usuarios = usuarios
        self.hoy = hoy_bogota()
        self.inicio = self.hoy - timedelta(days=365)
        self.contratistas: dict[str, uuid.UUID] = {}
        self.activos: dict[str, Activo] = {}
        self.planes: dict[str, PlanPreventivo] = {}
        self.recomendaciones_creadas: list[tuple[uuid.UUID, EstadoRecomendacion]] = []
        # Fechas simuladas que la base fijó con now(): se ajustan al final
        self.tiempos_novedad: dict[uuid.UUID, tuple[datetime, datetime | None, datetime | None]] = {}

    async def como(self, rol: UserRole) -> ActorSimple:
        user = self.usuarios[rol]
        await set_rls_context(self.db, tenant_id=self.tenant_id, user_id=user, role=rol.value)
        return ActorSimple(self.tenant_id, user, rol)

    async def sistema(self) -> None:
        await set_rls_context(self.db, tenant_id=self.tenant_id, role="SYSTEM")

    # --- Catálogo y activos ---------------------------------------------------------------

    async def preparar(self) -> None:
        admin = await self.como(R.ADMIN)
        for clave, (razon, nit, esp, tecnico, dias_fin, valor, periodicidad) in CONTRATISTAS.items():
            c = await catalogo.crear_contratista(
                self.db,
                admin,
                ContratistaIn(
                    razon_social=razon,
                    nit=nit,
                    contacto_nombre=tecnico,
                    telefono=f"601 {rng.randint(300, 799)} {rng.randint(1000, 9999)}",
                    email=f"servicio@{razon.split()[0].lower()}.demo",
                    especialidades=esp,
                    vigencia_contrato_inicio=self.hoy - timedelta(days=365 - (dias_fin or 0)) if dias_fin else None,
                    vigencia_contrato_fin=self.hoy + timedelta(days=dias_fin) if dias_fin else None,
                    valor_contrato=Decimal(valor) if valor else None,
                    periodicidad_pactada=periodicidad,
                    alcance_contrato=f"Mantenimiento preventivo y correctivo de: {', '.join(esp).lower()}."
                    if dias_fin
                    else None,
                ),
            )
            self.contratistas[clave] = c.id
        categorias = {c.codigo: c.id for c in await self.db.scalars(select(CategoriaActivo))}
        for a in ACTIVOS:
            self.activos[a.clave] = await activos.crear_activo(
                self.db,
                admin,
                ActivoIn(
                    nombre=a.nombre,
                    categoria_id=categorias[a.categoria],
                    subtipo=a.subtipo,
                    ubicacion=a.ubicacion,
                    marca=a.marca,
                    modelo=a.modelo,
                    numero_serie=f"{(a.marca or 'PH')[:3].upper()}-{rng.randint(100000, 999999)}" if a.marca else None,
                    especificaciones=a.esp,
                    vida_util_anios=a.vida_util,
                    fecha_instalacion=self.hoy - timedelta(days=365 * a.anios + rng.randint(0, 200)),
                    instalador_id=self.contratistas.get(a.mantenedor) if a.anios <= 3 and a.mantenedor else None,
                    mantenedor_id=self.contratistas.get(a.mantenedor) if a.mantenedor else None,
                    fecha_vencimiento_garantia=self.hoy + timedelta(days=a.garantia_dias) if a.garantia_dias else None,
                    criticidad=a.criticidad,
                ),
            )
        await self.db.commit()

    # --- Planes e historial preventivo --------------------------------------------------------

    async def aprobar_planes(self) -> None:
        for p in PLANES:
            actor = await self.como(R.AUXILIAR if rng.random() < 0.3 else R.ADMIN)  # algunos los propuso recepción
            inicio = self.inicio + timedelta(days=p.desfase if p.desfase is not None else rng.randint(0, 27))
            plan = await planes.crear_plan(
                self.db,
                actor,
                PlanIn(
                    activo_id=self.activos[p.activo].id,
                    nombre=p.nombre,
                    actividades_checklist=list(p.checklist),
                    periodicidad=p.periodicidad,
                    intervalo_horas=p.intervalo_horas,
                    base_calculo=p.base,
                    fecha_inicio=inicio,
                    contratista_id=self.contratistas.get(p.contratista) if p.contratista else None,
                    costo_estimado=Decimal(p.costo) if p.costo else None,
                ),
            )
            admin = await self.como(R.ADMIN)
            await planes.aprobar_plan(self.db, admin, plan.id, hoy=self.inicio)  # aprobados hace un año
            self.planes[p.clave] = plan
        # Uno propuesto por recepción que la administración aún no aprueba
        auxiliar = await self.como(R.AUXILIAR)
        await planes.crear_plan(
            self.db,
            auxiliar,
            PlanIn(
                activo_id=self.activos["fachada1"].id,
                nombre="Lavado de fachada con hidrolavadora",
                periodicidad=P.ANUAL,
                fecha_inicio=self.hoy + timedelta(days=60),
                contratista_id=self.contratistas["civ"],
                costo_estimado=Decimal(6_500_000),
            ),
        )
        await self.db.commit()

    def _mantenimiento(self, p: Plan, actividad: ActividadProgramada | None, ejecucion: date) -> MantenimientoIn:
        contratista = p.contratista
        costo = Decimal(p.costo) * Decimal(str(rng.uniform(0.9, 1.15)))
        mano = _miles(costo * Decimal("0.7")) if contratista else Decimal(0)
        repuestos = _miles(costo - mano) if p.costo else Decimal(0)
        observaciones = rng.random() < 0.08
        return MantenimientoIn(
            activo_id=self.activos[p.activo].id,
            actividad_id=actividad.id if actividad else None,
            tipo=TipoMantenimiento.PREVENTIVO,
            fecha_ejecucion=ejecucion,
            contratista_id=self.contratistas[contratista] if contratista else None,
            nombre_tecnico=f"{CONTRATISTAS[contratista][3]} ({CONTRATISTAS[contratista][0]})"
            if contratista
            else TECNICO_INTERNO,
            tiempo_ejecucion_horas=Decimal(rng.choice(["0.5", "1", "1.5", "2", "3", "4"])),
            actividades_realizadas=p.nombre + (": " + ", ".join(p.checklist).lower() if p.checklist else ""),
            novedades_encontradas="Desgaste leve; se deja en observación." if observaciones else None,
            checklist=[ItemChecklist(actividad=c, resultado="HECHO") for c in p.checklist],
            estado_post_intervencion=EstadoActivo.OPERATIVO_CON_OBSERVACIONES
            if observaciones
            else EstadoActivo.OPERATIVO,
            costo_mano_obra=mano,
            costo_repuestos=repuestos,
        )

    async def _registrar(
        self, p: Plan, actividad: ActividadProgramada | None, ejecucion: date, *, ultimo: bool = False
    ) -> None:
        """Registra el mantenimiento. En el último de un plan, el técnico deja sus recomendaciones."""
        # El técnico interno registra lo suyo; lo de contratistas lo registra la administración con el informe
        actor = await self.como(R.ADMIN if p.contratista else R.MANTENIMIENTO)
        datos = self._mantenimiento(p, actividad, ejecucion)
        sugeridas = RECOMENDACIONES.get(p.clave, []) if ultimo else []
        datos.recomendaciones = [
            RecomendacionNueva(
                descripcion=descripcion,
                prioridad=prioridad,
                costo_estimado=Decimal(costo),
                fecha_limite=ejecucion + timedelta(days=dias) if dias else None,
            )
            for descripcion, prioridad, costo, dias, _ in sugeridas
        ]
        if sugeridas:
            datos.recomendaciones_tecnico = "; ".join(r.descripcion for r in datos.recomendaciones)
        _, creadas = await mantenimientos.registrar(self.db, actor, datos)
        self.recomendaciones_creadas += [(r.id, s[4]) for r, s in zip(creadas, sugeridas, strict=True)]

    async def ejecutar_calendario(self) -> None:
        """Ejecuta en orden cronológico las actividades pasadas de los planes de calendario fijo."""
        por_id = {
            self.planes[p.clave].id: p
            for p in PLANES
            if p.base == BaseCalculo.CALENDARIO_FIJO and p.intervalo_horas is None
        }
        await self.sistema()
        pasadas = list(
            await self.db.scalars(
                select(ActividadProgramada)
                .where(
                    ActividadProgramada.plan_id.in_(por_id),
                    ActividadProgramada.fecha_programada < self.hoy,
                    ActividadProgramada.estado == EstadoActividad.PROGRAMADA,
                )
                .order_by(ActividadProgramada.fecha_programada)
            )
        )
        ultima_pasada: dict[uuid.UUID, uuid.UUID] = {}
        for x in pasadas:
            ultima_pasada[x.plan_id] = x.id
        a_ejecutar = [
            x
            for x in pasadas
            # vencidas a propósito (rojo en el semáforo): la última de algunos planes y las de los últimos 2 días
            if not (por_id[x.plan_id].vencer_ultima and ultima_pasada[x.plan_id] == x.id)
            and (self.hoy - x.fecha_programada).days > 2
        ]
        ultima_ejecutada = {x.plan_id: x.id for x in a_ejecutar}
        for x in a_ejecutar:
            ejecucion = min(
                x.fecha_programada + timedelta(days=rng.choice([0, 0, 0, 1, 2])), self.hoy - timedelta(days=1)
            )
            await self._registrar(por_id[x.plan_id], x, ejecucion, ultimo=ultima_ejecutada[x.plan_id] == x.id)
        await self.db.commit()

    async def ejecutar_desde_ultima(self) -> None:
        """Plan que cuenta desde la última ejecución: la base programa la siguiente fecha."""
        for p in (p for p in PLANES if p.base == BaseCalculo.DESDE_ULTIMA_EJECUCION):
            plan_id = self.planes[p.clave].id
            while True:
                await self.sistema()
                x = await self.db.scalar(
                    select(ActividadProgramada).where(
                        ActividadProgramada.plan_id == plan_id, ActividadProgramada.estado == EstadoActividad.PROGRAMADA
                    )
                )
                if x is None or x.fecha_programada >= self.hoy - timedelta(days=3):
                    break
                ejecucion = x.fecha_programada + timedelta(days=rng.randint(2, 9))
                ultimo = siguiente_fecha(ejecucion, p.periodicidad) >= self.hoy - timedelta(days=3)
                await self._registrar(p, x, ejecucion, ultimo=ultimo)
        await self.db.commit()

    async def horometro(self) -> None:
        """Motobomba 1: lecturas semanales (~6,5 h diarias) y cambios de sellos cada 500 h."""
        p = next(p for p in PLANES if p.intervalo_horas)
        activo = self.activos[p.activo]
        plan_id = self.planes[p.clave].id
        horas = Decimal(11850)
        base = horas
        dia = self.inicio
        while dia <= self.hoy:
            await self.sistema()
            await self.db.execute(
                text(
                    "INSERT INTO lecturas_uso (tenant_id, activo_id, fecha, horas_acumuladas, registrado_por_id) VALUES (:t, :a, :f, :h, :u)"
                ),
                {
                    "t": self.tenant_id,
                    "a": activo.id,
                    "f": _momento(dia, 8),
                    "h": horas,
                    "u": self.usuarios[R.MANTENIMIENTO],
                },
            )
            if horas - base >= 480 and dia < self.hoy:
                x = await self.db.scalar(
                    select(ActividadProgramada).where(
                        ActividadProgramada.plan_id == plan_id, ActividadProgramada.estado == EstadoActividad.PROGRAMADA
                    )
                )
                if x is not None:
                    await self._registrar(p, x, dia)
                    base = horas
            dia += timedelta(days=7)
            horas += Decimal(str(round(rng.uniform(5.8, 7.2) * 7, 1)))
        await self.sistema()
        await planes.extender_programacion(self.db, self.hoy)  # completa los próximos 12 meses
        await planes.reestimar_por_horas(self.db, self.hoy)  # fecha según el horómetro
        await self.db.commit()

    async def recomendaciones(self) -> None:
        """Lleva cada recomendación sugerida a su estado final con los mismos casos de uso de la API."""
        for rec_id, estado in self.recomendaciones_creadas:
            admin = await self.como(R.ADMIN)
            if estado == EstadoRecomendacion.EN_PROCESO:
                await recomendaciones.actualizar(
                    self.db, admin, rec_id, RecomendacionUpdate(responsable_id=self.usuarios[R.MANTENIMIENTO])
                )
                tecnico = await self.como(R.MANTENIMIENTO)
                await recomendaciones.actualizar(self.db, tecnico, rec_id, RecomendacionUpdate(estado=estado))
            elif estado == EstadoRecomendacion.EJECUTADA:
                await recomendaciones.actualizar(
                    self.db,
                    admin,
                    rec_id,
                    RecomendacionUpdate(
                        estado=estado, observaciones_administracion="Aprobada y ejecutada por el contratista"
                    ),
                )
            elif estado == EstadoRecomendacion.DESCARTADA_CON_JUSTIFICACION:
                await recomendaciones.actualizar(
                    self.db,
                    admin,
                    rec_id,
                    RecomendacionUpdate(
                        estado=estado,
                        justificacion_descarte="El consejo la aplazó para la vigencia 2028 por presupuesto",
                    ),
                )
        await self.db.commit()

    # --- Novedades ---------------------------------------------------------------------------------

    async def correctivos(self) -> None:
        for activo, dias, prioridad, descripcion, contratista, diagnostico, hecho, repuesto, mano, rep in CORRECTIVOS:
            dia = self.hoy - timedelta(days=dias)
            reporta = await self.como(rng.choice([R.AUXILIAR, R.MANTENIMIENTO]))
            nov = await novedades.reportar(
                self.db,
                reporta,
                NovedadIn(activo_id=self.activos[activo].id, descripcion=descripcion, prioridad=prioridad),
            )
            admin = await self.como(R.ADMIN)
            await novedades.avanzar(
                self.db,
                admin,
                nov.id,
                NovedadAvance(
                    estado=N.EN_GESTION,
                    contratista_asignado_id=self.contratistas[contratista] if contratista else None,
                    asignado_a_id=None if contratista else self.usuarios[R.MANTENIMIENTO],
                ),
            )
            await novedades.avanzar(
                self.db, admin, nov.id, NovedadAvance(estado=N.EN_EJECUCION, diagnostico=diagnostico)
            )
            ejecucion = dia + timedelta(days=1 if prioridad != PrioridadNovedad.MEDIA else 3)
            actor = await self.como(R.ADMIN if contratista else R.MANTENIMIENTO)
            await mantenimientos.registrar(
                self.db,
                actor,
                MantenimientoIn(
                    activo_id=self.activos[activo].id,
                    novedad_id=nov.id,
                    tipo=TipoMantenimiento.CORRECTIVO,
                    fecha_ejecucion=ejecucion,
                    contratista_id=self.contratistas[contratista] if contratista else None,
                    nombre_tecnico=f"{CONTRATISTAS[contratista][3]} ({CONTRATISTAS[contratista][0]})"
                    if contratista
                    else TECNICO_INTERNO,
                    diagnostico_inicial=diagnostico,
                    actividades_realizadas=hecho,
                    repuestos_utilizados=repuesto,
                    estado_post_intervencion=EstadoActivo.OPERATIVO,
                    costo_mano_obra=Decimal(mano),
                    costo_repuestos=Decimal(rep),
                    tiempo_ejecucion_horas=Decimal(rng.choice(["1", "2", "3", "5"])),
                ),
            )
            admin = await self.como(R.ADMIN)
            await novedades.avanzar(self.db, admin, nov.id, NovedadAvance(estado=N.CERRADA))
            horas_atencion = 2 if prioridad == PrioridadNovedad.CRITICA else rng.randint(4, 30)
            reporte = _momento(dia, rng.randint(7, 17), rng.choice([0, 15, 30, 45]))
            self.tiempos_novedad[nov.id] = (
                reporte,
                reporte + timedelta(hours=horas_atencion),
                _momento(ejecucion + timedelta(days=1), 10),
            )

        # Un reporte duplicado que la administración descarta
        auxiliar = await self.como(R.AUXILIAR)
        dup = await novedades.reportar(
            self.db,
            auxiliar,
            NovedadIn(
                activo_id=self.activos["asc1"].id,
                descripcion="Ascensor torre 1 no abre en el piso 7 (reporte de residente)",
            ),
        )
        admin = await self.como(R.ADMIN)
        await novedades.avanzar(
            self.db,
            admin,
            dup.id,
            NovedadAvance(estado=N.DESCARTADA, motivo_descarte="Duplicado de la novedad del mismo día"),
        )
        reporte = _momento(self.hoy - timedelta(days=290), 18)
        self.tiempos_novedad[dup.id] = (reporte, reporte + timedelta(hours=14), None)
        await self.db.commit()

    async def situacion_actual(self) -> None:
        """Lo que la administración encuentra hoy al entrar."""
        # 1. Crítica: la bomba eyectora se quemó; el equipo queda fuera de servicio
        auxiliar = await self.como(R.AUXILIAR)
        eyec = await novedades.reportar(
            self.db,
            auxiliar,
            NovedadIn(
                activo_id=self.activos["eyec"].id,
                descripcion="La bomba eyectora no arranca y el pozo se llena cuando llueve",
                prioridad=PrioridadNovedad.CRITICA,
                riesgo_identificado="Inundación del sótano 2 y daño de vehículos",
                poner_fuera_de_servicio=True,
            ),
        )
        admin = await self.como(R.ADMIN)
        await novedades.avanzar(
            self.db,
            admin,
            eyec.id,
            NovedadAvance(estado=N.EN_GESTION, contratista_asignado_id=self.contratistas["hid"]),
        )
        await novedades.avanzar(
            self.db,
            admin,
            eyec.id,
            NovedadAvance(estado=N.PROGRAMADA, diagnostico="Motor quemado: se requiere rebobinado o cambio de bomba"),
        )
        r = _momento(self.hoy - timedelta(days=3), 6, 40)
        self.tiempos_novedad[eyec.id] = (r, r + timedelta(hours=1, minutes=20), None)

        # 2. Filtraciones en la cubierta: pendiente de cotización (vinculada a la comparación de la demo)
        tecnico = await self.como(R.MANTENIMIENTO)
        cubierta = await novedades.reportar(
            self.db,
            tecnico,
            NovedadIn(
                activo_id=self.activos["cubierta2"].id,
                descripcion="Filtraciones en los apartamentos 1201 y 1202 cuando llueve fuerte",
                prioridad=PrioridadNovedad.ALTA,
                riesgo_identificado="Daño en cielos rasos y reclamaciones de residentes",
            ),
        )
        admin = await self.como(R.ADMIN)
        await novedades.avanzar(self.db, admin, cubierta.id, NovedadAvance(estado=N.EN_GESTION))
        comparacion = await self.db.scalar(select(QuoteComparison.id).order_by(QuoteComparison.created_at).limit(1))
        await novedades.avanzar(
            self.db,
            admin,
            cubierta.id,
            NovedadAvance(
                estado=N.PENDIENTE_COTIZACION,
                diagnostico="Manto asfáltico cuarteado en el 40 % de la cubierta",
                cotizacion_id=comparacion,
            ),
        )
        r = _momento(self.hoy - timedelta(days=25), 9, 10)
        self.tiempos_novedad[cubierta.id] = (r, r + timedelta(hours=26), None)

        # 3. En ejecución por el contratista de ascensores
        tecnico = await self.como(R.MANTENIMIENTO)
        boton = await novedades.reportar(
            self.db,
            tecnico,
            NovedadIn(activo_id=self.activos["asc2"].id, descripcion="El botón de llamada del piso 5 no responde"),
        )
        admin = await self.como(R.ADMIN)
        await novedades.avanzar(
            self.db,
            admin,
            boton.id,
            NovedadAvance(estado=N.EN_GESTION, contratista_asignado_id=self.contratistas["asc"]),
        )
        await novedades.avanzar(
            self.db, admin, boton.id, NovedadAvance(estado=N.EN_EJECUCION, diagnostico="Pulsador averiado")
        )
        r = _momento(self.hoy - timedelta(days=6), 15)
        self.tiempos_novedad[boton.id] = (r, r + timedelta(hours=20), None)

        # 4. Sin atender: una alta de hace 4 días (dispara el aviso de 72 h) y dos recientes
        for activo, dias, hora, prioridad, descripcion, rol in (
            (
                "acceso",
                4,
                19,
                PrioridadNovedad.ALTA,
                "El lector de tags del acceso vehicular falla de forma intermitente",
                R.AUXILIAR,
            ),
            ("mb1", 2, 7, PrioridadNovedad.MEDIA, "La motobomba 1 vibra y hace ruido al arrancar", R.MANTENIMIENTO),
            ("cctv", 1, 22, PrioridadNovedad.BAJA, "La cámara 12 del parqueadero no muestra imagen", R.AUXILIAR),
        ):
            actor = await self.como(rol)
            n = await novedades.reportar(
                self.db,
                actor,
                NovedadIn(activo_id=self.activos[activo].id, descripcion=descripcion, prioridad=prioridad),
            )
            self.tiempos_novedad[n.id] = (_momento(self.hoy - timedelta(days=dias), hora), None, None)

        # 5. Estados con observaciones decididos por la administración
        admin = await self.como(R.ADMIN)
        for clave, motivo in (
            ("asc2", "Botón del piso 5 en reparación"),
            ("mb1", "Vibración reportada por el técnico, en diagnóstico"),
        ):
            await activos.editar_activo(
                self.db,
                admin,
                self.activos[clave].id,
                ActivoUpdate(estado=EstadoActivo.OPERATIVO_CON_OBSERVACIONES, motivo=motivo),
            )

        # 6. La citofonía antigua se dio de baja al instalar la IP
        await activos.dar_de_baja(
            self.db,
            admin,
            self.activos["citof_viejo"].id,
            BajaIn(
                motivo="Reemplazada por la citofonía IP (sin repuestos disponibles)",
                fecha_baja=self.hoy - timedelta(days=330),
            ),
        )

        # 7. Agenda: actividades próximas asignadas al técnico y una reprogramación
        await self.sistema()
        internos = [self.planes[p.clave].id for p in PLANES if p.contratista is None and p.intervalo_horas is None]
        proximas = list(
            await self.db.scalars(
                select(ActividadProgramada)
                .where(
                    ActividadProgramada.plan_id.in_(internos),
                    ActividadProgramada.estado == EstadoActividad.PROGRAMADA,
                    ActividadProgramada.fecha_programada >= self.hoy,
                )
                .order_by(ActividadProgramada.fecha_programada)
                .limit(4)
            )
        )
        admin = await self.como(R.ADMIN)
        for x in proximas:
            await planes.asignar(self.db, admin, x.id, self.usuarios[R.MANTENIMIENTO])
        siguiente_asc = await self.db.scalar(
            select(ActividadProgramada)
            .where(
                ActividadProgramada.plan_id == self.planes["asc1_m"].id,
                ActividadProgramada.estado == EstadoActividad.PROGRAMADA,
                ActividadProgramada.fecha_programada >= self.hoy + timedelta(days=1),
            )
            .order_by(ActividadProgramada.fecha_programada)
            .limit(1)
        )
        if siguiente_asc is not None:
            auxiliar = await self.como(R.AUXILIAR)
            await planes.reprogramar(
                self.db,
                auxiliar,
                siguiente_asc.id,
                ReprogramacionIn(
                    nueva_fecha=siguiente_asc.fecha_programada + timedelta(days=3),
                    motivo="El contratista pidió el cambio por un festivo",
                ),
            )
        await self.db.commit()

    async def documentos(self) -> None:
        """Vincula documentos de la demo (si ya se cargaron) a la hoja de vida de los activos."""
        admin = await self.como(R.ADMIN)
        vinculos = (
            ("Certificado lavado de tanques", "tanque", TipoDocumentoActivo.CERTIFICACION),
            ("Póliza de áreas comunes", "asc1", TipoDocumentoActivo.OTRO),
            ("Póliza de áreas comunes", "asc2", TipoDocumentoActivo.OTRO),
            ("Cotización Cubiertas Andinas", "cubierta2", TipoDocumentoActivo.OTRO),
            ("Cotización ImperTec", "cubierta2", TipoDocumentoActivo.OTRO),
            ("Cotización Techos Pro", "cubierta2", TipoDocumentoActivo.OTRO),
        )
        for prefijo, activo, tipo in vinculos:
            doc = await self.db.scalar(
                select(Document.id).where(Document.title.startswith(prefijo), Document.deleted_at.is_(None)).limit(1)
            )
            if doc is not None:
                await activos.vincular_documento(
                    self.db, admin, self.activos[activo].id, VinculoDocumentoIn(document_id=doc, tipo=tipo)
                )
        await self.db.commit()

    async def ejecutar(self) -> None:
        await self.preparar()
        await self.aprobar_planes()
        await self.ejecutar_calendario()
        await self.ejecutar_desde_ultima()
        await self.horometro()
        await self.recomendaciones()
        await self.correctivos()
        await self.situacion_actual()
        await self.documentos()


def ajustar_fechas(
    tenant_id: uuid.UUID, inicio: date, tiempos: dict[uuid.UUID, tuple[datetime, datetime | None, datetime | None]]
) -> None:
    """Lleva a su fecha simulada lo que la base fijó con now() (solo demo, sin triggers)."""
    from app.services.demo import _owner_engine, sin_triggers

    with _owner_engine().begin() as conn, sin_triggers(conn):
        t = {"t": tenant_id, "inicio": _momento(inicio - timedelta(days=10), 9)}
        conn.execute(
            text(
                "UPDATE activos SET created_at = :inicio, updated_at = :inicio WHERE tenant_id = :t AND estado <> 'DADO_DE_BAJA'"
            ),
            t,
        )
        conn.execute(text("UPDATE contratistas SET created_at = :inicio, updated_at = :inicio WHERE tenant_id = :t"), t)
        conn.execute(
            text(
                "UPDATE planes_preventivos SET created_at = :inicio, aprobado_at = :inicio + interval '1 day'"
                " WHERE tenant_id = :t AND aprobado_at IS NOT NULL"
            ),
            t,
        )
        conn.execute(
            text(
                "UPDATE mantenimientos_ejecutados SET created_at = (fecha_ejecucion + time '17:30') AT TIME ZONE 'America/Bogota'"
                " WHERE tenant_id = :t"
            ),
            t,
        )
        conn.execute(
            text(
                "UPDATE recomendaciones_tecnicas r SET created_at = m.created_at, updated_at = m.created_at"
                " FROM mantenimientos_ejecutados m WHERE r.mantenimiento_origen_id = m.id AND r.tenant_id = :t"
            ),
            t,
        )
        for nov_id, (reporte, atencion, cierre) in tiempos.items():
            conn.execute(
                text(
                    "UPDATE novedades SET fecha_reporte = :r, created_at = :r,"
                    " fecha_atencion = CASE WHEN fecha_atencion IS NULL THEN NULL ELSE COALESCE(CAST(:a AS timestamptz), fecha_atencion) END,"
                    " cerrada_at = CASE WHEN cerrada_at IS NULL THEN NULL ELSE COALESCE(CAST(:c AS timestamptz), cerrada_at) END,"
                    " updated_at = COALESCE(CAST(:c AS timestamptz), CAST(:a AS timestamptz), :r) WHERE id = :id"
                ),
                {"r": reporte, "a": atencion, "c": cierre, "id": nov_id},
            )
        # La auditoría de creación acompaña a la fecha del registro
        for tabla, columna in (
            ("activos", "created_at"),
            ("mantenimientos_ejecutados", "created_at"),
            ("recomendaciones_tecnicas", "created_at"),
            ("novedades", "fecha_reporte"),
            ("contratistas", "created_at"),
            ("planes_preventivos", "created_at"),
        ):
            conn.execute(
                text(
                    f"UPDATE auditoria_activos a SET fecha_hora = x.{columna} FROM {tabla} x"  # noqa: S608 (nombres fijos)
                    " WHERE a.entidad_id = x.id AND a.accion = 'CREACION' AND a.tenant_id = :t"
                ),
                t,
            )
        conn.execute(
            text(
                "UPDATE auditoria_activos a SET fecha_hora = COALESCE(n.cerrada_at, n.fecha_atencion, n.fecha_reporte)"
                " FROM novedades n WHERE a.entidad_id = n.id AND a.accion <> 'CREACION' AND a.tenant_id = :t"
            ),
            t,
        )
        conn.execute(
            text(
                "UPDATE auditoria_activos a SET fecha_hora = (m.fecha_ejecucion + time '17:30') AT TIME ZONE 'America/Bogota'"
                " FROM mantenimientos_ejecutados m WHERE a.entidad = 'actividad' AND a.tenant_id = :t"
                "   AND a.entidad_id = m.actividad_id AND a.accion <> 'CREACION' AND m.anulado_at IS NULL"
            ),
            t,
        )


async def generar() -> None:
    async with SessionLocal() as db:
        tenant_id = await db.scalar(select(Tenant.id).where(Tenant.slug == TENANT))
        if tenant_id is None:
            raise SystemExit("No existe la copropiedad de demo: ejecute primero python -m app.scripts.seed")
        await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
        if await db.scalar(select(func.count()).select_from(Activo)):
            print("Ya hay activos en la demo: no se generan de nuevo.")
            return
        usuarios = {
            rol: uid
            for uid, rol in await db.execute(
                select(User.id, Membership.role)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.tenant_id == tenant_id,
                    Membership.role.in_([R.ADMIN, R.AUXILIAR, R.CONTABILIDAD, R.MANTENIMIENTO]),
                )
            )
        }
        if len(usuarios) < 4:
            raise SystemExit(
                "Faltan usuarios demo (admin, recepción, contabilidad, técnico): ejecute python -m app.scripts.seed"
            )
        demo = Demo(db, tenant_id, usuarios)
        await demo.ejecutar()

    ajustar_fechas(tenant_id, demo.inicio, demo.tiempos_novedad)

    async with SessionLocal() as db:
        await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
        conteos = {
            t: await db.scalar(text(f"SELECT count(*) FROM {t}"))  # noqa: S608 (nombres fijos)
            for t in (
                "activos",
                "planes_preventivos",
                "actividades_programadas",
                "mantenimientos_ejecutados",
                "novedades",
                "recomendaciones_tecnicas",
                "lecturas_uso",
            )
        }
        semaforo = dict(
            (await db.execute(text("SELECT semaforo, count(*) FROM v_semaforo_actividades GROUP BY 1"))).all()
        )
        print("Activos de demo:", ", ".join(f"{k}={v}" for k, v in conteos.items()))
        print("Semáforo de actividades pendientes:", ", ".join(f"{k}={v}" for k, v in sorted(semaforo.items())))


def main() -> None:
    asyncio.run(generar())
