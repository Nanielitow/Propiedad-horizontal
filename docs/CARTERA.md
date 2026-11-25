# Módulo de Cartera de cuotas de administración

La cuota ordinaria es el ingreso principal de una copropiedad y lo primero que un administrador espera de un software de propiedad horizontal. Este módulo factura la cuota de cada mes, causa los intereses de mora, registra los pagos con la imputación que exige la ley, lleva el saldo de cada unidad, reporta los morosos y expide el paz y salvo.

Estado: **fase 1 hecha** (base de datos, reglas y servicios). Ver §6.

---

## 0. Cómo encaja

| Ya existe | Cómo lo usa la cartera |
|---|---|
| **Unidades** con coeficiente, tipo y anexos | La cuota se calcula por coeficiente o por tarifa del tipo de unidad. Un anexo sin coeficiente propio no se factura aparte |
| **Responsable de pago** (`unidad_personas.responsable_pago`) | Cada cargo guarda a nombre de quién se causó (foto del momento), aunque después cambie el propietario |
| **Recaudos** | Siguen siendo los ingresos extraordinarios (parqueadero de visitantes, salón social). La cartera es otro libro: cuotas y su recaudo |
| Auditoría por trigger, consecutivos sin huecos, «nada se borra», RLS por rol | Mismos patrones. El residente ve solo lo de sus unidades |

## 1. Reglas de negocio

1. **Cuota ordinaria.** Método `COEFICIENTE`: presupuesto mensual × coeficiente / 100. Método `TARIFA_POR_TIPO`: un valor por tipo de unidad (apartamento, local, parqueadero…). Se redondea al múltiplo configurado (por defecto $100).
2. **Periodo.** Emitir el mes crea en una transacción la cuota de cada unidad, los intereses de mora y la aplicación de los saldos a favor. Un mes solo se emite una vez. Se puede anular el periodo solo si nadie ha pagado sobre él.
3. **Intereses de mora.** Al emitir, se cobra la tasa mensual configurada sobre el capital vencido que genera interés. Los intereses no generan intereses (art. 2235 del Código Civil). La Ley 675 (art. 30) fija el tope: 1,5 veces el interés bancario corriente certificado por la Superintendencia Financiera. La tasa la fija la administración y queda en la foto de cada periodo.
4. **Imputación de pagos** (art. 1653 del Código Civil): primero intereses, luego capital, de lo más antiguo a lo más reciente. Lo que sobra queda como **saldo a favor** y se aplica solo al causarse nuevos cargos.
5. **Descuento por pronto pago.** Solo si el pago llega antes de la fecha límite, deja la unidad al día en todo lo anterior y alcanza para la cuota con descuento. El descuento queda como ajuste ligado al pago: si el pago se anula, el descuento cae con él.
6. **Saldos calculados, nunca guardados.** Saldo de un cargo = valor − aplicaciones de pagos vigentes − ajustes (vista `v_saldos_cargo`). Anular un pago devuelve el saldo sin tocar nada más.
7. **Nada se edita ni se borra.** Periodos, cargos y pagos solo se anulan, con motivo. Las aplicaciones, los ajustes y los paz y salvos son inmutables. La base impide sobreaplicar un cargo o un pago, incluso con dos pagos simultáneos.
8. **Cuotas extraordinarias** aprobadas en asamblea: un valor por unidad o un total repartido por coeficiente, en una o varias cuotas mensuales.
9. **Condonaciones y correcciones**: ajustes con motivo (p. ej. «aprobado por el consejo, acta 45»), solo del administrador.
10. **Paz y salvo**: solo sin saldo vencido. Lleva consecutivo, vigencia hasta fin de mes y un código de verificación (sin 0/O ni 1/I, para dictarlo por teléfono). El residente puede descargar el suyo.

## 2. Modelo de datos (migración 0008)

`cartera_config` (por copropiedad) · `conceptos_cartera` (ADMINISTRACION, EXTRAORDINARIA, INTERESES_MORA, MULTA, OTRO; extensible) · `periodos_cartera` (con la foto de la configuración usada y sus totales) · `cargos_cartera` · `pagos_cartera` (recibo con consecutivo, referencia bancaria única) · `aplicaciones_pago` · `ajustes_cartera` · `paz_y_salvos` · `auditoria_cartera` · vista `v_saldos_cargo`.

## 3. Roles

| Acción | ADMIN | CONTABILIDAD | AUXILIAR | CONSEJO | RESIDENTE |
|---|---|---|---|---|---|
| Ver cartera, estados de cuenta y morosos | ✔ | ✔ | ✔ | ✔ | Solo sus unidades |
| Configurar, facturar, cuotas extraordinarias | ✔ | | | | |
| Registrar pagos | ✔ | ✔ | | | |
| Anular pagos, cargos y periodos; condonar | ✔ | | | | |
| Expedir paz y salvo | ✔ | ✔ | ✔ | | El suyo, si está al día |
| Auditoría | ✔ | ✔ | | | |

## 4. Plan

| Fase | Contenido |
|---|---|
| **1. Base de datos y reglas** | Migración 0008, modelos, imputación, intereses, descuento, facturación, pagos, anulaciones, paz y salvo, pruebas |
| **2. API, reportes y demo** | Endpoints, estado de cuenta (pantalla y PDF), morosos por antigüedad, resumen, paz y salvo en PDF, exportaciones, datos de demostración |
| **3. Pantallas** | Panel de cartera, facturación, registro de pagos, estado de cuenta, morosos, configuración, y para el residente: su estado de cuenta y su paz y salvo |

## 6. Estado de implementación

### Fase 1: base de datos y reglas (hecha)

- `alembic/sql/0008_cartera.up.sql`: 9 tablas, vista de saldos, triggers de «solo anular», validación de aplicaciones y ajustes con candado por cargo, auditoría y RLS por rol.
- `app/services/cartera/`: `dominio.py` (reglas puras), `comun.py` (configuración, saldos, responsable), `facturacion.py`, `pagos.py`, `cargos.py`, `paz_y_salvo.py`.
- Pruebas: 14 unitarias y 13 de integración (297 en total, todas en verde).
