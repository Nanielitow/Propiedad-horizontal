# Costos y operación de PH Gestión

Guía para el dueño de la plataforma: qué se paga, cuánto, qué lo hace subir y qué hay que vigilar.

Precios consultados el **26 de noviembre de 2026** en las páginas oficiales (Railway, Neon, Google AI Studio,
Cloudflare, Resend). Cambian: revíselos cada trimestre. Las cifras de uso son **estimaciones**: confírmelas con los
tableros de cada proveedor después del primer mes con el cliente.

---

## 1. Resumen

**Pesos colombianos:** conversión con la TRM de referencia de **$3.300 por dólar** (TRM certificada del 18 nov 2026:
$3.309,55). Todos los proveedores cobran en dólares a su tarjeta, así que el valor en pesos cambia con la TRM.

| Servicio | Para qué | Plan | Costo mensual estimado |
|---|---|---|---|
| Railway | Web, API, worker, tareas programadas, Redis | Pro | **US$20 ≈ $66.000** (incluye US$20 de consumo) |
| Neon | Base de datos PostgreSQL | Launch | **US$5–20 ≈ $16.500–66.000** (según horas de uso) |
| Cloudflare R2 | Archivos (PDF, soportes, fotos) | Pago por uso | **$0** hasta 10 GB |
| Resend | Correos de la app | Gratis → Pro | **$0** hoy · **US$20 ≈ $66.000** con residentes reales |
| Google Gemini | Buscador con IA, lectura de documentos | Pago por uso | **US$1–10 ≈ $3.300–33.000** (según uso) |
| Dominio `propiedadhorizontal.app` | Dirección web | Anual | **≈ $4.000 al mes** (US$14,20 ≈ $46.900 al año) |
| **Total sin impuestos** | | | **US$30–50 ≈ $99.000–165.000 al mes** |
| **Total con IVA (19 %)** | | | **≈ $118.000–196.000 al mes** |

**Impuestos y comisiones al pagar con tarjeta:**
- **IVA del 19 % sobre servicios digitales del exterior** (Ley 1819 de 2016). Muchas plataformas extranjeras lo cobran
  o el banco lo retiene en la compra. Revise su extracto: si aparece, súmelo al costo. Si factura como empresa o
  persona responsable de IVA, consulte a su contador si puede descontarlo.
- **Comisión del banco por compras en moneda extranjera**, normalmente un pequeño porcentaje más el diferencial de
  cambio. Varía según la tarjeta.
- Para presupuestar con margen, calcule **~$130.000–210.000 al mes** para los primeros conjuntos.

El costo es casi **fijo**: no depende del número de copropiedades sino del uso total. Pasar de 1 a 10 conjuntos
apenas mueve la factura; lo que la mueve es la IA (preguntas y documentos analizados) y los correos.

---

## 2. Cada servicio en detalle

### Railway (servidores)

- **Plan Pro: US$20 (≈ $66.000) al mes por espacio de trabajo**, con **US$20 de consumo incluido**. Si el consumo del
  mes no pasa de US$20, solo paga los US$20.
- Tarifas de consumo: **US$10 (≈ $33.000) por GB de RAM al mes**, **US$20 (≈ $66.000) por vCPU al mes**, salida a
  internet US$0,05/GB. Se cobra por segundo.
- Servicios: `web` (Next.js), `api` (FastAPI, 2 procesos), `worker` (Celery: OCR, IA, correos), `beat` (tareas
  programadas) y `Redis`.
- Estimación: unos 1,3–1,6 GB de RAM en total y CPU casi en reposo ⇒ **~US$15–20 de consumo**, dentro del
  crédito. **Verifíquelo** en Railway → *Usage* al cerrar el primer mes.
- **Qué lo sube:** procesar muchos PDF escaneados a la vez (el OCR usa CPU y memoria), más tráfico, o agregar
  réplicas.
- **Recomendado:** Railway → *Settings → Usage* → fije un **límite de gasto** (p. ej. US$40 ≈ $132.000) con alerta
  al 80 %.

### Neon (base de datos)

- **Plan Launch, pago por uso, sin mínimo mensual:**
  - Cómputo: **US$0,106 (≈ $350) por CU-hora** (1 CU ≈ 4 GB de RAM).
  - Almacenamiento: **US$0,35 (≈ $1.155) por GB al mes**. Hoy la base pesa ~26 MB ⇒ unos $30.
  - Transferencia: 500 GB incluidos.
  - **Historial para restaurar: hasta 7 días** (ver «Respaldos»).
- **Se apaga sola** tras 5 minutos sin consultas (cómputo apagado = US$0) y despierta con la siguiente. La primera
  consulta después de una pausa tarda ~0,5–1 s más.
- Estimación con el tamaño mínimo (0,25 CU):
  - encendida unas 8 h al día: **~US$6 ≈ $19.800 al mes**;
  - encendida 24/7: **~US$19 ≈ $62.700 al mes**.

  Con más usuarios estará encendida más tiempo: ese es el techo realista para los primeros conjuntos.
- **Recomendado:** Neon → *Billing* → alerta de gasto.

### Cloudflare R2 (archivos)

- **Gratis cada mes:** 10 GB guardados, 1 millón de escrituras y 10 millones de lecturas. Descargas sin costo.
- Después: US$0,015 (≈ $50) por GB al mes. Un conjunto con años de actas, contratos y soportes rara vez pasa de 1–2 GB.
- Hoy: 1,2 MB. **Costo esperado: $0 por mucho tiempo.**

### Resend (correo)

- **Gratis: 3.000 correos al mes, pero máximo 100 al día.** No permite comprar extra en el plan gratis.
- **Pro: US$20 (≈ $66.000) al mes por 50.000 correos.** Excedente: US$0,90 (≈ $3.000) por cada 1.000.
- **Ojo con el tope diario.** Una circular «con correo» a un conjunto de 120 unidades ya pasa de 100. Lo mismo al
  invitar de golpe a todos los residentes. Los correos que pasen del tope fallan: el worker reintenta durante
  unos minutos y luego se pierden (el aviso igual queda en la app).
- **Recomendado:** pase a **Pro** antes de invitar a los residentes o de enviar la primera circular por correo.
  Mientras solo use la app el equipo administrativo, el plan gratis alcanza.
- La región de Resend es São Paulo. No afecta: el correo sale en segundo plano.

### Google Gemini (inteligencia artificial)

Modelos configurados en `.env` (y en las variables de Railway):

| Uso | Modelo | Precio por millón de tokens (entrada / salida) |
|---|---|---|
| Buscador con IA (chat) | `gemini-3.5-flash-lite` | US$0,30 / US$2,50 (≈ $990 / $8.250) |
| Leer documentos: vencimientos, cotizaciones, actas | `gemini-3.5-flash` → **redirige a `gemini-3.6-flash`** | US$0,75 / US$3,75 (≈ $2.475 / $12.375) **hasta el 31 dic 2026** · **US$1,50 / US$7,50 (≈ $4.950 / $24.750) desde el 1 ene 2027** |
| Índice para buscar (embeddings) | `gemini-embedding-001` | US$0,15 (≈ $495), solo entrada |

Un millón de tokens equivale a unas 750.000 palabras: unos 1.500 PDF de una página.

El «razonamiento» del modelo se cobra como salida. El chat usa razonamiento mínimo para ahorrar.

**Cuánto cuesta en la práctica (aproximado):**

| Acción | Costo |
|---|---|
| Una pregunta al buscador | ~US$0,003 ≈ **$10** |
| 1.000 preguntas | ~US$3 ≈ **$9.900** |
| Indexar un PDF de 50 páginas | ~US$0,005 ≈ **$17** |
| Analizar un documento (vencimientos, cotización o acta) | ~US$0,02 ≈ **$66** hoy · ~US$0,05 ≈ **$165** desde enero |

Con uso normal de un conjunto (unas cuantas preguntas al día y algunos documentos al mes): **menos de US$1 ≈ $3.300
al mes por conjunto.**

**Límites que ya trae la app** (protegen la factura):
- 300 preguntas al día por usuario.
- 40 análisis de IA al día por copropiedad.
- En los conjuntos de demostración, 40 preguntas al día por visitante.

**Pendientes:**
- **Antes del 1 de enero de 2027** decida el modelo de extracción, porque ese día su precio se duplica. Opciones:
  - dejar `gemini-3.6-flash` y asumir el doble (sigue siendo poco);
  - pasar a `gemini-3.5-flash-lite`, que es 2,5 veces más barato, probando antes que lea bien sus documentos.

  Se cambia en la variable `EXTRACTION_MODEL` de `api` y `worker`.
- `gemini-embedding-001` se apaga el **14 de mayo de 2028**; su reemplazo es `gemini-embedding-2`. Cambiarlo
  exige re-indexar los documentos: planéelo con tiempo.
- **Activada la capa paga (prepago, 26 nov 2026).** Úsela siempre, no la gratuita: en la gratuita Google puede usar los datos para entrenar sus
  modelos, y aquí hay documentos de terceros.
- **Recomendado:** Google Cloud → *Billing → Budgets & alerts*, presupuesto mensual (p. ej. US$15 ≈ $49.500) con
  alertas.

### Dominio

- `propiedadhorizontal.app` en Cloudflare Registrar: **~US$14,20 ≈ $46.900 al año**. Cloudflare cobra el precio del
  registro, sin recargo.
- **Active la renovación automática.** Si el dominio vence, la app y los correos dejan de funcionar.
- Los dominios `.app` exigen HTTPS. Ya está así.

---

## Controles de gasto configurados (26 nov 2026)

| Servicio | Aviso | Tope | Qué pasa al llegar al tope |
|---|---|---|---|
| Railway | Correo a US$25 (≈ $82.500) | US$75 (≈ $247.500) | **Se apagan todos los servicios** (la app se cae). Se reactiva subiendo el tope en railway.com/workspace/usage |
| Neon | Correo a US$25 (spending notifications) | Autoscaling de 0,25 a 1 CU, con scale to zero | Nunca se apaga: solo limita la capacidad (peor caso ~US$77/mes) |
| Gemini | — | **Prepago**: US$10 cargados, sin recarga automática | Se detienen el buscador con IA y el análisis de documentos hasta recargar; el resto de la app sigue |

Con prepago, Google no usa los datos para entrenar (capa paga). Revise el saldo cada mes en AI Studio → Billing; cuando
conozca el gasto mensual, puede activar la recarga automática con un monto pequeño.

## 3. Qué hace subir la factura

| Si pasa esto… | Sube… | Qué hacer |
|---|---|---|
| Invitar a todos los residentes o enviar circulares por correo | Resend (tope de 100/día) | Pasar a Resend Pro (US$20 ≈ $66.000) |
| Muchos usuarios a lo largo del día | Neon (más horas encendida) | Normal; techo ~US$20 ≈ $66.000 con 0,25 CU |
| Subir lotes grandes de PDF escaneados | Railway (CPU del OCR) y Gemini | Subir por partes; revisar *Usage* |
| Muchas preguntas al buscador | Gemini | Ya hay límites por usuario y por día |
| Crecer a decenas de conjuntos con uso diario | Railway, Neon, Gemini | Revisar tamaños; seguirá siendo bajo por conjunto |

---

## 4. Para ponerle precio a su servicio

Tenga presentes estas cifras al definir cuánto cobrar (el precio de venta es decisión suya):

- **Costo fijo de la plataforma:** ~US$30–50 al mes ≈ **$99.000–165.000** (≈ $118.000–196.000 con IVA), tenga 1 o
  10 conjuntos.
- **Costo variable por conjunto:** ~US$1–3 ≈ **$3.300–9.900 al mes** (IA y su parte de los correos).
- Con el primer cliente casi todo el costo es fijo. Con 7 conjuntos el costo por conjunto baja a unos US$5–8 ≈
  **$16.500–26.400 al mes** (≈ $20.000–31.000 con IVA).
- No incluye su tiempo de soporte ni las herramientas de desarrollo.
- Si cobra en pesos y paga en dólares, una subida de la TRM le reduce el margen: deje un colchón o revise su tarifa
  una vez al año.

---

## 5. Lo que tiene que saber para operar

### Dónde vive cada cosa

| Pieza | Dónde | Cuenta |
|---|---|---|
| Código | GitHub (repositorio `Propiedad-horizontal`) | Suya |
| Aplicación | Railway, región US East | Suya (plan Pro) |
| Base de datos | Neon, AWS US East 1 | Suya (plan Launch) |
| Archivos | Cloudflare R2, bucket `ph-documentos` | Suya |
| Dominio y DNS | Cloudflare | Suya |
| Correo | Resend | Suya |
| IA | Google AI Studio / Google Cloud | Suya |

### Secretos (lo más delicado)

- Las claves viven en **dos lugares**:
  - las **variables de cada servicio en Railway**, que usa la app;
  - el archivo **`.env` de su PC**, que usan los scripts de mantenimiento.
- **Nunca** las pegue en un chat, un correo ni en Git. `.env` está en `.gitignore`.
- **Guarde una copia de `.env` en un gestor de contraseñas** (Bitwarden, 1Password). Si su PC se daña, la app sigue
  funcionando, pero necesitará esas claves para mantenimiento.
- Si una clave se filtra: rótela en el proveedor y actualícela en Railway y en `.env`. Lo más sensible es la conexión
  de Neon, las claves de R2, la de Resend, la de Gemini y `JWT_SECRET`. Cambiar `JWT_SECRET` cierra todas las sesiones.

### Desplegar cambios

- Cada `git push` a `main` redespliega **solo** los servicios cuyo código cambió.
- `api` aplica las migraciones de base de datos antes de arrancar (`alembic upgrade head`, configurado en
  `deploy/railway/api.json`).
- **Lección del 26 nov 2026:** el servicio `api` no tenía configurado su archivo de Railway y la migración no corrió.
  La app estuvo caída ~15 minutos. Ya está corregido. Si algún día ve error 500 justo después de un despliegue con
  cambios de base de datos, esa es la primera sospecha.
- Cambiar variables en Railway redespliega el servicio: puede haber 1–3 minutos de interrupción. Hágalo fuera del
  horario de oficina del cliente.

### Respaldos

- **Neon guarda historial de 7 días.** Puede restaurar la base a cualquier momento de la última semana (Neon →
  *Branches → Restore*).
- **Respaldo automático cada noche** (3:00 a. m.) en R2: 30 días de copias diarias y 12 meses de mensuales, con aviso
  por correo si falla. Se ve, se fuerza y se descarga en `/plataforma`. Detalle y cómo restaurar: `docs/RESPALDOS.md`.
- **Recomendado:** una vez al trimestre, restaurar el último respaldo en una rama de prueba de Neon para confirmar
  que sirve.
- R2 no tiene historial de versiones activado: un archivo borrado desde la app se pierde. Las copias de cada
  documento quedan en la base (texto e índice), pero no el PDF.

### Monitoreo

- Salud de la app: `https://app.propiedadhorizontal.app/api/health` debe responder `{"web":"ok","postgres":"ok","redis":"ok"}`.
- **Monitor activo (26 nov 2026):** UptimeRobot consulta `/api/health` cada 5 minutos y avisa por correo y en la app
  del celular si cae (responde 503 si falla la web, la API, la base o Redis). Un «Down» corto durante un despliegue es
  normal.
- **Alertas de errores (Sentry):** con `SENTRY_DSN` en `api`, `worker` y `beat`, cada error de la API o de una tarea
  llega por correo, agrupado y sin datos personales (ni contraseñas, cookies, tokens ni formularios).
- Registros: Railway → servicio → *Deployments → Deploy Logs*. Los de la API no muestran claves ni enlaces de
  activación.

### Cuentas y copropiedades

Detalle en `docs/CUENTAS.md`. Lo esencial:
- Usted crea las copropiedades y su primer administrador en `/plataforma`. Una administradora con varios conjuntos
  usa **un solo correo**.
- No ve los datos de los conjuntos (privacidad). Para entrar a uno, su administración lo invita.
- Una copropiedad creada por error se elimina en `/plataforma` → lápiz → *Eliminar*. Los datos quedan en la base y
  se pueden recuperar.
- Los conjuntos de demostración (Los Pinos, Torre Central) se muestran en `/demo`. En ellos no se invitan usuarios
  y los correos solo salen a `SMTP_DEMO_RECIPIENTS`.

### Límites de uso (protegen contra abuso y costos)

| Qué | Límite |
|---|---|
| Intentos de inicio de sesión | 10 por cuenta cada 15 min y 50 por red |
| Recuperar contraseña | 3 por correo y 10 por red, cada hora |
| Invitaciones | 100 por hora por administrador |
| Preguntas al buscador | 20 por minuto y 300 por día por usuario |
| Análisis con IA | 40 por día por copropiedad |

Si un usuario ve «Demasiados intentos», se libera solo al pasar la ventana.

---

## 6. Aspectos legales en Colombia

- **Ley 1581 de 2012 (datos personales):**
  - Cada copropiedad es la **responsable** de los datos y usted (PH Gestión) es el **encargado**.
  - La política está en `/privacidad` y se acepta al activar la cuenta. **Pida a un abogado que la revise** y
    agregue un correo de contacto real, en la variable `NEXT_PUBLIC_CONTACT_EMAIL` del servicio `web`.
  - Firme con cada copropiedad un **contrato de transmisión de datos** (encargo), que exige la ley.
  - Los datos se guardan fuera de Colombia (EE. UU.). La política lo informa, pero confirme con el abogado los
    requisitos de transferencia internacional.
  - El **Registro Nacional de Bases de Datos (RNBD)** de la SIC solo es obligatorio para empresas por encima de
    cierto tamaño de activos. Verifique si le aplica.
- **Facturación electrónica (DIAN):** la app **no** factura. Lo que usted cobre a sus clientes lo factura por su
  cuenta; la contabilidad de cada conjunto la lleva su contador con su propio software.
- **Ley 675 de 2001:** la app sigue sus reglas: quórum por coeficiente, mayorías, actas. La validez jurídica de cada
  asamblea sigue dependiendo de la convocatoria y del acta firmada.

---

## 7. Calendario de pendientes

| Cuándo | Qué |
|---|---|
| Antes de invitar residentes | Pasar Resend a Pro (US$20 ≈ $66.000 al mes) |
| Hecho (26 nov) | Límites de gasto en Railway, Neon y Gemini (prepago) |
| Hecho (26 nov) | Renovación automática del dominio en Cloudflare |
| Hecho (26 nov) | Monitor de disponibilidad (UptimeRobot) |
| Ya | Copia de `.env` en un gestor de contraseñas |
| Antes de usar la app con datos reales | Revisión de `/privacidad` por un abogado y contrato de encargo con cada copropiedad |
| Antes del 1 ene 2027 | Decidir el modelo de extracción (`EXTRACTION_MODEL`): su precio se duplica ese día |
| Cada mes | Revisar *Usage* de Railway, Neon y Gemini; confirmar en `/plataforma` que los respaldos están al día |
| Cada trimestre | Restaurar un respaldo en una rama de prueba de Neon |
| Cada trimestre | Revisar precios de los proveedores |
| Antes de mayo 2028 | Migrar `gemini-embedding-001` → `gemini-embedding-2` (re-indexar documentos) |

---

## Fuentes (26 nov 2026)

- Railway: <https://railway.com/pricing>
- Neon: <https://neon.com/pricing>
- Gemini (precios): <https://aistudio.google.com/docs/pricing>
- Gemini (modelos retirados): <https://aistudio.google.com/docs/deprecations>
- Cloudflare R2: <https://developers.cloudflare.com/r2/pricing/>
- Resend: <https://resend.com/pricing>
- Dominio `.app` en Cloudflare: <https://costgoat.com/compare/domains/app> (referencia de terceros)
- TRM: Superintendencia Financiera de Colombia (certificada del 18 nov 2026: $3.309,55), reportada en
  <https://www.portafolio.co/economia/finanzas/dolar-en-colombia-frena-su-racha-alcista-y-cae-este-miercoles-18-de-noviembre-este-es-su-precio-oficial-506559>
