# Respaldos de la base de datos

## Qué se respalda y cuándo

- **Todas las noches a las 3:00 a. m. (hora de Colombia)**, el worker hace un `pg_dump` completo de la base de Neon
  (formato custom, comprimido) con el rol dueño del esquema, que ignora RLS: incluye los datos de **todas** las
  copropiedades. Tarea `respaldos.diario`, `app/services/respaldos.py`.
- Antes de subirlo se verifica que el archivo se pueda leer (`pg_restore --list`). Si no, no se sube.
- Se guarda en R2, bucket `ph-documentos`, carpeta `respaldos/` (aparte de los documentos de los conjuntos):
  - `respaldos/diarios/ph-AAAA-MM-DD-HHMM.dump`: se conservan **30 días**.
  - `respaldos/mensuales/ph-AAAA-MM.dump`: la copia del día 1 de cada mes, se conserva **12 meses**.
- Solo corre en producción (`ENVIRONMENT=production`). En local se puede forzar desde el panel.
- **Si falla**, reintenta dos veces (cada 10 minutos). Si sigue fallando, avisa por correo a los dueños de la
  plataforma y queda el error en Sentry.

Además, Neon guarda su propio historial de **7 días** (restaurar a cualquier momento de la última semana desde el
panel de Neon).

**No incluye** los archivos de R2 (PDF de documentos, soportes, fotos): el respaldo es de la base de datos. Los
documentos tienen su texto e índice en la base, pero no el PDF original.

## Panel

`/plataforma` → «Respaldos de la base de datos»:
- estado: al día si hubo un respaldo en las últimas 36 horas;
- historial con tamaño;
- «Respaldar ahora»;
- «Descargar»: enlace firmado de 5 minutos.

El archivo descargado contiene todos los datos personales de todas las copropiedades: guárdelo cifrado o en un lugar
seguro, y bórrelo cuando ya no lo necesite.

## Restaurar

Se necesita el cliente de **PostgreSQL 18** (`pg_restore` 18), la versión de Neon. La imagen de la API lo trae.

### Opción recomendada: en una base nueva y luego cambiar

Así nunca se pisa la base actual hasta confirmar que el respaldo está bien.

1. En Neon, cree una **rama** nueva (*Branches → New branch*) o una base vacía, y copie su cadena de conexión del rol dueño.
2. Descargue el respaldo desde el panel (o con la consola de R2).
3. Restaure, por ejemplo desde el contenedor de la API (el archivo debe estar dentro de `apps/api` para verse en `/app`):

   ```sh
   docker compose exec -T -e PGURL="<cadena de la base nueva>" api \
     sh -c 'pg_restore --no-owner --no-privileges --exit-on-error --dbname="$PGURL" /app/ph-AAAA-MM-DD-HHMM.dump'
   ```

   Antes de abrir la app, recree el rol `app_user` y sus permisos en la base nueva (ver `deploy/neon/migrar.sh`).
4. Revise los datos: conteos, la última copropiedad y los últimos pagos.
5. Apunte la app a la base restaurada: en Railway cambie `DATABASE_URL`, `SYNC_DATABASE_URL` y
   `MIGRATIONS_DATABASE_URL` en `api`, `worker` y `beat` (o promueva la rama en Neon).

### Restaurar una sola tabla o una copropiedad

`pg_restore --list` muestra el contenido. Con `--use-list` se restaura solo lo elegido, en una base aparte, y luego se
copian los datos necesarios. Hágalo con cuidado: las tablas están relacionadas y tienen RLS.

## Probar que los respaldos sirven

Una vez al trimestre:
1. Descargue el último respaldo.
2. Restáurelo en una rama de prueba de Neon.
3. Entre a la app apuntando a esa rama (o revise los conteos) y luego borre la rama.

Un respaldo que nunca se ha restaurado no es un respaldo confirmado.
