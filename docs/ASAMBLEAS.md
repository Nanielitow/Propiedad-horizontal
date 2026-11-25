# Módulo de Asambleas de copropietarios

La asamblea general es el máximo órgano de la copropiedad (Ley 675 de 2001). Este módulo la acompaña de principio a fin: programar y **convocar** (con el orden del día como circular), **instalar** con un padrón fijo de unidades y coeficientes, registrar **asistencia y poderes**, mostrar el **quórum en vivo**, **votar** cada punto ponderando por coeficiente (en la sala o desde el portal), calcular el **resultado según la mayoría que exige la ley** y producir el **acta**.

Estado: **fase 1 hecha** (base de datos, reglas y servicios). Ver §5.

---

## 1. Reglas legales que implementa

| Regla | Artículo | Cómo se aplica |
|---|---|---|
| Quórum en primera convocatoria: más de la mitad de los coeficientes | 45 | `Quorum.hay_quorum` compara el coeficiente presente con el total del padrón (50 % exacto no basta) |
| Segunda convocatoria: decide cualquier número plural de propietarios | 41 | Basta con dos unidades presentes |
| Mayoría simple: mitad más uno de los coeficientes representados | 45 | Se calcula sobre el quórum en el momento de cerrar la votación |
| Mayoría calificada: 70 % de los coeficientes del conjunto (reforma del reglamento, cuotas extraordinarias altas, cambio de destinación…) | 46 | Sobre el **total**, no sobre los presentes; no se rebaja en segunda convocatoria |
| Convocatoria con 15 días calendario de anticipación | 39 | Aviso al convocar si es con menos |
| Votación ponderada por coeficiente | 37 | El peso de cada voto lo fija el padrón (trigger), no quien vota |

No se decide sin quórum: la base y el servicio impiden abrir una votación sin él. Un propietario en mora conserva el voto; el padrón solo lo señala (informativo).

## 2. Cómo funciona

1. **Programar** la asamblea (ordinaria o extraordinaria; presencial, virtual o mixta; primera o segunda convocatoria) con su orden del día. Cada punto es informativo o de votación (mayoría simple, calificada del 70 % o elección).
2. **Convocar:** se publica una circular importante con el orden del día y el aviso de poderes, y se envía por correo.
3. **Instalar:** se fija el **padrón** (unidades activas con coeficiente, sus propietarios y quiénes de ellos tienen cuenta) y la asamblea queda en curso. Cambios posteriores en el censo no alteran el quórum.
4. **Asistencia:** recepción registra a cada propietario o apoderado (con su documento y la foto del poder). Se respeta el máximo de poderes por apoderado. En asambleas virtuales o mixtas, el propietario con cuenta se registra desde el portal. Quien se retira deja de contar.
5. **Votar:** se abre un punto a la vez. El personal registra los votos en la sala y el propietario vota desde el portal por todas sus unidades presentes. **El voto no se cambia ni se borra.**
6. **Cerrar el punto:** el resultado queda fijado con el quórum de ese momento y su explicación («Aprobado: 57,14 % de los coeficientes presentes a favor»).
7. **Cerrar la asamblea:** queda inmutable; solo se le puede enlazar el acta.

## 3. Datos (migración 0010)

`asambleas` · `asamblea_padron` (foto inmutable) · `asamblea_asistencias` (con retiro) · `asamblea_puntos` (con resultado y conclusión) · `asamblea_votos` (un voto por unidad y punto, inmutable).

## 4. Roles

| Acción | ADMIN | AUXILIAR | CONSEJO / CONTABILIDAD | RESIDENTE |
|---|---|---|---|---|
| Programar, convocar, instalar, abrir y cerrar votaciones, cerrar | ✔ | | | |
| Registrar asistencia, poderes y votos en la sala | ✔ | ✔ | | |
| Consultar asambleas, quórum y resultados | ✔ | ✔ | ✔ | ✔ |
| Asistir y votar desde el portal (virtual o mixta) | | | | Sus unidades, si es propietario |

## 5. Estado de implementación

### Fase 1: base de datos y reglas (hecha)

- **Migración 0010** con triggers: flujo de estados, padrón que solo se arma al instalar, asistencia y votos solo con la asamblea en curso, votación solo con el punto abierto y la unidad presente, el coeficiente del voto lo pone la base, punto cerrado y asamblea cerrada inmutables, nada se borra. RLS por rol, incluido el voto del residente solo por las unidades donde figura en el padrón.
- **Código:** `app/models/asamblea.py`, `app/schemas/asambleas.py`, `app/services/asambleas/` (`dominio.py` con quórum y mayorías, `servicio.py` con los casos de uso).
- **Pruebas:** 6 unitarias (quórum en primera y segunda convocatoria, mayoría simple con empate, calificada sobre el total, elección con empate, convocatoria) y 4 de integración (332 en total, todas en verde).
