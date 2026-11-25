"""Censo de la copropiedad exportable (Excel y PDF) con el motor de reportes compartido.

El Consejo recibe unidades, coeficientes y propietarios, pero sin datos de contacto.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Persona, Tenant, UnidadPersona, Unit, Vehiculo
from app.models.enums import OcupacionUnidad, RelacionUnidad, TipoUnidad, UserRole
from app.services.activos.reportes import ReporteActivos
from app.services.comun import TZ, Actor, exigir, hoy_bogota
from app.services.recaudos.reportes import Columna, Tabla
from app.services.unidades import dominio as d
from app.services.unidades.consultas import _orden_unidad

TIPOS = {
    TipoUnidad.APARTAMENTO: "Apartamento",
    TipoUnidad.CASA: "Casa",
    TipoUnidad.LOCAL: "Local",
    TipoUnidad.OFICINA: "Oficina",
    TipoUnidad.PARQUEADERO: "Parqueadero",
    TipoUnidad.DEPOSITO: "Depósito",
    TipoUnidad.OTRO: "Otro",
}
OCUPACION = {
    OcupacionUnidad.PROPIETARIO: "Habitada por propietario",
    OcupacionUnidad.ARRENDADA: "Arrendada",
    OcupacionUnidad.DESOCUPADA: "Desocupada",
    OcupacionUnidad.SIN_INFORMACION: "Sin información",
}
RELACION = {
    RelacionUnidad.PROPIETARIO: "Propietario",
    RelacionUnidad.ARRENDATARIO: "Arrendatario",
    RelacionUnidad.RESIDENTE: "Residente",
    RelacionUnidad.AUTORIZADO: "Autorizado",
}


async def censo(db: AsyncSession, actor: Actor) -> ReporteActivos:
    exigir(actor, d.PUEDE_EXPORTAR, "exportar el censo")
    contacto = actor.role in d.PUEDE_VER_DIRECTORIO
    sensibles = actor.role in d.PUEDE_VER_DATOS_SENSIBLES
    tenant = await db.get(Tenant, actor.tenant_id)
    unidades = sorted(await db.scalars(select(Unit).where(Unit.activa.is_(True))), key=_orden_unidad)
    por_id = {u.id: u for u in unidades}
    vinculos = (
        await db.execute(
            select(UnidadPersona, Persona)
            .join(Persona, Persona.id == UnidadPersona.persona_id)
            .where(UnidadPersona.fecha_fin.is_(None))
        )
    ).all()
    por_unidad: dict[object, list[tuple[UnidadPersona, Persona]]] = defaultdict(list)
    for v, p in vinculos:
        por_unidad[v.unidad_id].append((v, p))

    def nombres(u: Unit, relacion: RelacionUnidad) -> str:
        return ", ".join(p.nombre_completo for v, p in por_unidad[u.id] if v.relacion == relacion)

    cols = [
        Columna("Unidad"),
        Columna("Tipo"),
        Columna("Anexo de"),
        Columna("Coeficiente (%)", "coeficiente"),
        Columna("Área (m²)", "entero"),
        Columna("Ocupación"),
        Columna("Propietario(s)"),
    ]
    if contacto:
        cols += [Columna("Arrendatario"), Columna("Responsable de pago"), Columna("Teléfono de contacto")]
    filas = []
    for u in unidades:
        principal = por_id.get(u.unidad_principal_id) if u.unidad_principal_id else None
        fila = [
            u.etiqueta,
            TIPOS[u.tipo],
            principal.etiqueta if principal else "",
            u.coefficient,
            int(u.area_m2) if u.area_m2 is not None else None,
            OCUPACION[u.ocupacion] if principal is None else "",
            nombres(u, RelacionUnidad.PROPIETARIO),
        ]
        if contacto:
            pago = next((p for v, p in por_unidad[u.id] if v.responsable_pago), None)
            cont = next((p for v, p in por_unidad[u.id] if v.es_contacto_principal), None)
            fila += [
                nombres(u, RelacionUnidad.ARRENDATARIO),
                pago.nombre_completo if pago else "",
                cont.telefono if cont and cont.telefono else "",
            ]
        filas.append(fila)
    estado = d.estado_coeficientes(
        u.coefficient for u in unidades if not (u.unidad_principal_id and u.coefficient is None)
    )
    totales = ["Total", "", "", estado.suma, None, "", ""] + (["", "", ""] if contacto else [])
    tablas = [Tabla("Unidades", cols, filas, totales, nota=estado.mensaje)]

    if contacto:
        cp = [Columna("Nombre"), Columna("Unidad"), Columna("Relación"), Columna("Reside"), Columna("Teléfono")]
        if sensibles:
            cp += [Columna("Documento"), Columna("Correo"), Columna("Autoriza datos")]
        filas_p = []
        for v, p in sorted(
            vinculos, key=lambda vp: (vp[1].nombre_completo.lower(), _orden_unidad(por_id[vp[0].unidad_id]))
        ):
            if v.unidad_id not in por_id:
                continue
            f = [
                p.nombre_completo,
                por_id[v.unidad_id].etiqueta,
                RELACION[v.relacion],
                "Sí" if v.reside else "No",
                p.telefono or "",
            ]
            if sensibles:
                doc = f"{p.tipo_documento} {p.numero_documento}" if p.numero_documento else ""
                f += [doc, p.email or "", "Sí" if p.autoriza_datos_at else "No"]
            filas_p.append(f)
        tablas.append(Tabla("Personas", cp, filas_p))

    if actor.role in d.PUEDE_VER_VEHICULOS:
        vehs = (await db.execute(select(Vehiculo).where(Vehiculo.activo).order_by(Vehiculo.placa))).scalars().all()
        tablas.append(
            Tabla(
                "Vehículos",
                [Columna("Placa"), Columna("Tipo"), Columna("Unidad"), Columna("Marca"), Columna("Color")],
                [
                    [v.placa, v.tipo.value.capitalize(), por_id[v.unidad_id].etiqueta, v.marca or "", v.color or ""]
                    for v in vehs
                    if v.unidad_id in por_id
                ],
            )
        )

    principales = [u for u in unidades if u.unidad_principal_id is None]
    resumen = [
        ("Unidades activas", str(len(unidades))),
        ("Unidades principales", str(len(principales))),
        ("Anexos (parqueaderos, depósitos)", str(len(unidades) - len(principales))),
        ("Arrendadas", str(sum(1 for u in principales if u.ocupacion == OcupacionUnidad.ARRENDADA))),
        ("Coeficientes", estado.mensaje),
    ]
    if actor.role == UserRole.CONSEJO:
        resumen.append(("Nota", "Versión para el Consejo: sin datos de contacto (Ley 1581 de 2012)"))
    hoy = hoy_bogota()
    return ReporteActivos(
        tipo="censo",
        titulo="Censo de la copropiedad",
        copropiedad=tenant.name if tenant else "",
        desde=hoy,
        hasta=hoy,
        generado=datetime.now(TZ),
        resumen=resumen,
        tablas=tablas,
        corte=True,
    )
