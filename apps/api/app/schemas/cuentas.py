import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import MIN_PASSWORD
from app.models.enums import UserRole

Email = Annotated[str, Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Nombre = Annotated[str, Field(min_length=2, max_length=200)]
Clave = Annotated[str, Field(min_length=MIN_PASSWORD, max_length=128)]

ETIQUETA_ROL = {
    UserRole.ADMIN: "Administrador",
    UserRole.RESIDENTE: "Residente",
    UserRole.AUXILIAR: "Recepción",
    UserRole.CONTABILIDAD: "Contabilidad",
    UserRole.CONSEJO: "Consejo de administración",
    UserRole.MANTENIMIENTO: "Mantenimiento",
}


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _clave_razonable(v: str) -> str:
    if len(set(v)) < 4:
        raise ValueError("La contraseña es demasiado simple: combine letras, números o símbolos")
    return v


# --- Enlaces y contraseña -----------------------------------------------------------------------
class EnlaceOut(BaseModel):
    tipo: Literal["INVITACION", "RECUPERACION"]
    email: str
    nombre: str
    copropiedad: str | None
    requiere_politica: bool  # aún no ha aceptado la política de tratamiento de datos vigente
    politica_version: str


class EnlaceIn(_Base):
    token: Annotated[str, Field(min_length=20, max_length=200)]


class ActivarIn(_Base):
    token: Annotated[str, Field(min_length=20, max_length=200)]
    password: Clave
    acepta_politica: bool

    _v = field_validator("password")(_clave_razonable)


class RestablecerIn(_Base):
    token: Annotated[str, Field(min_length=20, max_length=200)]
    password: Clave

    _v = field_validator("password")(_clave_razonable)


class RecuperarIn(_Base):
    email: Email


class CambiarClaveIn(_Base):
    actual: Annotated[str, Field(min_length=1, max_length=256)]
    nueva: Clave

    _v = field_validator("nueva")(_clave_razonable)


# --- Usuarios de una copropiedad --------------------------------------------------------------------
class InvitacionIn(_Base):
    email: Email
    nombre: Nombre
    rol: UserRole
    persona_id: uuid.UUID | None = None  # residente o propietario del censo al que se le da acceso al portal

    @field_validator("email")
    @classmethod
    def _minusculas(cls, v: str) -> str:
        return v.lower()


class CambioRolIn(_Base):
    rol: UserRole


class UsuarioCopropiedad(BaseModel):
    user_id: uuid.UUID
    nombre: str
    email: str
    rol: UserRole
    rol_etiqueta: str
    estado: Literal["ACTIVO", "INVITADO", "DESACTIVADO"]
    ultimo_ingreso: datetime | None
    agregado_en: datetime
    es_usted: bool


class InvitacionOut(BaseModel):
    usuario: UsuarioCopropiedad
    nuevo: bool  # True: se creó la cuenta y se envió el enlace para definir la clave
    correo_enviado: bool


# --- Plataforma (dueño) ----------------------------------------------------------------------------------
class CopropiedadIn(_Base):
    nombre: Annotated[str, Field(min_length=3, max_length=200)]
    nit: Annotated[str | None, Field(max_length=30)] = None
    ciudad: Annotated[str | None, Field(max_length=100)] = None
    direccion: Annotated[str | None, Field(max_length=200)] = None
    admin_email: Email
    admin_nombre: Nombre

    @field_validator("admin_email")
    @classmethod
    def _minusculas(cls, v: str) -> str:
        return v.lower()


class CopropiedadUpdate(_Base):
    nombre: Annotated[str | None, Field(min_length=3, max_length=200)] = None
    nit: Annotated[str | None, Field(max_length=30)] = None
    ciudad: Annotated[str | None, Field(max_length=100)] = None
    direccion: Annotated[str | None, Field(max_length=200)] = None
    is_demo: bool | None = None


class CopropiedadOut(BaseModel):
    id: uuid.UUID
    nombre: str
    slug: str
    nit: str | None
    ciudad: str | None
    direccion: str | None
    is_demo: bool
    creada_en: datetime
    unidades: int
    usuarios: int
    administradores: int
    invitaciones_pendientes: int  # administradores que aún no activan su cuenta


class CopropiedadCreada(BaseModel):
    copropiedad: CopropiedadOut
    administrador_nuevo: bool
    correo_enviado: bool
    enlace_invitacion: str | None  # el mismo del correo; None si el administrador ya tenía cuenta


class EnlaceInvitacion(BaseModel):
    """Enlace de activación de un administrador invitado, para que el dueño lo envíe él mismo (p. ej. WhatsApp)."""

    nombre: str
    email: str
    enlace: str
