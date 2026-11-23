"""Traducción de errores de dominio y de la base de datos a respuestas HTTP.

Las reglas críticas viven también en PostgreSQL (triggers, CHECK, RLS). Si una
petición las viola, el error de la base se convierte en un 4xx con un mensaje
útil en lugar de un 500: los triggers del módulo de recaudos ya lanzan mensajes
en español pensados para el usuario.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.services.recaudos.dominio import NoEncontrado, PermisoDenegado, RecaudoError, TransicionInvalida

log = logging.getLogger(__name__)

_POR_TIPO: list[tuple[type[RecaudoError], int]] = [
    (PermisoDenegado, status.HTTP_403_FORBIDDEN),
    (NoEncontrado, status.HTTP_404_NOT_FOUND),
    (TransicionInvalida, status.HTTP_409_CONFLICT),
]


def _sqlstate(exc: DBAPIError) -> str | None:
    orig = exc.orig
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def _mensaje_db(exc: DBAPIError) -> str:
    """Mensaje primario de PostgreSQL, sin el prefijo de la clase de excepción del driver."""
    causa = getattr(exc.orig, "__cause__", None) or exc.orig
    texto = getattr(causa, "message", None) or str(causa)
    return str(texto).splitlines()[0].split(": ", 1)[-1] if "<class" in str(texto) else str(texto).splitlines()[0]


def traducir_error_db(exc: DBAPIError) -> tuple[int, str] | None:
    """(código HTTP, mensaje) para los errores de PostgreSQL que son de negocio; None si es un fallo real."""
    estado = _sqlstate(exc)
    mensaje = _mensaje_db(exc)
    if estado == "42501":  # insufficient_privilege: RLS, permiso de tabla o trigger del módulo
        tecnico = "row-level security" in mensaje or "permission denied" in mensaje
        return status.HTTP_403_FORBIDDEN, "Su rol no permite esta operación" if tecnico else mensaje
    if estado == "23514":  # check_violation: regla de negocio de un trigger o un CHECK de tabla
        tecnico = "violates check constraint" in mensaje
        return status.HTTP_409_CONFLICT, "Los datos no cumplen las reglas del registro" if tecnico else mensaje
    if estado == "23505":
        return status.HTTP_409_CONFLICT, "Ya existe un registro con esos datos"
    if estado == "23503":
        return status.HTTP_422_UNPROCESSABLE_ENTITY, "Hace referencia a un registro inexistente"
    return None


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(RecaudoError)
    async def _dominio(_: Request, exc: RecaudoError) -> JSONResponse:
        codigo = next((c for tipo, c in _POR_TIPO if isinstance(exc, tipo)), status.HTTP_400_BAD_REQUEST)
        return JSONResponse(status_code=codigo, content={"detail": str(exc)})

    @app.exception_handler(DBAPIError)
    async def _base_de_datos(request: Request, exc: DBAPIError) -> JSONResponse:
        if (traducido := traducir_error_db(exc)) is not None:
            codigo, detalle = traducido
            return JSONResponse(status_code=codigo, content={"detail": detalle})
        log.exception("error de base de datos no controlado en %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Error interno"})
