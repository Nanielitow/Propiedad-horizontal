"""Respaldos de la base de datos en el almacenamiento (R2 en producción).

Cada noche se hace un `pg_dump` completo (formato custom, comprimido) con el rol dueño del esquema, que ignora RLS:
con `app_user` las tablas saldrían vacías. Se verifica que el archivo se pueda leer (`pg_restore --list`) antes de
subirlo. Retención: diarios 30 días; el del día 1 de cada mes se guarda también como mensual durante 12 meses.

Las credenciales nunca se escriben en registros ni en mensajes de error: la conexión viaja en variables de entorno de
libpq, no en la línea de comandos. Restaurar: docs/RESPALDOS.md.
"""

import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.services.storage.s3 import get_storage

log = logging.getLogger(__name__)

PREFIJO = "respaldos/"
DIARIOS = f"{PREFIJO}diarios/"
MENSUALES = f"{PREFIJO}mensuales/"
RETENER_DIARIOS = timedelta(days=30)
RETENER_MENSUALES_MESES = 12
TZ = ZoneInfo("America/Bogota")
_FECHA = re.compile(r"ph-(\d{4})-(\d{2})(?:-(\d{2}))?")


class RespaldoError(RuntimeError):
    """Falla del respaldo. El mensaje es seguro de mostrar (sin credenciales)."""


@dataclass(frozen=True)
class Respaldo:
    clave: str
    tamano: int
    fecha: datetime
    tipo: str  # "diario" | "mensual"


def _entorno_libpq(url: str) -> dict[str, str]:
    """Convierte la URL de SQLAlchemy en variables PG* de libpq (así la contraseña no aparece en `ps` ni en logs)."""
    u = urlsplit(
        url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")
    )
    if not u.hostname or not u.path.strip("/"):
        raise RespaldoError("La URL de la base de datos para respaldos no es válida")
    env = {
        "PGHOST": u.hostname,
        "PGPORT": str(u.port or 5432),
        "PGDATABASE": u.path.lstrip("/"),
        "PGUSER": unquote(u.username or ""),
        "PGPASSWORD": unquote(u.password or ""),
        "PGCONNECT_TIMEOUT": "20",
    }
    for parte in (u.query or "").split("&"):
        clave, _, valor = parte.partition("=")
        if clave in {"sslmode", "ssl"}:
            env["PGSSLMODE"] = "require" if valor in {"require", "true", "1"} else valor
    return env


def _ejecutar(cmd: list[str], env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 - comando fijo, sin shell
            cmd, env={**os.environ, **env}, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise RespaldoError(f"No está instalado {cmd[0]} en el servidor") from exc
    except subprocess.TimeoutExpired as exc:
        raise RespaldoError(f"{cmd[0]} tardó más de {timeout // 60} minutos") from exc


def _limpiar(texto: str, env: dict[str, str]) -> str:
    """Quita cualquier rastro de la contraseña o el usuario de un mensaje de error de pg_dump."""
    for secreto in (env.get("PGPASSWORD"), env.get("PGUSER")):
        if secreto:
            texto = texto.replace(secreto, "***")
    return texto.strip()[-500:]


def crear_respaldo(ahora: datetime | None = None) -> dict[str, object]:
    """Hace, verifica y sube un respaldo. Devuelve un resumen. Lanza RespaldoError si algo falla."""
    s = get_settings()
    url = s.migrations_database_url
    if not url:
        raise RespaldoError("Falta MIGRATIONS_DATABASE_URL (rol dueño): sin él no hay con qué respaldar")
    env = _entorno_libpq(url)
    ahora = (ahora or datetime.now(UTC)).astimezone(TZ)
    nombre = f"ph-{ahora:%Y-%m-%d-%H%M}.dump"
    inicio = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        archivo = Path(tmp) / nombre
        dump = _ejecutar(
            ["pg_dump", "--format=custom", "--compress=6", "--no-password", f"--file={archivo}"], env, timeout=1800
        )
        if dump.returncode != 0 or not archivo.exists():
            raise RespaldoError(f"pg_dump falló: {_limpiar(dump.stderr, env) or 'sin detalle'}")
        lista = _ejecutar(["pg_restore", "--list", str(archivo)], {}, timeout=300)
        entradas = sum(1 for linea in lista.stdout.splitlines() if linea and not linea.startswith(";"))
        tablas = sum(1 for linea in lista.stdout.splitlines() if " TABLE DATA " in linea)
        if lista.returncode != 0 or tablas == 0:
            raise RespaldoError("El archivo del respaldo no se pudo leer: no se subió")
        tamano = archivo.stat().st_size
        storage = get_storage()
        clave = f"{DIARIOS}{nombre}"
        storage.upload(archivo, clave, content_type="application/octet-stream")
        mensual = None
        if ahora.day == 1:
            mensual = f"{MENSUALES}ph-{ahora:%Y-%m}.dump"
            storage.upload(archivo, mensual, content_type="application/octet-stream")
    borrados = aplicar_retencion(ahora.date())
    resumen = {
        "clave": clave,
        "mensual": mensual,
        "tamano_bytes": tamano,
        "tablas": tablas,
        "entradas": entradas,
        "segundos": round(time.monotonic() - inicio, 1),
        "borrados": borrados,
    }
    log.info("respaldo listo: %s (%s KB, %s tablas)", clave, tamano // 1024, tablas)
    return resumen


def fecha_de(clave: str) -> date | None:
    m = _FECHA.search(clave)
    if not m:
        return None
    anio, mes, dia = m.groups()
    return date(int(anio), int(mes), int(dia or 1))


def claves_vencidas(claves: list[str], hoy: date) -> list[str]:
    """Qué respaldos ya cumplieron su tiempo de retención (función pura, para probarla sin almacenamiento)."""
    vencidas = []
    # Mensuales: se conservan los de los últimos 12 meses (el mismo mes del año pasado ya sale)
    meses = hoy.year * 12 + (hoy.month - 1) - (RETENER_MENSUALES_MESES - 1)  # el mes actual cuenta como uno de los 12
    limite_mensual = date(meses // 12, meses % 12 + 1, 1)
    for clave in claves:
        f = fecha_de(clave)
        if f is None:
            continue
        if clave.startswith(DIARIOS) and f < hoy - RETENER_DIARIOS:
            vencidas.append(clave)
        elif clave.startswith(MENSUALES) and f < limite_mensual:
            vencidas.append(clave)
    return vencidas


def aplicar_retencion(hoy: date) -> int:
    storage = get_storage()
    vencidas = claves_vencidas(storage.list_keys(PREFIJO), hoy)
    if vencidas:
        storage.delete_many(vencidas)
    return len(vencidas)


def listar() -> list[Respaldo]:
    salida = []
    for clave, tamano, modificado in get_storage().list_objects(PREFIJO):
        if not clave.endswith(".dump"):
            continue
        salida.append(Respaldo(clave, tamano, modificado, "mensual" if clave.startswith(MENSUALES) else "diario"))
    return sorted(salida, key=lambda r: r.fecha, reverse=True)


def es_clave_valida(clave: str) -> bool:
    return (
        clave.startswith((DIARIOS, MENSUALES))
        and clave.endswith(".dump")
        and ".." not in clave
        and re.fullmatch(r"[A-Za-z0-9/_.-]+", clave) is not None
    )
