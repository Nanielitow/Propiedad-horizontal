"""API del módulo de unidades, copropietarios, residentes y vehículos (docs/UNIDADES.md §4).

Dentro de cada router, las rutas con segmento fijo (/resumen, /importar, /exportar)
se declaran antes que /{unidad_id}, que de otro modo las capturaría.
"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DbSession, TenantCtx
from app.core.rate_limit import DEMO_UNIDADES_PER_IP_DAY, UNIDADES_WRITES_PER_MINUTE, enforce, enforce_demo
from app.models.enums import OcupacionUnidad, RelacionUnidad, TipoUnidad
from app.schemas.unidades import (
    CerrarVinculoIn,
    MotivoIn,
    PersonaIn,
    PersonaUpdate,
    UnidadIn,
    UnidadUpdate,
    VehiculoIn,
    VehiculoUpdate,
    VinculoIn,
    VinculoUpdate,
)
from app.schemas.unidades_out import (
    PersonaDetalle,
    PersonasPagina,
    PlacaOut,
    ResumenUnidades,
    UnidadDetalle,
    UnidadesPagina,
    VehiculoOut,
)
from app.services.comun import ValidacionError
from app.services.recaudos import exportar
from app.services.unidades import consultas, gestion, importar, reportes
from app.services.unidades.consultas import FiltroUnidades

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME = {"xlsx": MIME_XLSX, "pdf": "application/pdf"}

unidades_router = APIRouter(prefix="/tenants/{tenant_id}/unidades", tags=["unidades"])
personas_router = APIRouter(prefix="/tenants/{tenant_id}/personas", tags=["unidades: personas"])
otros_router = APIRouter(prefix="/tenants/{tenant_id}", tags=["unidades"])


async def limitar_escritura(request: Request, ctx: TenantCtx) -> None:
    await enforce(request, UNIDADES_WRITES_PER_MINUTE, str(ctx.user_id))
    await enforce_demo(request, DEMO_UNIDADES_PER_IP_DAY, demo=ctx.is_demo)


async def _leer_excel(archivo: UploadFile) -> tuple[str, bytes]:
    nombre = (archivo.filename or "censo.xlsx").replace("\\", "/").split("/")[-1][:200]
    if not nombre.lower().endswith(".xlsx"):
        raise ValidacionError("Suba un archivo de Excel (.xlsx). Si tiene .xls o .csv, ábralo y guárdelo como .xlsx")
    contenido = await archivo.read(importar.MAX_BYTES + 1)
    if len(contenido) > importar.MAX_BYTES:
        raise ValidacionError("El archivo supera 5 MB")
    return nombre, contenido


# --- Unidades: rutas fijas ---------------------------------------------------------


@unidades_router.get("", response_model=UnidadesPagina)
async def listar_unidades(
    ctx: TenantCtx,
    db: DbSession,
    torre: Annotated[str | None, Query(max_length=20)] = None,
    tipo: TipoUnidad | None = None,
    ocupacion: OcupacionUnidad | None = None,
    texto: Annotated[str | None, Query(max_length=100)] = None,
    incluir_inactivas: bool = False,
    solo_principales: bool = False,
    sin_propietario: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> UnidadesPagina:
    filtro = FiltroUnidades(torre, tipo, ocupacion, texto, incluir_inactivas, solo_principales, sin_propietario)
    return await consultas.listar_unidades(db, ctx, filtro, page=page, page_size=page_size)


@unidades_router.post("", response_model=UnidadDetalle, status_code=status.HTTP_201_CREATED)
async def crear_unidad(body: UnidadIn, request: Request, ctx: TenantCtx, db: DbSession) -> UnidadDetalle:
    await limitar_escritura(request, ctx)
    u = await gestion.crear_unidad(db, ctx, body)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, u.id)


@unidades_router.get("/resumen", response_model=ResumenUnidades)
async def resumen(ctx: TenantCtx, db: DbSession) -> ResumenUnidades:
    """Totales por tipo y ocupación, suma de coeficientes y unidades sin propietario."""
    return await consultas.resumen(db, ctx)


@unidades_router.get("/importar/plantilla")
async def plantilla(ctx: TenantCtx) -> Response:
    del ctx  # solo exige pertenecer a la copropiedad
    datos = await run_in_threadpool(importar.plantilla)
    return Response(
        content=datos,
        media_type=MIME_XLSX,
        headers={"Content-Disposition": 'attachment; filename="plantilla-censo.xlsx"'},
    )


@unidades_router.post("/importar/previa", response_model=None)
async def importar_previa(
    request: Request, ctx: TenantCtx, db: DbSession, archivo: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    """Lee el Excel y devuelve lo que haría, sin guardar nada."""
    await enforce(request, UNIDADES_WRITES_PER_MINUTE, str(ctx.user_id))
    nombre, contenido = await _leer_excel(archivo)
    plan = await importar.previsualizar(db, ctx, nombre, contenido)  # solo lee: no hay nada que revertir
    return plan.a_json()


@unidades_router.post("/importar/confirmar", response_model=None)
async def importar_confirmar(
    request: Request,
    ctx: TenantCtx,
    db: DbSession,
    archivo: Annotated[UploadFile, File()],
    sha256: Annotated[str, Form(pattern=r"^[0-9a-f]{64}$")],
) -> dict[str, Any]:
    """Aplica el archivo revisado en la vista previa (mismo hash), todo o nada."""
    await limitar_escritura(request, ctx)
    nombre, contenido = await _leer_excel(archivo)
    r = await importar.aplicar(db, ctx, nombre, contenido, sha256)
    await db.commit()
    return {
        "id": str(r.id),
        "archivo": r.archivo_nombre,
        "unidades_creadas": r.unidades_creadas,
        "unidades_actualizadas": r.unidades_actualizadas,
        "personas_creadas": r.personas_creadas,
        "personas_actualizadas": r.personas_actualizadas,
        "vinculos_creados": r.vinculos_creados,
        "vehiculos_creados": r.vehiculos_creados,
        "advertencias": r.advertencias,
    }


@unidades_router.get("/exportar")
async def exportar_censo(ctx: TenantCtx, db: DbSession, formato: Literal["xlsx", "pdf"] = "xlsx") -> Response:
    r = await reportes.censo(db, ctx)
    datos = await run_in_threadpool(exportar.a_pdf if formato == "pdf" else exportar.a_excel, r)
    return Response(
        content=datos,
        media_type=MIME[formato],
        headers={"Content-Disposition": f'attachment; filename="censo-{r.hasta.isoformat()}.{formato}"'},
    )


# --- Unidades: por id --------------------------------------------------------------


@unidades_router.get("/{unidad_id}", response_model=UnidadDetalle)
async def ficha_unidad(unidad_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> UnidadDetalle:
    return await consultas.ficha_unidad(db, ctx, unidad_id)


@unidades_router.patch("/{unidad_id}", response_model=UnidadDetalle)
async def editar_unidad(
    unidad_id: uuid.UUID, body: UnidadUpdate, request: Request, ctx: TenantCtx, db: DbSession
) -> UnidadDetalle:
    await limitar_escritura(request, ctx)
    await gestion.editar_unidad(db, ctx, unidad_id, body)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, unidad_id)


@unidades_router.post("/{unidad_id}/desactivar", response_model=UnidadDetalle)
async def desactivar_unidad(
    unidad_id: uuid.UUID, body: MotivoIn, request: Request, ctx: TenantCtx, db: DbSession
) -> UnidadDetalle:
    await limitar_escritura(request, ctx)
    await gestion.desactivar_unidad(db, ctx, unidad_id, body.motivo)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, unidad_id)


@unidades_router.post("/{unidad_id}/reactivar", response_model=UnidadDetalle)
async def reactivar_unidad(
    unidad_id: uuid.UUID, body: MotivoIn, request: Request, ctx: TenantCtx, db: DbSession
) -> UnidadDetalle:
    await limitar_escritura(request, ctx)
    await gestion.reactivar_unidad(db, ctx, unidad_id, body.motivo)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, unidad_id)


@unidades_router.post("/{unidad_id}/vinculos", response_model=UnidadDetalle, status_code=status.HTTP_201_CREATED)
async def vincular(
    unidad_id: uuid.UUID, body: VinculoIn, request: Request, ctx: TenantCtx, db: DbSession
) -> UnidadDetalle:
    """Vincula una persona existente o crea una nueva en el mismo paso."""
    await limitar_escritura(request, ctx)
    await gestion.vincular(db, ctx, unidad_id, body)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, unidad_id)


@unidades_router.get("/{unidad_id}/vehiculos", response_model=list[VehiculoOut])
async def vehiculos_de_unidad(unidad_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> list[VehiculoOut]:
    return await consultas.vehiculos_de_unidad(db, ctx, unidad_id)


@unidades_router.post("/{unidad_id}/vehiculos", response_model=UnidadDetalle, status_code=status.HTTP_201_CREATED)
async def registrar_vehiculo(
    unidad_id: uuid.UUID, body: VehiculoIn, request: Request, ctx: TenantCtx, db: DbSession
) -> UnidadDetalle:
    await limitar_escritura(request, ctx)
    await gestion.registrar_vehiculo(db, ctx, unidad_id, body)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, unidad_id)


# --- Vínculos, vehículos, placas y "mi unidad" ---------------------------------------


@otros_router.patch("/vinculos/{vinculo_id}", response_model=UnidadDetalle)
async def editar_vinculo(
    vinculo_id: uuid.UUID, body: VinculoUpdate, request: Request, ctx: TenantCtx, db: DbSession
) -> UnidadDetalle:
    await limitar_escritura(request, ctx)
    v = await gestion.editar_vinculo(db, ctx, vinculo_id, body)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, v.unidad_id)


@otros_router.post("/vinculos/{vinculo_id}/cerrar", response_model=UnidadDetalle)
async def cerrar_vinculo(
    vinculo_id: uuid.UUID, body: CerrarVinculoIn, request: Request, ctx: TenantCtx, db: DbSession
) -> UnidadDetalle:
    """Venta, fin del arriendo, mudanza: el vínculo pasa al historial."""
    await limitar_escritura(request, ctx)
    v = await gestion.cerrar_vinculo(db, ctx, vinculo_id, body)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, v.unidad_id)


@otros_router.patch("/vehiculos/{vehiculo_id}", response_model=UnidadDetalle)
async def editar_vehiculo(
    vehiculo_id: uuid.UUID, body: VehiculoUpdate, request: Request, ctx: TenantCtx, db: DbSession
) -> UnidadDetalle:
    await limitar_escritura(request, ctx)
    v = await gestion.editar_vehiculo(db, ctx, vehiculo_id, body)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, v.unidad_id)


@otros_router.post("/vehiculos/{vehiculo_id}/retirar", response_model=UnidadDetalle)
async def retirar_vehiculo(
    vehiculo_id: uuid.UUID, body: MotivoIn, request: Request, ctx: TenantCtx, db: DbSession
) -> UnidadDetalle:
    await limitar_escritura(request, ctx)
    v = await gestion.retirar_vehiculo(db, ctx, vehiculo_id, body.motivo)
    await db.commit()
    return await consultas.ficha_unidad(db, ctx, v.unidad_id)


@otros_router.get("/vehiculos/placa/{placa}", response_model=PlacaOut)
async def buscar_placa(placa: str, ctx: TenantCtx, db: DbSession) -> PlacaOut:
    """¿Residente o visitante? La usa recepción al registrar el parqueadero."""
    try:
        return await consultas.buscar_placa(db, ctx, placa)
    except ValueError as e:
        raise ValidacionError(str(e)) from None


@otros_router.get("/mi-unidad", response_model=list[UnidadDetalle])
async def mi_unidad(ctx: TenantCtx, db: DbSession) -> list[UnidadDetalle]:
    """Para el residente: sus unidades, quién figura en ellas y sus vehículos."""
    return await consultas.mi_unidad(db, ctx)


# --- Personas ----------------------------------------------------------------------


@personas_router.get("", response_model=PersonasPagina)
async def directorio(
    ctx: TenantCtx,
    db: DbSession,
    texto: Annotated[str | None, Query(max_length=100)] = None,
    relacion: RelacionUnidad | None = None,
    incluir_inactivas: bool = False,
    sin_unidad: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PersonasPagina:
    return await consultas.directorio(
        db,
        ctx,
        texto=texto,
        relacion=relacion,
        incluir_inactivas=incluir_inactivas,
        sin_unidad=sin_unidad,
        page=page,
        page_size=page_size,
    )


@personas_router.post("", response_model=PersonaDetalle, status_code=status.HTTP_201_CREATED)
async def crear_persona(body: PersonaIn, request: Request, ctx: TenantCtx, db: DbSession) -> PersonaDetalle:
    await limitar_escritura(request, ctx)
    p = await gestion.crear_persona(db, ctx, body)
    await db.commit()
    return await consultas.ficha_persona(db, ctx, p.id)


@personas_router.get("/{persona_id}", response_model=PersonaDetalle)
async def ficha_persona(persona_id: uuid.UUID, ctx: TenantCtx, db: DbSession) -> PersonaDetalle:
    return await consultas.ficha_persona(db, ctx, persona_id)


@personas_router.patch("/{persona_id}", response_model=PersonaDetalle)
async def editar_persona(
    persona_id: uuid.UUID, body: PersonaUpdate, request: Request, ctx: TenantCtx, db: DbSession
) -> PersonaDetalle:
    await limitar_escritura(request, ctx)
    await gestion.editar_persona(db, ctx, persona_id, body)
    await db.commit()
    return await consultas.ficha_persona(db, ctx, persona_id)


@personas_router.post("/{persona_id}/desactivar", response_model=PersonaDetalle)
async def desactivar_persona(
    persona_id: uuid.UUID, body: MotivoIn, request: Request, ctx: TenantCtx, db: DbSession
) -> PersonaDetalle:
    await limitar_escritura(request, ctx)
    await gestion.desactivar_persona(db, ctx, persona_id, body.motivo)
    await db.commit()
    return await consultas.ficha_persona(db, ctx, persona_id)
