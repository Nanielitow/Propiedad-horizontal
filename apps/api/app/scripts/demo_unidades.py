"""Datos de demostración del censo (Conjunto Residencial Los Pinos).

Construido con los MISMOS casos de uso que la API (validaciones, triggers, auditoría):
  - 48 apartamentos (torres 1 y 2, pisos 1 a 6) + 2 locales comerciales, con área y
    coeficiente proporcional al área (suman exactamente 100 %);
  - 48 parqueaderos y 24 depósitos privados como anexos, sin coeficiente propio;
  - propietarios (algunos con dos apartamentos y algunos copropietarios al 50 %),
    ~20 % de unidades arrendadas, algunas desocupadas, familias residentes y autorizados;
  - historial: ventas y arriendos terminados (vínculos cerrados con fecha y motivo);
  - vehículos de los residentes;
  - Carlos Pérez (residente@lospinos.demo) es propietario del 1-502 y lo habita.

Uso: python -m app.scripts.demo unidades   (requiere `seed`; no repite si ya hay personas)
"""

import asyncio
import random
import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import Membership, Persona, Tenant, Unit, User
from app.models.enums import RelacionUnidad, TipoDocumentoIdentidad, TipoUnidad, TipoVehiculo, UserRole
from app.schemas.unidades import (
    CerrarVinculoIn,
    PersonaIn,
    UnidadIn,
    UnidadUpdate,
    VehiculoIn,
    VinculoIn,
    VinculoUpdate,
)
from app.services.comun import ActorSimple, hoy_bogota
from app.services.unidades import gestion

TENANT = "los-pinos"
RESIDENTE_EMAIL = "residente@lospinos.demo"
rng = random.Random(675)  # noqa: S311 - datos de demo reproducibles (Ley 675 de 2001)

NOMBRES = [
    "Andrés", "Camila", "Santiago", "Valentina", "Juan Pablo", "Laura", "Sebastián", "Daniela", "Felipe", "Natalia",
    "Mateo", "Isabella", "Alejandro", "Mariana", "Nicolás", "Paula", "Diego", "Sofía", "Julián", "Catalina",
    "Ricardo", "Gloria", "Hernando", "Beatriz", "Óscar", "Patricia", "Fernando", "Luz Marina", "Germán", "Adriana",
    "Mauricio", "Claudia", "Javier", "Sandra", "Gustavo", "Liliana", "Álvaro", "Mónica", "Jorge", "Ángela",
]  # fmt: skip
APELLIDOS = [
    "Rodríguez", "Gómez", "González", "Martínez", "García", "López", "Hernández", "Sánchez", "Ramírez", "Torres",
    "Díaz", "Vargas", "Moreno", "Rojas", "Jiménez", "Castro", "Ortiz", "Rubio", "Suárez", "Mejía",
    "Restrepo", "Ospina", "Cárdenas", "Salazar", "Quintero", "Arango", "Zapata", "Londoño", "Gutiérrez", "Botero",
]  # fmt: skip
MARCAS = [
    "Mazda 3",
    "Chevrolet Onix",
    "Renault Duster",
    "Kia Picanto",
    "Toyota Corolla",
    "Nissan Kicks",
    "Suzuki Swift",
]
MOTOS = ["Yamaha NMAX", "Honda CB 190", "AKT 125", "Bajaj Pulsar"]
COLORES = ["Gris", "Blanco", "Negro", "Rojo", "Azul", "Plata"]
LETRAS = "ABCDEFGHJKLMNPRSTUVWXYZ"


class Demo:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID, admin: uuid.UUID, residente: uuid.UUID | None) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.admin = ActorSimple(tenant_id, admin, UserRole.ADMIN)
        self.residente = residente
        self.hoy = hoy_bogota()
        self.documentos: set[str] = set()
        self.placas: set[str] = set()
        self.nombres: set[str] = set()

    async def _admin(self) -> ActorSimple:
        await set_rls_context(self.db, tenant_id=self.tenant_id, user_id=self.admin.user_id, role="ADMIN")
        return self.admin

    # --- Generadores ---------------------------------------------------------------

    def _nombre(self, apellido: str | None = None) -> str:
        while True:
            n = f"{rng.choice(NOMBRES)} {apellido or rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
            if n not in self.nombres:
                self.nombres.add(n)
                return n

    def _documento(self, menor: bool = False) -> str:
        while True:
            d = str(rng.randint(1_000_000_000, 1_099_999_999) if menor else rng.randint(10_000_000, 80_999_999))
            if d not in self.documentos:
                self.documentos.add(d)
                return d

    def _placa(self, moto: bool) -> str:
        while True:
            letras = "".join(rng.choice(LETRAS) for _ in range(3))
            p = f"{letras}{rng.randint(10, 99)}{rng.choice(LETRAS)}" if moto else f"{letras}{rng.randint(100, 999)}"
            if p not in self.placas:
                self.placas.add(p)
                return p

    def _persona(
        self, nombre: str, *, menor: bool = False, correo: bool = True, user_id: uuid.UUID | None = None
    ) -> PersonaIn:
        usuario = nombre.split()[0].lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o")
        return PersonaIn(
            nombre_completo=nombre,
            tipo_documento=TipoDocumentoIdentidad.TI if menor else TipoDocumentoIdentidad.CC,
            numero_documento=self._documento(menor),
            telefono=None
            if menor
            else f"3{rng.choice([0, 1, 2, 5])}{rng.randint(0, 9)}{rng.randint(1_000_000, 9_999_999)}",
            email=f"{usuario}.{rng.randint(10, 99)}@correo.demo" if correo and not menor else None,
            autoriza_datos=not menor and rng.random() < 0.8,
            user_id=user_id,
        )

    # --- Pasos ---------------------------------------------------------------------

    async def unidades(self) -> list[Unit]:
        admin = await self._admin()
        existentes = {(u.tower, u.number): u for u in await self.db.scalars(select(Unit))}
        principales: list[tuple[str, str, TipoUnidad, Decimal]] = []
        for torre in ("1", "2"):
            for piso in range(1, 7):
                for apto in range(1, 5):
                    area = Decimal("74.50") if apto in (1, 4) else Decimal("62.30")  # esquineros más grandes
                    principales.append((torre, f"{piso}0{apto}", TipoUnidad.APARTAMENTO, area))
        principales += [
            ("", "L-01", TipoUnidad.LOCAL, Decimal("45.00")),
            ("", "L-02", TipoUnidad.LOCAL, Decimal("38.20")),
        ]

        total = sum(a for *_, a in principales)
        coefs = [(a / total * 100).quantize(Decimal("0.0001")) for *_, a in principales]
        coefs[-1] += Decimal(100) - sum(coefs)  # el redondeo se ajusta en la última unidad

        creadas: list[Unit] = []
        for (torre, numero, tipo, area), coef in zip(principales, coefs, strict=True):
            u = existentes.get((torre, numero))
            if u is None:
                u = await gestion.crear_unidad(
                    self.db, admin, UnidadIn(tower=torre, number=numero, tipo=tipo, coefficient=coef, area_m2=area)
                )
            else:
                await gestion.editar_unidad(
                    self.db,
                    admin,
                    u.id,
                    UnidadUpdate(tipo=tipo, coefficient=coef, area_m2=area, motivo="Carga inicial del censo"),
                )
            creadas.append(u)

        apartamentos = [u for u in creadas if u.tipo == TipoUnidad.APARTAMENTO]
        for i, apto in enumerate(apartamentos, start=1):
            await gestion.crear_unidad(
                self.db,
                admin,
                UnidadIn(
                    tower=apto.tower,
                    number=f"PQ-{(i - 1) % 24 + 1:02d}",
                    tipo=TipoUnidad.PARQUEADERO,
                    area_m2=Decimal("12.50"),
                    unidad_principal_id=apto.id,
                ),
            )
        esquineros = [a for a in apartamentos if a.number.endswith(("01", "04"))]
        for i, apto in enumerate(esquineros, start=1):
            await gestion.crear_unidad(
                self.db,
                admin,
                UnidadIn(
                    tower=apto.tower,
                    number=f"DP-{(i - 1) % 12 + 1:02d}",
                    tipo=TipoUnidad.DEPOSITO,
                    area_m2=Decimal("3.20"),
                    unidad_principal_id=apto.id,
                ),
            )
        return creadas

    async def personas(self, principales: list[Unit]) -> None:
        admin = await self._admin()
        inversionistas: list[uuid.UUID] = []  # propietarios con más de una unidad (no residen en la segunda)
        hace = lambda dias: self.hoy - timedelta(days=dias)  # noqa: E731

        for u in principales:
            es_carlos = (u.tower, u.number) == ("1", "502")
            local = u.tipo == TipoUnidad.LOCAL
            suerte = rng.random()
            arrendada = local or (not es_carlos and suerte < 0.2)
            desocupada = not arrendada and not es_carlos and suerte < 0.27

            # Historial: un propietario anterior que vendió (en ~1 de cada 6 unidades)
            if not es_carlos and rng.random() < 0.17:
                anterior = await gestion.vincular(
                    self.db,
                    admin,
                    u.id,
                    VinculoIn(
                        persona=self._persona(self._nombre(), correo=False),
                        relacion=RelacionUnidad.PROPIETARIO,
                        reside=True,
                        fecha_inicio=hace(rng.randint(2500, 4000)),
                    ),
                )
                await gestion.cerrar_vinculo(
                    self.db,
                    admin,
                    anterior.id,
                    CerrarVinculoIn(
                        motivo="Venta del inmueble (escritura registrada)", fecha_fin=hace(rng.randint(400, 2400))
                    ),
                )

            # Propietario(s)
            inicio = hace(rng.randint(200, 2300))
            if es_carlos:
                carlos = await gestion.vincular(
                    self.db,
                    admin,
                    u.id,
                    VinculoIn(
                        persona=PersonaIn(
                            nombre_completo="Carlos Pérez",
                            tipo_documento=TipoDocumentoIdentidad.CC,
                            numero_documento="79456123",
                            telefono="3104567890",
                            email=RESIDENTE_EMAIL,
                            autoriza_datos=True,
                            user_id=self.residente,
                        ),
                        relacion=RelacionUnidad.PROPIETARIO,
                        reside=True,
                        fecha_inicio=hace(1800),
                    ),
                )
                for nombre, menor in (("Diana Pérez Ríos", False), ("Samuel Pérez Ríos", True)):
                    await gestion.vincular(
                        self.db,
                        admin,
                        u.id,
                        VinculoIn(
                            persona=self._persona(nombre, menor=menor), relacion=RelacionUnidad.RESIDENTE, reside=True
                        ),
                    )
                await gestion.registrar_vehiculo(
                    self.db,
                    admin,
                    u.id,
                    VehiculoIn(
                        placa="JPK482",
                        tipo=TipoVehiculo.CARRO,
                        marca="Mazda CX-30",
                        color="Rojo",
                        persona_id=carlos.persona_id,
                    ),
                )
                continue

            if inversionistas and (arrendada or desocupada) and rng.random() < 0.35:
                propietario = await gestion.vincular(
                    self.db,
                    admin,
                    u.id,
                    VinculoIn(
                        persona_id=rng.choice(inversionistas), relacion=RelacionUnidad.PROPIETARIO, fecha_inicio=inicio
                    ),
                )
            elif not local and rng.random() < 0.1:  # pareja copropietaria al 50 %
                apellido = rng.choice(APELLIDOS)
                propietario = await gestion.vincular(
                    self.db,
                    admin,
                    u.id,
                    VinculoIn(
                        persona=self._persona(self._nombre(apellido)),
                        relacion=RelacionUnidad.PROPIETARIO,
                        porcentaje_propiedad=Decimal(50),
                        reside=not (arrendada or desocupada),
                        fecha_inicio=inicio,
                    ),
                )
                await gestion.vincular(
                    self.db,
                    admin,
                    u.id,
                    VinculoIn(
                        persona=self._persona(self._nombre()),
                        relacion=RelacionUnidad.PROPIETARIO,
                        porcentaje_propiedad=Decimal(50),
                        reside=not (arrendada or desocupada),
                        fecha_inicio=inicio,
                    ),
                )
            else:
                propietario = await gestion.vincular(
                    self.db,
                    admin,
                    u.id,
                    VinculoIn(
                        persona=self._persona(self._nombre()),
                        relacion=RelacionUnidad.PROPIETARIO,
                        reside=not (arrendada or desocupada),
                        fecha_inicio=inicio,
                    ),
                )
                if arrendada or desocupada:
                    inversionistas.append(propietario.persona_id)

            habitante = propietario
            if arrendada:
                if rng.random() < 0.4:  # un arriendo anterior que terminó
                    previo = await gestion.vincular(
                        self.db,
                        admin,
                        u.id,
                        VinculoIn(
                            persona=self._persona(self._nombre(), correo=False),
                            relacion=RelacionUnidad.ARRENDATARIO,
                            reside=not local,
                            es_contacto_principal=False,
                            fecha_inicio=hace(rng.randint(500, 900)),
                        ),
                    )
                    await gestion.cerrar_vinculo(
                        self.db,
                        admin,
                        previo.id,
                        CerrarVinculoIn(
                            motivo="Terminación del contrato de arriendo", fecha_fin=hace(rng.randint(60, 450))
                        ),
                    )
                habitante = await gestion.vincular(
                    self.db,
                    admin,
                    u.id,
                    VinculoIn(
                        persona=self._persona(self._nombre()),
                        relacion=RelacionUnidad.ARRENDATARIO,
                        reside=not local,
                        es_contacto_principal=True,  # quien vive allí es el contacto del día a día
                        fecha_inicio=hace(rng.randint(30, 400)),
                    ),
                )
                if rng.random() < 0.25:  # algunos propietarios delegan el pago en el arrendatario
                    await gestion.editar_vinculo(self.db, admin, habitante.id, VinculoUpdate(responsable_pago=True))

            if desocupada or local:
                continue
            # Familia residente
            apellido = (await self.db.get(Persona, habitante.persona_id)).nombre_completo.split()[-2]  # type: ignore[union-attr]
            for _ in range(rng.choice([0, 1, 1, 2, 2, 3])):
                menor = rng.random() < 0.4
                await gestion.vincular(
                    self.db,
                    admin,
                    u.id,
                    VinculoIn(
                        persona=self._persona(self._nombre(apellido), menor=menor, correo=False),
                        relacion=RelacionUnidad.RESIDENTE,
                        reside=True,
                    ),
                )
            if rng.random() < 0.1:
                await gestion.vincular(
                    self.db,
                    admin,
                    u.id,
                    VinculoIn(persona=self._persona(self._nombre(), correo=False), relacion=RelacionUnidad.AUTORIZADO),
                )
            # Vehículos (en ~75 % de las unidades habitadas)
            if rng.random() < 0.75:
                moto = rng.random() < 0.2
                await gestion.registrar_vehiculo(
                    self.db,
                    admin,
                    u.id,
                    VehiculoIn(
                        placa=self._placa(moto),
                        tipo=TipoVehiculo.MOTO if moto else TipoVehiculo.CARRO,
                        marca=rng.choice(MOTOS if moto else MARCAS),
                        color=rng.choice(COLORES),
                        persona_id=habitante.persona_id,
                    ),
                )
                if rng.random() < 0.15:
                    await gestion.registrar_vehiculo(
                        self.db,
                        admin,
                        u.id,
                        VehiculoIn(
                            placa=self._placa(True),
                            tipo=TipoVehiculo.MOTO,
                            marca=rng.choice(MOTOS),
                            color=rng.choice(COLORES),
                        ),
                    )


async def generar() -> None:
    async with SessionLocal() as db:
        tenant_id = await db.scalar(select(Tenant.id).where(Tenant.slug == TENANT))
        if tenant_id is None:
            raise SystemExit("No existe la copropiedad de demo: ejecute primero python -m app.scripts.seed")
        await set_rls_context(db, tenant_id=tenant_id, role="SYSTEM")
        if await db.scalar(select(func.count()).select_from(Persona)):
            print("Ya hay personas en el censo de la demo: no se generan de nuevo.")
            return
        admin = await db.scalar(
            select(Membership.user_id)
            .where(Membership.tenant_id == tenant_id, Membership.role == UserRole.ADMIN)
            .limit(1)
        )
        if admin is None:
            raise SystemExit("Falta el administrador de la demo: ejecute python -m app.scripts.seed")
        residente = await db.scalar(select(User.id).where(User.email == RESIDENTE_EMAIL))
        demo = Demo(db, tenant_id, admin, residente)
        principales = await demo.unidades()
        await demo.personas(principales)
        await db.commit()

        await set_rls_context(db, tenant_id=tenant_id, user_id=admin, role="ADMIN")
        resumen = await gestion.estado_coeficientes(db, demo.admin)
        unidades = await db.scalar(select(func.count()).select_from(Unit).where(Unit.activa))
        personas = await db.scalar(select(func.count()).select_from(Persona))
        print(f"Censo de demo: {unidades} unidades, {personas} personas. {resumen.mensaje}.")


def main() -> None:
    asyncio.run(generar())
