"""Movimientos de demostración del módulo de recaudos (Conjunto Residencial Los Pinos).

Simula ~6 semanas de operación usando los MISMOS casos de uso que la API (con
sus validaciones, triggers y auditoría), así los datos son coherentes por
construcción:
  - parqueadero de visitantes todos los días (recepción) y aseo ocasional;
  - alquileres del salón social y la zona BBQ con reserva (alquiler + aseo);
  - transferencias de residentes, verificadas por contabilidad;
  - cierre de caja diario de recepción (con un par de faltantes y un sobrante);
  - entregas semanales a la administración y consignaciones conciliadas;
  - una anulación y transferencias viejas sin verificar (alertas).

Uso: python -m app.scripts.demo recaudos   (requiere `seed` y no repite si ya hay datos)
"""

import asyncio
import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import ConceptoRecaudo, Membership, Recaudo, Tenant, Unit, User
from app.models.enums import EstadoRecaudo, MedioPago, UserRole
from app.schemas.recaudos import (
    AplicacionIn,
    CierreCajaIn,
    ConsignacionCreate,
    EntregaConfirmacion,
    EntregaCreate,
    ParqueaderoIn,
    RecaudoCreate,
    ReservaCreate,
    ZonaCreate,
)
from app.services.recaudos import alertas, caja, catalogos, conciliacion, service
from app.services.recaudos.dominio import TZ, ActorSimple, ValidacionError

TENANT = "los-pinos"
DIAS = 42
rng = random.Random(20261122)  # noqa: S311  (determinista a propósito: la demo sale igual cada vez; no es criptografía)

UNIDADES = [(t, f"{p}0{a}") for t in ("1", "2") for p in range(1, 7) for a in range(1, 5)]
RESIDENTES = [
    "Familia Pérez",
    "Andrea Molina",
    "Camilo Restrepo",
    "Luisa Fernanda Ríos",
    "Jaime Ortiz",
    "Familia Cárdenas",
]
VISITANTES = ["Visitante", "Domicilio", "Técnico ascensores", "Visitante torre 1", "Visitante torre 2"]


def _placa() -> str:
    letras = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))
    return (
        f"{letras}{rng.randint(100, 999)}"
        if rng.random() < 0.8
        else f"{letras}{rng.randint(10, 99)}{rng.choice('ABCDEFG')}"
    )


def _momento(dia: date, hora: int, minuto: int = 0) -> datetime:
    return datetime.combine(dia, time(hora, minuto), TZ)


class Demo:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID, usuarios: dict[UserRole, uuid.UUID]) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.usuarios = usuarios
        self.conceptos: dict[str, ConceptoRecaudo] = {}
        self.unidades: list[uuid.UUID] = []
        self.zonas: dict[str, uuid.UUID] = {}

    async def como(self, rol: UserRole) -> ActorSimple:
        user = self.usuarios[rol]
        await set_rls_context(self.db, tenant_id=self.tenant_id, user_id=user, role=rol.value)
        return ActorSimple(self.tenant_id, user, rol)

    async def preparar(self) -> None:
        await set_rls_context(self.db, tenant_id=self.tenant_id, role="SYSTEM")
        if not await self.db.scalar(select(func.count()).select_from(Unit)):
            self.db.add_all(Unit(id=uuid.uuid4(), tenant_id=self.tenant_id, tower=t, number=n) for t, n in UNIDADES)
            await self.db.flush()
        self.unidades = list(await self.db.scalars(select(Unit.id)))
        self.conceptos = {c.codigo: c for c in await self.db.scalars(select(ConceptoRecaudo))}
        admin = await self.como(UserRole.ADMIN)
        for nombre, alquiler, aseo in (("Salón social", 150000, 50000), ("Zona BBQ", 80000, 30000)):
            zona = await catalogos.crear_zona(
                self.db, admin, ZonaCreate(nombre=nombre, tarifa_alquiler=Decimal(alquiler), tarifa_aseo=Decimal(aseo))
            )
            self.zonas[nombre] = zona.id
        await self.db.commit()

    async def parqueadero(self, dia: date, ahora: datetime) -> None:
        recepcion = await self.como(UserRole.AUXILIAR)
        for _ in range(rng.randint(3, 7)):
            ingreso = _momento(dia, rng.randint(7, 18), rng.choice((0, 10, 20, 30, 40, 50)))
            salida = ingreso + timedelta(minutes=rng.choice((35, 50, 75, 110, 140, 190, 240, 300)))
            salida = min(salida, ahora - timedelta(minutes=5))
            if salida <= ingreso:
                continue
            await service.registrar_recaudo(
                self.db,
                recepcion,
                RecaudoCreate(
                    concepto_id=self.conceptos["PARQUEADERO"].id,
                    medio_pago=MedioPago.EFECTIVO,
                    nombre_pagador=rng.choice(VISITANTES),
                    unidad_id=rng.choice(self.unidades) if rng.random() < 0.6 else None,
                    fecha_recaudo=salida,
                    parqueadero=ParqueaderoIn(placa_vehiculo=_placa(), hora_ingreso=ingreso, hora_salida=salida),
                ),
                ahora=ahora,
            )
        if rng.random() < 0.2:
            await service.registrar_recaudo(
                self.db,
                recepcion,
                RecaudoCreate(
                    concepto_id=self.conceptos["ASEO"].id,
                    medio_pago=MedioPago.EFECTIVO,
                    nombre_pagador=rng.choice(RESIDENTES),
                    unidad_id=rng.choice(self.unidades),
                    fecha_recaudo=_momento(dia, 17),
                    observaciones="Aseo del salón después de reunión",
                ),
                ahora=ahora,
            )

    async def alquiler(self, dia: date, ahora: datetime) -> None:
        """Reserva para el fin de semana siguiente, pagada hoy (transferencia o efectivo)."""
        zona = rng.choice(list(self.zonas))
        residente = rng.choice(RESIDENTES)
        unidad = rng.choice(self.unidades)
        admin = await self.como(UserRole.ADMIN)
        try:
            reserva = await catalogos.crear_reserva(
                self.db,
                admin,
                ReservaCreate(
                    zona_id=self.zonas[zona],
                    solicitante=residente,
                    unidad_id=unidad,
                    fecha_evento=dia + timedelta(days=(5 - dia.weekday()) % 7 or 7),
                    hora_inicio=time(14),
                    hora_fin=time(22),
                ),
            )
        except ValidacionError:  # la zona ya estaba reservada ese sábado
            return
        transferencia = rng.random() < 0.5
        actor = admin if transferencia else await self.como(UserRole.AUXILIAR)
        await service.registrar_recaudo(
            self.db,
            actor,
            RecaudoCreate(
                concepto_id=self.conceptos["ALQUILER_ZONA"].id,
                medio_pago=MedioPago.TRANSFERENCIA if transferencia else MedioPago.EFECTIVO,
                nombre_pagador=residente,
                unidad_id=unidad,
                reserva_id=reserva.id,
                numero_comprobante=f"BCOL-{rng.randint(100000, 999999)}" if transferencia else None,
                fecha_recaudo=_momento(dia, 11),
            ),
            ahora=ahora,
        )

    async def transferencia(self, dia: date, ahora: datetime) -> uuid.UUID:
        admin = await self.como(UserRole.ADMIN)
        motivo, valor = rng.choice(
            (
                ("Reposición de tarjeta de acceso", 25000),
                ("Venta de material reciclable", 68000),
                ("Uso de gimnasio para invitado", 15000),
                ("Copia de llave de cuarto útil", 12000),
            )
        )
        r = await service.registrar_recaudo(
            self.db,
            admin,
            RecaudoCreate(
                concepto_id=self.conceptos["OTROS"].id,
                medio_pago=MedioPago.TRANSFERENCIA,
                nombre_pagador=rng.choice(RESIDENTES),
                unidad_id=rng.choice(self.unidades),
                valor_recibido=Decimal(valor),
                numero_comprobante=f"NEQUI-{rng.randint(10**7, 10**8 - 1)}",
                observaciones=motivo,
                fecha_recaudo=_momento(dia, 10),
            ),
            ahora=ahora,
        )
        return r.id

    async def cierre(self, dia: date, ajuste: int = 0, nota: str | None = None) -> None:
        recepcion = await self.como(UserRole.AUXILIAR)
        ahora = _momento(dia, 20, 30)
        resumen = await caja.estado_caja(self.db, recepcion, ahora=ahora)
        if not resumen.cantidad:
            return
        await caja.cerrar_caja(
            self.db,
            recepcion,
            CierreCajaIn(
                saldo_inicial=Decimal(100000),
                valor_fisico_contado=Decimal(100000) + resumen.total_efectivo + ajuste,
                observacion_justificacion=nota,
            ),
            ahora=ahora,
        )

    async def entrega_semanal(self, dia: date) -> None:
        recepcion = await self.como(UserRole.AUXILIAR)
        ids = list(
            await self.db.scalars(
                select(Recaudo.id).where(
                    Recaudo.usuario_receptor_id == recepcion.user_id,
                    Recaudo.estado == EstadoRecaudo.RECAUDADO_EN_CAJA,
                    Recaudo.cierre_id.is_not(None),
                    Recaudo.entrega_id.is_(None),
                )
            )
        )
        if not ids:
            return
        entrega = await caja.crear_entrega(
            self.db, recepcion, EntregaCreate(recibido_por_id=self.usuarios[UserRole.ADMIN], recaudo_ids=ids)
        )
        admin = await self.como(UserRole.ADMIN)
        await caja.confirmar_entrega(
            self.db, admin, entrega.id, EntregaConfirmacion(valor_contado=entrega.valor_total), ahora=_momento(dia, 9)
        )

    async def consignacion_semanal(self, dia: date, n: int) -> uuid.UUID | None:
        admin = await self.como(UserRole.ADMIN)
        pendientes = [
            p
            for p in await conciliacion.pendientes_por_consignar(self.db, admin)
            if p.recaudo.estado == EstadoRecaudo.ENTREGADO_ADMINISTRACION
        ]
        if not pendientes:
            return None
        total = sum((p.saldo for p in pendientes), Decimal(0))
        c, _ = await conciliacion.registrar_consignacion(
            self.db,
            admin,
            ConsignacionCreate(
                fecha_consignacion=dia,
                banco_destino="Bancolombia",
                referencia_bancaria=f"CNS-{dia:%Y%m%d}-{n:02d}",
                valor_consignado=total,
                aplicaciones=[AplicacionIn(recaudo_id=p.recaudo.id) for p in pendientes],
            ),
            ahora=_momento(dia, 11),
        )
        return c.id

    async def ejecutar(self) -> None:
        await self.preparar()
        hoy = datetime.now(TZ).date()
        transferencias: list[tuple[date, uuid.UUID]] = []
        consignaciones: list[tuple[date, uuid.UUID]] = []
        faltantes = {
            hoy - timedelta(days=17): (-5000, "Se entregó mal el cambio de un billete de $50.000"),
            hoy - timedelta(days=6): (-3000, "Faltante por moneda falsa detectada al contar"),
            hoy - timedelta(days=11): (2000, "Visitante no esperó el cambio"),
        }

        for i in range(DIAS, -1, -1):
            dia = hoy - timedelta(days=i)
            ahora = _momento(dia, 20) if i else datetime.now(TZ)
            if i == 0 and ahora.hour < 9:
                break
            await self.parqueadero(dia, ahora)
            if dia.weekday() in (1, 3) and rng.random() < 0.8:
                await self.alquiler(dia, ahora)
            if dia.weekday() in (0, 4):
                transferencias.append((dia, await self.transferencia(dia, ahora)))
            if i > 0:  # hoy la caja sigue abierta: así la demo muestra un cierre pendiente
                ajuste, nota = faltantes.get(dia, (0, None))
                await self.cierre(dia, ajuste, nota)
            if dia.weekday() == 0 and i > 0:
                await self.entrega_semanal(dia)
            if dia.weekday() == 1 and i > 0:
                if cid := await self.consignacion_semanal(dia, len(consignaciones) + 1):
                    consignaciones.append((dia, cid))
            await self.db.commit()

        # Contabilidad: aprueba y verifica lo consignado (la última consignación queda pendiente)
        contabilidad = await self.como(UserRole.CONTABILIDAD)
        for dia, cid in consignaciones[:-1]:
            await conciliacion.aprobar_consignacion(
                self.db, contabilidad, cid, ahora=_momento(dia + timedelta(days=1), 10)
            )
            await conciliacion.verificar_consignacion(
                self.db, contabilidad, cid, ahora=_momento(dia + timedelta(days=3), 10)
            )
        if consignaciones:
            ultima_dia, ultima = consignaciones[-1]
            await conciliacion.aprobar_consignacion(
                self.db, contabilidad, ultima, ahora=_momento(ultima_dia + timedelta(days=1), 10)
            )
        # Verifica las transferencias, salvo dos recientes y una vieja (queda una alerta)
        for dia, rid in transferencias[:-3]:
            await service.verificar_recaudo(self.db, contabilidad, rid, ahora=_momento(dia + timedelta(days=2), 9))
        await self.db.commit()

        # Una anulación con su motivo (queda en la auditoría)
        admin = await self.como(UserRole.ADMIN)
        duplicado = await self.transferencia(hoy - timedelta(days=2), datetime.now(TZ))
        await service.anular_recaudo(self.db, admin, duplicado, "Transferencia registrada dos veces por error")
        await set_rls_context(self.db, tenant_id=self.tenant_id, role="SYSTEM")
        await alertas.detectar_transferencias_sin_verificar(self.db, self.tenant_id, dias=3)
        await self.db.commit()


async def generar() -> None:
    async with SessionLocal() as db:
        tenant_id = await db.scalar(select(Tenant.id).where(Tenant.slug == TENANT))
        if tenant_id is None:
            raise SystemExit("No existe la copropiedad de demo: ejecute primero python -m app.scripts.seed")
        await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
        if await db.scalar(select(func.count()).select_from(Recaudo)):
            print("Ya hay recaudos en la demo: no se generan de nuevo.")
            return
        usuarios = {
            rol: uid
            for uid, rol in await db.execute(
                select(User.id, Membership.role)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.tenant_id == tenant_id,
                    Membership.role.in_([UserRole.ADMIN, UserRole.AUXILIAR, UserRole.CONTABILIDAD]),
                )
            )
        }
        if len(usuarios) < 3:
            raise SystemExit(
                "Faltan usuarios demo (admin, recepción, contabilidad): ejecute python -m app.scripts.seed"
            )
        await Demo(db, tenant_id, usuarios).ejecutar()

        await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
        resumen = (
            await db.execute(text("SELECT count(*), sum(valor_recibido) FROM recaudos WHERE estado <> 'ANULADO'"))
        ).one()
        estados = dict((await db.execute(text("SELECT estado::text, count(*) FROM recaudos GROUP BY 1"))).all())
        print(f"Recaudos de demo: {resumen[0]} por ${resumen[1]:,.0f}".replace(",", "."))
        print("Por estado:", ", ".join(f"{k}={v}" for k, v in sorted(estados.items())))


def main() -> None:
    asyncio.run(generar())
