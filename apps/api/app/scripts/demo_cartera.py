"""Datos de demostración de la cartera (Conjunto Residencial Los Pinos).

Doce meses de facturación construidos con los MISMOS casos de uso que la API, en orden
cronológico (emitir el mes, luego los pagos de ese mes), para que intereses, descuentos y
saldos a favor salgan coherentes por construcción:
  - presupuesto mensual de $42.000.000 repartido por coeficiente, vencimiento el día 10,
    5 % de descuento hasta el día 5 y 1,8 % mensual de mora;
  - perfiles de pago: puntuales con descuento (la mayoría), tardíos, morosos crónicos que
    abonan a medias, tres deudas largas (3, 6 y 9 meses) y un propietario que paga por adelantado;
  - una cuota extraordinaria (impermeabilización, $30.000.000 en 3 cuotas por coeficiente),
    una condonación de intereses aprobada por el consejo y un pago anulado;
  - Carlos Pérez (1-502) siempre al día: puede descargar su paz y salvo.

Uso: python -m app.scripts.demo cartera   (requiere `unidades`; no repite si ya hay periodos)
"""

import asyncio
import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import CargoCartera, ConceptoCartera, Membership, PeriodoCartera, Tenant, Unit
from app.models.enums import MedioPago, MetodoCuota, TipoAjuste, UserRole
from app.schemas.cartera import AjusteIn, ConfigIn, EmitirPeriodoIn, PagoIn
from app.services.cartera import comun, facturacion, pagos, paz_y_salvo
from app.services.cartera import dominio as d
from app.services.cartera.cargos import partir_en_cuotas
from app.services.comun import ActorSimple, hoy_bogota

TENANT = "los-pinos"
rng = random.Random(1653)  # noqa: S311 - datos de demo reproducibles (art. 1653 del Código Civil)
D = Decimal


def _meses(hoy: date, n: int) -> list[date]:
    primero = hoy.replace(day=1)
    salida = []
    for _ in range(n):
        salida.append(primero)
        primero = (primero - timedelta(days=1)).replace(day=1)
    return list(reversed(salida))


class Demo:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID, admin: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.admin = ActorSimple(tenant_id, admin, UserRole.ADMIN)
        self.hoy = hoy_bogota()
        self.n_ref = 0

    async def _admin(self) -> ActorSimple:
        await set_rls_context(self.db, tenant_id=self.tenant_id, user_id=self.admin.user_id, role="ADMIN")
        return self.admin

    def _ref(self, fecha: date) -> str:
        self.n_ref += 1
        return f"TRF{fecha:%Y%m%d}{self.n_ref:04d}"

    async def pagar(self, unidad: uuid.UUID, valor: Decimal, fecha: date) -> pagos.ResultadoPago | None:
        if valor <= 0 or fecha > self.hoy:
            return None
        admin = await self._admin()
        medio = rng.choices([MedioPago.TRANSFERENCIA, MedioPago.EFECTIVO, MedioPago.CONSIGNACION], [70, 15, 15])[0]
        return await pagos.registrar_pago(
            self.db,
            admin,
            PagoIn(
                unidad_id=unidad,
                fecha_pago=fecha,
                valor=valor,
                medio_pago=medio,
                referencia=None if medio == MedioPago.EFECTIVO else self._ref(fecha),
            ),
        )

    async def ejecutar(self) -> None:
        admin = await self._admin()
        await self.db.execute(text("SELECT seed_conceptos_cartera(:t)"), {"t": self.tenant_id})
        await comun.guardar_config(
            self.db,
            admin,
            ConfigIn(
                metodo=MetodoCuota.COEFICIENTE,
                presupuesto_mensual=D("42000000"),
                dia_vencimiento=10,
                descuento_pct=D("5"),
                dia_limite_descuento=5,
                tasa_mora_mensual=D("1.8"),
                nota_cuenta_cobro="Pague por transferencia a la cuenta de ahorros 123-456789-01 de Bancolombia.",
            ),
        )
        unidades = list(await self.db.scalars(select(Unit).where(Unit.activa.is_(True), Unit.coefficient.is_not(None))))
        # Perfiles de pago
        perfiles: dict[uuid.UUID, str] = {}
        etiquetas = {u.id: u.etiqueta for u in unidades}
        for u in unidades:
            perfiles[u.id] = rng.choices(["puntual", "tardio", "cronico"], [72, 18, 10])[0]
        especiales = {"1-502": "puntual", "2-603": "deuda9", "1-204": "deuda6", "2-101": "deuda3", "1-301": "adelanta"}
        por_etiqueta = {v: k for k, v in etiquetas.items()}
        for et, perfil in especiales.items():
            if et in por_etiqueta:
                perfiles[por_etiqueta[et]] = perfil

        meses = _meses(self.hoy, 12)
        extra = await comun.concepto(self.db, admin, codigo="EXTRAORDINARIA")
        for i, mes in enumerate(meses):
            admin = await self._admin()
            await facturacion.emitir(self.db, admin, EmitirPeriodoIn(anio=mes.year, mes=mes.month, fecha_emision=mes))
            if i == 8:  # cuota extraordinaria aprobada en la asamblea (3 cuotas mensuales)
                await self._extraordinaria(unidades, extra, mes)
            restantes = 11 - i  # meses que faltan hasta el actual
            for u in unidades:
                await self._pagos_del_mes(u.id, perfiles[u.id], mes, restantes)

        await self._condonacion_y_anulacion(por_etiqueta)
        admin = await self._admin()
        if "1-502" in por_etiqueta:
            await paz_y_salvo.emitir(self.db, admin, por_etiqueta["1-502"])

    async def _extraordinaria(self, unidades: list[Unit], concepto: ConceptoCartera, mes: date) -> None:
        """Como la crearía el servicio, pero con fecha pasada (el servicio no admite vencimientos pasados)."""
        suma = sum((u.coefficient for u in unidades if u.coefficient), D(0))
        for u in unidades:
            total = d.redondear(D("30000000") * (u.coefficient or 0) / suma, 100)
            rid, rnombre = await comun.responsable(self.db, u.id)
            for k, valor in enumerate(partir_en_cuotas(total, 3, 100)):
                venc = date(mes.year + (mes.month + k - 1) // 12, (mes.month + k - 1) % 12 + 1, 10)
                self.db.add(
                    CargoCartera(
                        id=uuid.uuid4(),
                        tenant_id=self.tenant_id,
                        unidad_id=u.id,
                        concepto_id=concepto.id,
                        descripcion=f"Impermeabilización de cubiertas (cuota {k + 1} de 3)",
                        valor=valor,
                        fecha_causacion=mes,
                        fecha_vencimiento=venc,
                        genera_interes=True,
                        responsable_persona_id=rid,
                        responsable_nombre=rnombre,
                        creado_por_id=self.admin.user_id,
                    )
                )
        await self.db.flush()

    async def _vencido_hasta(self, unidad: uuid.UUID, fecha: date) -> Decimal:
        """Lo que debe pagar para quedar al día con lo que vence hasta `fecha` (fin del mes)."""
        pend = await comun.pendientes(self.db, unidad)
        return sum((c.saldo for c in pend if c.fecha_vencimiento <= fecha), D(0))

    async def _pagos_del_mes(self, unidad: uuid.UUID, perfil: str, mes: date, restantes: int) -> None:
        fin = (mes.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        pend = await comun.pendientes(self.db, unidad)
        cuota = next((c for c in pend if c.descuento_pct and c.fecha_causacion == mes), None)
        deuda = await self._vencido_hasta(unidad, fin)
        if perfil in ("puntual", "adelanta"):
            dia = mes + timedelta(days=rng.randint(0, 4))
            desc = d.descuento(cuota.valor, cuota.descuento_pct) if cuota and cuota.descuento_pct else D(0)
            extra = cuota.valor * 2 if perfil == "adelanta" and mes.month in (1, 7) else D(0)  # anticipa dos meses
            await self.pagar(unidad, deuda - desc + extra, dia)
        elif perfil == "tardio":
            await self.pagar(unidad, deuda, mes + timedelta(days=rng.randint(14, 25)))
        elif perfil == "cronico":
            if rng.random() < 0.55:
                await self.pagar(
                    unidad,
                    d.redondear(deuda * D(rng.choice(["0.4", "0.5", "0.7", "1"])), 1000),
                    mes + timedelta(days=rng.randint(12, 27)),
                )
        elif perfil.startswith("deuda"):
            meses_sin_pagar = int(perfil[5:])
            if restantes >= meses_sin_pagar:  # antes de caer en mora pagaba bien
                await self.pagar(unidad, deuda, mes + timedelta(days=rng.randint(6, 9)))

    async def _condonacion_y_anulacion(self, por_etiqueta: dict[str, uuid.UUID]) -> None:
        admin = await self._admin()
        # Condonación de intereses a un moroso que firmó acuerdo de pago
        if "1-204" in por_etiqueta:
            filas = await self.db.execute(
                select(CargoCartera.id, CargoCartera.valor)
                .join(ConceptoCartera, ConceptoCartera.id == CargoCartera.concepto_id)
                .where(CargoCartera.unidad_id == por_etiqueta["1-204"], ConceptoCartera.codigo == "INTERESES_MORA")
                .order_by(CargoCartera.fecha_causacion)
                .limit(1)
            )
            fila = filas.first()
            if fila:
                await pagos.ajustar(
                    self.db,
                    admin,
                    AjusteIn(
                        cargo_id=fila[0],
                        tipo=TipoAjuste.CONDONACION,
                        valor=fila[1],
                        motivo="Acuerdo de pago aprobado por el consejo, acta 47",
                    ),
                )
        # Un pago registrado dos veces por error, y su anulación
        if "2-202" in por_etiqueta:
            r = await self.pagar(por_etiqueta["2-202"], D("150000"), self.hoy - timedelta(days=3))
            if r:
                await pagos.anular_pago(self.db, admin, r.pago.id, "Pago registrado dos veces por error de digitación")


async def generar() -> None:
    async with SessionLocal() as db:
        tenant_id = await db.scalar(select(Tenant.id).where(Tenant.slug == TENANT))
        if tenant_id is None:
            raise SystemExit("No existe la copropiedad de demo: ejecute primero python -m app.scripts.seed")
        await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
        if await db.scalar(select(func.count()).select_from(PeriodoCartera)):
            print("Ya hay cartera en la demo: no se genera de nuevo.")
            return
        if not await db.scalar(select(func.count()).select_from(Unit).where(Unit.coefficient.is_not(None))):
            raise SystemExit("Faltan las unidades con coeficiente: ejecute primero python -m app.scripts.demo unidades")
        admin = await db.scalar(
            select(Membership.user_id)
            .where(Membership.tenant_id == tenant_id, Membership.role == UserRole.ADMIN)
            .limit(1)
        )
        demo = Demo(db, tenant_id, admin)  # type: ignore[arg-type]
        await demo.ejecutar()
        await db.commit()

        await set_rls_context(db, tenant_id=tenant_id, user_id=admin, role="ADMIN")
        from app.services.cartera import consultas

        r = await consultas.resumen(db, demo.admin)
        print(
            f"Cartera de demo: total {r.cartera_total:,.0f}, vencida {r.cartera_vencida:,.0f}, "
            f"{r.unidades_en_mora} unidades en mora, recaudo del mes {r.recaudo_pct} %"
        )


def main() -> None:
    asyncio.run(generar())
