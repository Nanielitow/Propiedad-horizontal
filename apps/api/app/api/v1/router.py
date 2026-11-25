from fastapi import APIRouter

from app.api.v1 import (
    activos,
    activos_operacion,
    activos_panel,
    asambleas,
    auth,
    cartera,
    deadlines,
    documents,
    minutes,
    portal,
    quotes,
    recaudos,
    recaudos_caja,
    recaudos_panel,
    search,
    unidades,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(deadlines.router)
api_router.include_router(quotes.router)
api_router.include_router(minutes.router)
# Recaudos: las rutas con prefijo fijo (/caja, /entregas, /alertas...) van ANTES que
# las de /{recaudo_id}, que de otro modo capturarían esos segmentos.
api_router.include_router(recaudos_caja.router)
api_router.include_router(recaudos_panel.router)
api_router.include_router(recaudos.router)
# Activos: igual, /planes, /novedades, /qr... antes que /{activo_id}
api_router.include_router(activos_operacion.router)
api_router.include_router(activos_panel.router)
api_router.include_router(activos.router)
# Unidades, copropietarios y residentes
api_router.include_router(unidades.unidades_router)
api_router.include_router(unidades.personas_router)
api_router.include_router(unidades.otros_router)
# Cartera de cuotas de administración
api_router.include_router(cartera.router)
# Portal del residente: PQRS, circulares y reservas
api_router.include_router(portal.router)
# Asambleas de copropietarios
api_router.include_router(asambleas.router)
