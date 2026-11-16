# Arquitectura · PH-SaaS (Administración de Propiedad Horizontal)

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind, shadcn/ui, react-pdf |
| Backend API | Python 3.12 + FastAPI, SQLAlchemy 2.0 (async) + Alembic, Pydantic v2 |
| Workers | Celery + Redis (broker y result backend), Celery beat para tareas programadas |
| Documentos | PyMuPDF (texto nativo), ocrmypdf + Tesseract `spa` (escaneados) |
| Datos | PostgreSQL 17 + pgvector 0.8 (HNSW) + FTS español (`unaccent`) |
| Archivos | S3 compatible (Cloudflare R2 / SeaweedFS en local), URLs firmadas |
| IA | Capa `LLMProvider` (OpenAI por defecto, Gemini intercambiable): embeddings, streaming, Structured Outputs |

## Estructura del monorepo

```
propiedad-horizontal/
├── apps/
│   ├── web/                                # Next.js
│   │   ├── src/app/
│   │   │   ├── (auth)/login/
│   │   │   └── (app)/[tenantSlug]/
│   │   │       ├── search/                 # Buscador IA + visor PDF lateral
│   │   │       ├── documents/              # Subida, estado de ingesta, listado
│   │   │       ├── deadlines/              # Calendario de vencimientos
│   │   │       ├── quotes/                 # Comparador de cotizaciones
│   │   │       └── minutes/                # Resúmenes de actas
│   │   ├── src/components/
│   │   │   ├── ui/                         # shadcn/ui
│   │   │   ├── chat/                       # Mensajes en streaming, chips de citas
│   │   │   ├── pdf-viewer/                 # react-pdf, salto a página, resaltado
│   │   │   └── ...
│   │   ├── src/lib/                        # api-client, auth, lector SSE
│   │   └── src/types/api.ts                # Generado desde OpenAPI (openapi-typescript)
│   │
│   └── api/                                # FastAPI + Celery (mismo código, distintos entrypoints)
│       ├── app/
│       │   ├── main.py
│       │   ├── core/                       # config, seguridad (JWT, argon2), logging
│       │   ├── db/                         # engine, sesión con SET LOCAL app.tenant_id/role
│       │   ├── models/                     # SQLAlchemy
│       │   ├── schemas/                    # Pydantic (request/response)
│       │   ├── api/
│       │   │   ├── deps.py                 # current_user, tenant_context, require_role()
│       │   │   └── v1/                     # auth, documents, search, chat, deadlines, quotes, minutes
│       │   ├── services/
│       │   │   ├── storage/                # presign PUT/GET, claves por tenant
│       │   │   ├── ingestion/              # extract, ocr, chunker, embedder
│       │   │   ├── retrieval/              # hybrid_search, prompt builder, validación de citas
│       │   │   ├── llm/                    # LLMProvider, openai_provider, gemini_provider
│       │   │   └── extraction/             # deadlines, quotes, minutes (schemas Structured Outputs)
│       │   ├── repositories/
│       │   └── workers/
│       │       ├── celery_app.py
│       │       ├── schedule.py             # beat: recordatorios diarios
│       │       └── tasks/                  # ingest, extract_deadlines, summarize_minutes, compare_quotes
│       ├── alembic/
│       │   ├── sql/                        # migraciones SQL-first (fuente de verdad del esquema)
│       │   └── versions/                   # 0001_initial_schema.py ejecuta sql/0001_*.up.sql
│       ├── samples/                        # PDFs de demo (nativo y escaneado)
│       ├── tests/                          # unit (chunker), integration (RLS contra Postgres real)
│       ├── pyproject.toml                  # uv
│       └── Dockerfile                      # imagen única; worker incluye tesseract-ocr-spa
│
├── infra/
│   └── postgres/init/                      # extensiones, rol app_user
├── docker-compose.yml                      # postgres+pgvector, redis, seaweedfs, api, worker, beat, web
├── docs/
│   ├── ARCHITECTURE.md
│   └── adr/                                # Architecture Decision Records
├── .github/workflows/                      # lint, typecheck, tests
├── package.json                            # atajos: up, down, logs, web:dev, db:psql (sin make en Windows)
├── .env.example
└── README.md
```

## Decisiones clave (trade-offs)

1. **FastAPI + Celery en lugar de NestJS + BullMQ.** El ecosistema de PDF/OCR (PyMuPDF, ocrmypdf, Tesseract), tokenización y evaluación de RAG es mucho más maduro en Python. Coste: dos lenguajes en el monorepo; se mitiga generando los tipos TS desde el OpenAPI de FastAPI, de modo que el contrato es una sola fuente de verdad.

2. **Multi-tenancy en esquema compartido + `tenant_id` + RLS.** Frente a una base o esquema por edificio, es lo más simple de operar y migrar, y escala a miles de tenants. El riesgo (un `WHERE` olvidado) se cubre con tres capas: (a) filtros explícitos en los repositorios, (b) Row Level Security con `FORCE`, alimentada por `SET LOCAL app.tenant_id` en cada transacción, y (c) claves foráneas compuestas `(tenant_id, id)`, que hacen imposible relacionar filas de edificios distintos. Coste: hay que gestionar bien el contexto en el pool de conexiones (por eso `SET LOCAL`, que muere con la transacción).

3. **RBAC aplicado también en la base de datos.** `access_level` se desnormaliza en cada chunk y una política RLS `RESTRICTIVE` impide que un `RESIDENTE` lea chunks `ADMIN`, aunque haya un bug en la API. Un trigger propaga en la misma transacción los cambios de clasificación del documento a sus chunks.

4. **pgvector en lugar de una base vectorial dedicada (Pinecone, Qdrant).** Un solo sistema, transacciones ACID entre documento y embeddings, joins y RLS sobre los vectores. Hasta unos pocos millones de chunks rinde de sobra. Coste: el filtrado con HNSW puede dejar el top-k incompleto; se resuelve con `hnsw.iterative_scan` (pgvector ≥ 0.8). Si un tenant crece mucho, se pueden usar particiones o índices parciales por tenant.

5. **HNSW frente a IVFFlat.** No necesita entrenamiento (sirve con la tabla vacía e inserciones incrementales) y tiene mejor recall. Coste: construcción más lenta y más memoria.

6. **Búsqueda híbrida con Reciprocal Rank Fusion.** Los vectores captan la semántica ("¿puedo tener perro?" → "mascotas"), pero fallan con literales como números de póliza, NIT o "Artículo 23". El FTS en español con `unaccent` cubre esos casos. RRF combina rankings sin calibrar puntuaciones heterogéneas. El re-ranking con un cross-encoder queda como mejora opcional.

7. **Chunks conscientes de página.** Cada chunk guarda `page_number` y `page_end`, y el texto por página se guarda aparte (`document_pages`). Así la cita lleva al visor a la página exacta y se puede re-chunkear o cambiar de modelo de embeddings sin repetir el OCR, que es la etapa más cara.

8. **Citas verificables en lugar de confiar en el LLM.** Al modelo se le pasan los fragmentos numerados `[1]..[n]` y se le pide citar por número. El backend traduce cada número al `document_id` y `page_number` reales y descarta los que no existen. El modelo nunca inventa IDs ni páginas.

9. **Vencimientos con humano en el bucle.** Lo que extrae la IA entra en estado `PENDING_REVIEW` con su `confidence`, página y frase de origen. Nada dispara alertas hasta que un admin lo confirma, porque un falso negativo (una póliza vencida) cuesta mucho más que un clic de revisión.

10. **Subida directa a S3 con URL prefirmada.** El navegador sube el archivo directamente a R2, sin pasar por la API. El worker lo descarga, lo procesa y guarda una versión con capa de texto (ocrmypdf). El visor recibe una URL GET de corta duración (unos 5 min), emitida tras verificar el RBAC.

11. **Idempotencia.** El hash `sha256` es único por tenant (evita duplicados), los jobs se registran en `processing_jobs` para reintentos y trazabilidad, y `deadline_notifications` tiene una restricción única para no enviar un recordatorio dos veces.

12. **Embeddings de 1536 dimensiones (`text-embedding-3-small`) con `embedding_model` versionado.** Buen equilibrio entre coste y calidad en español. `gemini-embedding-001` también admite 1536 dimensiones, así que cambiar de proveedor no exige migrar la columna, solo re-embeber (`POST /documents/{id}/reprocess`), y `document_pages` lo hace barato. Para desarrollar sin API key existe `EMBEDDING_PROVIDER=fake` (vectores deterministas por hashing).

13. **Migraciones SQL-first.** RLS, políticas, triggers, la función `hybrid_search` y los enums no se pueden expresar con el autogenerate de Alembic. La fuente de verdad del esquema es `alembic/sql/*.sql`; los modelos SQLAlchemy lo reflejan. Coste: hay que mantener modelo y SQL sincronizados a mano; lo cubren los tests de integración.

14. **Contexto RLS re-aplicado automáticamente.** `SET LOCAL` muere con cada transacción, así que tras un `commit()` la sesión quedaría sin tenant y vería 0 filas. Un listener `after_begin` de SQLAlchemy re-aplica `app.tenant_id`, `app.user_id` y `app.role` al inicio de cada transacción. Así es imposible olvidarlo y una conexión del pool nunca arrastra el tenant de otra petición.

15. **Chunking por bloques y secciones.** Se extrae por bloques de layout (párrafos), no por líneas, y se abre un chunk nuevo en cada CAPÍTULO o TÍTULO. Así cada chunk pertenece a un tema y una zona del documento, y la cita abre la página correcta. Al embeber, cada chunk se prefija con el título del documento y la sección (*contextual chunk header*), pero en la base se guarda limpio.

16. **Commit antes de encolar.** La API confirma la transacción y solo después envía la tarea a Celery; si no, el worker podría buscar un job que aún no existe. Coste: si Redis cae justo entre ambos pasos, el documento queda en `QUEUED`; un *transactional outbox* o una tarea que recoja jobs huérfanos lo resolvería.

17. **Errores permanentes frente a transitorios.** Un PDF cifrado o corrupto, o un hash que no coincide, falla de inmediato con un mensaje legible (`PermanentIngestionError`). Los errores de red, de S3 o los límites del proveedor de IA se reintentan con backoff exponencial (30 s, 60 s, 120 s).

19. **Modelo de chat elegido por latencia medida.** Con la misma pregunta, `gemini-3.5-flash` tardó unos 20 s en dar el primer token (incluso con el razonamiento al mínimo) y `gemini-3.5-flash-lite` con `thinking_level=minimal` tardó unos 0,7 s, citando igual de bien. Para un chat se prioriza la latencia; el modelo más potente se reserva para extracciones en segundo plano (vencimientos, actas), donde nadie espera mirando la pantalla.

20. **Búsqueda léxica con OR.** `plainto_tsquery` exige que aparezcan TODAS las palabras, y una pregunta natural casi nunca coincide completa. Se unen los lexemas con `|` y `ts_rank_cd` premia a los chunks que contienen más términos. Las *stopwords* ("el", "de", "puedo") las elimina el diccionario español.

21. **Streaming por SSE sobre `fetch`.** `EventSource` no permite POST ni cabeceras de autenticación, así que el frontend lee el `ReadableStream`. Orden de los eventos: `sources` (antes de la primera palabra, para que el panel de fuentes aparezca de inmediato), `token`… y `done` con las citas ya validadas. `X-Accel-Buffering: no` evita que un proxy acumule la respuesta.

22. **Reescritura de preguntas de seguimiento.** "¿Y los lunes?" no sirve para buscar. Si hay historial, el LLM la reescribe como pregunta autónoma ("¿Cuál es el horario de la piscina los lunes?") antes de la recuperación. El historial se envía sin los fragmentos antiguos para no inflar los tokens.

23. **Sin fragmentos no hay LLM.** Si la búsqueda no devuelve nada (por ejemplo, otro edificio o un residente sin acceso), se responde "No encontré…" sin llamar al modelo: coste cero y cero posibilidades de alucinar. La pregunta del usuario se guarda antes de llamar al LLM y la respuesta al terminar, con su traza de recuperación (chunks, puntuaciones y consulta reescrita) para evaluar la calidad del RAG.

24. **BFF con cookie httpOnly en lugar de guardar el JWT en el navegador.** El navegador nunca habla con FastAPI: llama a `/api/proxy/*`, un route handler de Next.js que añade el token desde una cookie httpOnly y reenvía la petición (con streaming, para el SSE del chat). El token es inaccesible para JavaScript, lo que mitiga el robo por XSS, y web y API comparten origen, sin CORS. Coste: un salto de red extra, despreciable frente a la latencia del LLM.

25. **Navegación completa al iniciar y cerrar sesión.** La caché en memoria de SWR sobrevive a la navegación de cliente. Sin una recarga completa, el siguiente usuario de la misma pestaña vería por un instante datos del anterior (detectado en pruebas: el admin veía la lista del residente). Login y logout usan `window.location`.

26. **Resaltado del fragmento citado en el PDF.** Al pulsar una cita, el visor abre la página y resalta el fragmento. Se recorre la capa de texto de pdf.js ya dibujada, se buscan las líneas o palabras del fragmento y se resalta el **bloque continuo más grande**. No se usa `customTextRenderer` de react-pdf porque empareja texto y elementos con un contador que se desfasa en las capas de texto generadas por OCR.

27. **Auditoría sin `RETURNING`.** SQLAlchemy añade `RETURNING id` a los INSERT, y PostgreSQL aplica a las filas devueltas las políticas de SELECT. Como un residente no puede leer `audit_logs` (es *append-only*), su INSERT se rechazaba. La auditoría se escribe con SQL explícito, y un test de regresión lo cubre.

28. **Detector de vencimientos: la IA propone y el código verifica.** Tras la ingesta, los documentos de las categorías Contratos, Mantenimiento y Actas pasan por un job aparte (si falla, el documento sigue disponible en el buscador). Se usa *Structured Outputs* con un esquema Pydantic, y antes de guardar nada:
    - la frase de origen debe existir **literalmente** en el documento (coincidencia normalizada o ≥ 85 % de palabras, para tolerar errores de OCR); si no, es una alucinación y se descarta;
    - si la frase está en otra página, se corrige la página;
    - se rechazan fechas inválidas, ya muy pasadas o absurdas.

    Todo entra como `PENDING_REVIEW` y no genera alertas hasta que un admin lo confirma.

29. **Deduplicación y prioridad de fuente.** Mismo tipo y misma fecha en el edificio equivale a un mismo vencimiento, aunque lo mencionen varios documentos. Si un acta dice "la póliza vence el 31 de marzo" y luego se sube la póliza, la fuente pasa a ser la póliza: al verificar, el admin debe ver el documento original. Un vencimiento descartado no se vuelve a proponer.

30. **Modelo distinto para extraer y para conversar.** La extracción usa `gemini-3.5-flash` con razonamiento completo (de 12 a 21 s por documento, en segundo plano) porque hay que calcular fechas relativas: "12 meses desde el 1-feb" da 31-ene, y "preaviso de 30 días" da 1-ene. El chat usa el Lite, porque ahí hay una persona esperando.

31. **Recordatorios idempotentes.** Celery beat ejecuta la tarea a diario (7:00, hora de Bogotá). La restricción única `(deadline_id, notify_on, channel)` más `INSERT … ON CONFLICT DO NOTHING RETURNING` garantizan un único aviso por día aunque la tarea corra dos veces. Se usa `RETURNING` y no `rowcount`, porque con un INSERT del ORM `rowcount` reporta 1 aunque no inserte (detectado en pruebas). El canal actual es `in_app`; el correo se conectaría en ese mismo punto.

32. **Vencimientos periódicos.** Al marcar como realizado un mantenimiento que se repite (por ejemplo, el lavado de tanques cada 6 meses), se crea la siguiente fecha ya confirmada. `add_months` ajusta el fin de mes (31-ene + 1 mes = 28/29-feb).

33. **Comparador de cotizaciones: los números los calcula el código, no el LLM.** Hay una extracción estructurada por cotización, en paralelo (unos 20 s para 3). Cada cifra se verifica buscándola escrita en el documento, y se aceptan los formatos 48.500.000, 48,500,000 y 48500000. Los totales y el IVA calculados ("más IVA del 19 %") se comprueban por la aritmética y se marcan "calculado". Lo que no se verifica no se oculta: se marca "verificar". La tabla y los ganadores por criterio (precio, garantía, plazo, con los días hábiles convertidos a calendario) se calculan en código. El LLM solo redacta el análisis, a partir de los datos ya verificados.

34. **El análisis advierte cuándo el precio engaña.** El prompt obliga a señalar las diferencias de alcance. En la prueba, la cotización más barata excluía andamios y retiro de escombros, y el análisis desaconsejó adjudicarla sin cotizar antes esos conceptos. Los datos ausentes se envían como "no indicado" y no como "no verificado", para no generar falsas alarmas ni tecnicismos en el texto para el consejo.

35. **Respaldo automático ante cuota agotada.** El plan gratuito de Gemini limita el modelo Flash a 20 solicitudes diarias. Si el modelo de extracción responde 429, la misma tarea se repite con el modelo Lite y queda registrado ("gemini-3.5-flash-lite (respaldo por cuota)"). Otros errores (503, red) no degradan el modelo: se reintentan con backoff.

36. **Resumidor de actas.** Al subir un acta se dispara su resumen, en paralelo a la búsqueda de vencimientos. Extrae tipo de reunión, fecha, quórum, acuerdos, votaciones con porcentajes y compromisos con responsable y fecha; los plazos relativos ("dentro de los 10 días siguientes") se calculan a partir de la fecha del acta. Se verifica la frase de cada elemento y que **cada porcentaje aparezca escrito en el acta**. Un quórum que no aparece no se muestra. Los compromisos pasan a `action_items` para hacerles seguimiento, y al volver a resumir un acta se conserva el estado de las tareas existentes.

37. **Gráfico de votaciones accesible.** La barra apilada usa azul (a favor), naranja tostado (en contra) y gris (abstención), validados con un script: con daltonismo protanopia la separación es ΔE 20,4. Se evitó verde/rojo, que son indistinguibles para esa forma de daltonismo. Los porcentajes siempre van escritos junto a la barra, con leyenda y tooltip, para que el color nunca sea la única forma de leer el resultado.

38. **Límites de uso con Redis (ventana fija).** Hay límites por usuario (preguntas por minuto y por día, búsquedas, subidas), por edificio (análisis con IA, para acotar el gasto total) y por cuenta e IP en el login (fuerza bruta). La ventana fija es simple: permite un pico de hasta 2x en el borde de dos ventanas, aceptable aquí. Si Redis cae, se deja pasar la petición (*fail-open*): el límite protege el costo y no debe tumbar el servicio. La respuesta 429 incluye `Retry-After` y un mensaje en español.

39. **Refresh tokens rotativos con ventana de gracia.** El acceso dura 15 minutos y la renovación 7 días. El `jti` del refresh vive en Redis (lista de permitidos) y se consume con `GETDEL` atómico. Reutilizar un token rotado devuelve 401, porque es señal de robo. Problema real: el navegador lanza varias peticiones a la vez cuando el acceso vence, y la segunda cerraría la sesión. Por eso, durante 30 s, reutilizar el token recién rotado devuelve **el mismo** par nuevo. El BFF de Next.js renueva de forma transparente (y repite la petición si la API responde 401); como los Server Components no pueden escribir cookies, las navegaciones pasan por `/api/auth/refresh`.

40. **Recordatorios por correo idempotentes y sin pérdidas.** Por cada canal (`in_app`, `email`), `INSERT … ON CONFLICT DO NOTHING RETURNING` decide si toca enviar. El insert del correo va en un SAVEPOINT junto al envío: si el SMTP falla, se deshace y el correo se reintenta al día siguiente en lugar de perderse. Solo se envía a los administradores del edificio. En local, Mailpit atrapa los correos.

41. **Calidad automatizada.** `ruff` (lint + formato a 120 columnas; E501 desactivado porque las líneas largas restantes son prompts, SQL y HTML), migraciones contra pgvector real en CI, typecheck y build del frontend, y build de las imágenes de producción. La configuración se valida al arrancar: en producción se rechazan un `JWT_SECRET` de ejemplo o el proveedor de embeddings de prueba, la documentación `/docs` se desactiva y la imagen corre con un usuario sin privilegios.

42. **Producción en un VPS con Docker Compose.** Se eligió frente a servicios gestionados (Railway, Neon, Upstash) por costo (unos 5–7 USD al mes frente a 15–30) y porque reutiliza el mismo modelo de despliegue que el entorno local. El precio es operar el servidor uno mismo, cosa que se automatiza con scripts: preparación del servidor (SSH solo con llave, firewall, swap, actualizaciones automáticas), despliegue con verificación de salud y vuelta atrás por SHA, y copias diarias a R2.

43. **Superficie pública mínima.** Solo Caddy publica puertos (80/443) y la API de FastAPI no es accesible desde internet: el navegador habla con el BFF de Next.js y con R2 mediante URLs firmadas. Como Docker publica puertos saltándose `ufw`, ningún otro servicio declara `ports` en el compose de producción. Redis lleva contraseña aunque no sea alcanzable desde fuera (defensa en profundidad) y la documentación interactiva de la API se desactiva en producción.

44. **Imágenes inmutables por commit.** GitHub Actions construye las imágenes tras pasar el CI y las publica en GHCR con dos etiquetas: el SHA del commit y `latest`. El servidor nunca compila: descarga y arranca. Volver atrás es `deploy.sh <sha>`. Las migraciones corren como un servicio previo (`migrate`) del que depende la API, así que una migración fallida impide arrancar una versión incompatible con la base. `NEXT_PUBLIC_DEMO_MODE` se pasa como argumento de compilación porque Next.js incrusta esas variables en el JavaScript del navegador.

45. **Demo pública con restauración por instantánea SQL.** Los datos de la demo se cargan una vez con un script reproducible (`demo load`) y se guardan en un esquema `demo_snapshot`. Cada noche se restauran en **una sola transacción** (`TRUNCATE … CASCADE` + `INSERT … OVERRIDING SYSTEM VALUE`, omitiendo las columnas generadas y reajustando la secuencia de auditoría) y se borran de R2 los archivos huérfanos. Restaurar por SQL en lugar de reprocesar los documentos tarda 0,1 s y no gasta llamadas a la IA. Como todos los visitantes comparten las cuentas demo, se añaden límites por IP (preguntas y subidas diarias): un límite por usuario lo agotaría un solo visitante para todos.

18. **Licencias.** PyMuPDF y Ghostscript (que usa ocrmypdf) son AGPL. Para un proyecto de portafolio de código abierto no hay problema. Si se comercializa como SaaS cerrado, hay que comprar la licencia comercial o cambiar a `pypdfium2` (Apache/BSD).
