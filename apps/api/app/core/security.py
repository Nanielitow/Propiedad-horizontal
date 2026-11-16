import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_hasher = PasswordHasher()  # argon2id con parámetros por defecto de OWASP
# Hash señuelo: si el email no existe se verifica igual contra él, para que el
# tiempo de respuesta no revele qué emails están registrados.
_DUMMY_HASH = _hasher.hash("timing-attack-mitigation")

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def burn_verification_time(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    settings = get_settings()
    ttl = timedelta(minutes=settings.jwt_access_ttl_minutes)
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "type": "access", "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM), int(ttl.total_seconds())


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str, int]:
    """Token de larga duración para renovar el de acceso. Su `jti` se registra en
    Redis y se invalida al usarse (rotación): un token robado y ya usado no sirve."""
    settings = get_settings()
    ttl = timedelta(days=settings.jwt_refresh_ttl_days)
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    payload = {"sub": str(user_id), "type": "refresh", "jti": jti, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM), jti, int(ttl.total_seconds())


def decode_refresh_token(token: str) -> tuple[uuid.UUID, str]:
    payload = jwt.decode(
        token, get_settings().jwt_secret, algorithms=[_ALGORITHM], options={"require": ["exp", "sub", "jti"]}
    )
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Tipo de token incorrecto")
    try:
        return uuid.UUID(payload["sub"]), str(payload["jti"])
    except ValueError as exc:
        raise jwt.InvalidTokenError("sub inválido") from exc


def decode_access_token(token: str) -> uuid.UUID:
    """Lanza jwt.InvalidTokenError si el token es inválido o expiró."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGORITHM], options={"require": ["exp", "sub"]})
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Tipo de token incorrecto")
    try:
        return uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise jwt.InvalidTokenError("sub inválido") from exc
