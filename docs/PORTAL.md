# Portal del residente: PQRS, circulares y reservas

El residente deja de ser un usuario pasivo (solo documentos y chat) y gana trámites propios: radicar y seguir **PQRS**, recibir **circulares** con acuse de lectura y **reservar zonas sociales** sin llamar a la administración. Junto con su estado de cuenta y su paz y salvo (módulo de cartera), es la razón para que los residentes usen la plataforma.

Estado: **fases 1 y 2 hechas** (base de datos, reglas, API, correos y demo). Ver §5.

---

## 1. PQRS (peticiones, quejas, reclamos, sugerencias y felicitaciones)

- **Radicado** consecutivo por copropiedad, sin huecos (`PQRS-2026-0001`).
- **Quién radica:** el residente desde el portal (a su nombre, sobre sus unidades) o recepción/administración a nombre de alguien (presencial, correo, teléfono).
- **Plazo:** 15 días hábiles, como el derecho de petición (Ley 1755 de 2015), sin sábados, domingos ni festivos colombianos. Los festivos se calculan (fijos, Ley Emiliani trasladados al lunes y los que dependen de la Pascua), no se escriben a mano. Reabrir reinicia el plazo.
- **Flujo** (impuesto por trigger): `RADICADA → EN_TRAMITE → RESPONDIDA → CERRADA`; `RESPONDIDA → EN_TRAMITE` si el residente la reabre; `DESISTIDA` antes de responder. No se cierra sin respuesta. Lo radicado (asunto, descripción, quién) no se modifica: se agregan mensajes.
- **Conversación:** mensajes públicos, **notas internas** del personal (el residente no las ve, por RLS) y **respuesta formal**. Al cerrar, el residente **califica** de 1 a 5.
- **Quién la ve:** administración y recepción, todas; consejo, todas en lectura (comité de convivencia); contabilidad, las de cartera; mantenimiento, las que tiene asignadas; el residente, las suyas (un vecino no ve la queja de otro).
- **Integración:** una PQRS de mantenimiento se convierte en **novedad** del activo afectado (módulo de mantenimiento) y queda enlazada.
- **Adjuntos:** fotos o PDF, subidos con URL firmada a la carpeta de la copropiedad; la API solo acepta claves de esa carpeta y ya subidas.

## 2. Circulares

- **Borrador → publicada (numerada) → archivada.** Una publicada no se edita: se publica una aclaración.
- **Destinatarios:** toda la copropiedad o torres específicas. Se envían por correo también a **propietarios sin cuenta** que tienen correo en el directorio.
- **Importante:** se destaca y pide **acuse de lectura**; la administración ve cuántos la leyeron.
- Puede llevar un PDF del módulo de documentos.

## 3. Reservas de zonas sociales desde el portal

- **Reglas por zona:** horario, anticipación mínima y máxima, cupo mensual por unidad, capacidad, **exigir estar al día con la cartera**, aprobación manual o automática.
- **Disponibilidad sin datos personales:** el residente ve las franjas ocupadas, no quién reservó (función `disponibilidad_zona`, SECURITY DEFINER). El cruce de horarios del residente se valida con esa misma función: una consulta directa no vería las reservas de los vecinos por la RLS.
- **El residente solo cancela** sus reservas (trigger). La administración aprueba o rechaza con motivo.
- El cobro del alquiler sigue siendo un recaudo asociado a la reserva (módulo de recaudos).

## 4. Plan

| Fase | Contenido |
|---|---|
| **1. Base de datos y reglas** | Migración 0009, modelos, días hábiles y festivos, servicios de PQRS, circulares y reservas, pruebas |
| **2. API, correos y demo** | Endpoints, avisos por correo (PQRS radicada y respondida, circular publicada, reserva solicitada y decidida), datos de demostración |
| **3. Pantallas** | Inicio del residente, Mis PQRS, Circulares, Reservar; para el personal: bandeja de PQRS, redactor de circulares, solicitudes de reserva y reglas de las zonas |

## 5. Estado de implementación

### Fase 1: base de datos y reglas (hecha)

- **Migración 0009**: `pqrs`, `pqrs_mensajes`, `circulares`, `circular_lecturas`, `auditoria_portal`; ampliación de `zonas_sociales` (reglas) y `reservas` (portal, decisión); estado `RECHAZADA`; triggers de flujo, inmutabilidad y auditoría; RLS por rol, incluido el residente sobre zonas y reservas.
- **Código:** `app/models/portal.py`, `app/schemas/portal.py`, `app/services/portal/` (`dominio.py`, `pqrs.py`, `circulares.py`, `reservas.py`, `adjuntos.py`).
- **Pruebas:** 13 unitarias (festivos de 2026 contra el calendario oficial, días hábiles, reglas de reserva, estados) y 6 de integración (319 en total, todas en verde).

### Fase 2: API, correos y demo (hecha)

- **API** (`app/api/v1/portal.py`): inicio del residente y pendientes del personal; PQRS (bandeja con filtros, resumen con tiempo de respuesta y satisfacción, radicar, detalle con la conversación, mensajes, responder, gestionar, calificar, reabrir, desistir, convertir en novedad); adjuntos con URL firmada; circulares (listar según la torre, crear, editar borrador, publicar, archivar, marcar leída con estadísticas para el personal); zonas con sus reglas y disponibilidad; reservas (listar, solicitar, cancelar, decidir).
- **Privacidad en la conversación:** al residente las respuestas le llegan firmadas por «Administración», no con el nombre de quien escribió.
- **Correos** (`app/workers/tasks/portal.py`), encolados después del commit: PQRS radicada (al personal), PQRS respondida (a quien radicó, o al contacto dejado por recepción), circular publicada (a los destinatarios, una sola vez aunque la tarea se reintente), reserva solicitada (al personal) y decidida (al residente).
- **Demo** (`python -m app.scripts.demo portal`): reglas de 3 zonas, 14 PQRS en todos los estados (radicadas por Carlos y por recepción a nombre de otros residentes; una vencida, una convertida en novedad), 6 circulares publicadas y un borrador, y 2 reservas de Carlos (una esperando aprobación). Instantánea actualizada.
- **Pruebas:** 3 de API (322 en total, todas en verde).
