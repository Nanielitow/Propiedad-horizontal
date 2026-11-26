"""Panel consolidado de quien administra varias copropiedades."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.services import consolidado

router = APIRouter(prefix="/mis-copropiedades", tags=["panel consolidado"])


@router.get("/resumen", response_model=consolidado.ResumenConsolidado)
async def resumen(user: CurrentUser, db: DbSession) -> consolidado.ResumenConsolidado:
    """Indicadores de cada copropiedad donde la persona es administradora (vacío si no administra ninguna)."""
    return await consolidado.resumen(db, user.id)
