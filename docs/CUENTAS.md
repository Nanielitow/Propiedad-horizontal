# Cuentas, copropiedades y demo

## Modelo

- **Una cuenta por persona** (su correo) y **una membresía por copropiedad**, con un rol en cada una. Una
  administradora con 7 conjuntos entra una sola vez y cambia de conjunto con el selector del menú lateral.
- **Dueño de la plataforma** (`users.is_platform_admin`): crea copropiedades y su primer administrador desde
  `/plataforma`. No ve los datos de los conjuntos (RLS); para entrar a uno, su administración lo invita.
- **Administrador de cada copropiedad**: invita a su equipo y a los residentes desde «Usuarios y accesos», o desde
  la ficha de una unidad («Dar acceso al portal», que vincula la cuenta a la persona del censo y le muestra su
  unidad). Cambia roles y retira accesos; siempre queda al menos un administrador.

## Enlaces de un solo uso (`account_tokens`)

| Tipo | Vence | Para qué |
|---|---|---|
| `INVITACION` | 7 días | Definir la primera contraseña y aceptar la política de datos (Ley 1581) |
| `RECUPERACION` | 1 hora | «¿Olvidó su contraseña?» |

Solo se guarda el SHA-256 del token. Emitir uno nuevo anula los anteriores del mismo tipo; usarlo lo consume.
Activar, restablecer o cambiar la clave fija `users.sessions_valid_after`: los tokens emitidos antes dejan de valer
(se cierran las demás sesiones). Invitar a alguien que ya tiene cuenta no le manda enlace: solo un aviso.

Los correos los envía el worker (`cuentas.correo`); la API no espera al servidor SMTP.

## Demo dentro de la app real

La demo ya no es global (`DEMO_MODE=false` en producción): es una marca por copropiedad (`tenants.is_demo`).
Los conjuntos de ejemplo (Los Pinos y Torre Central) conviven con los reales y se entra a ellos desde
`/demo` (el login normal no muestra las cuentas de ejemplo). En un conjunto de ejemplo:

- No se pueden invitar ni modificar usuarios, ni cambiar la clave de las cuentas `@*.demo`.
- Los correos solo salen a `SMTP_DEMO_RECIPIENTS` (los visitantes podrían registrar correos de terceros).
- Aplican los límites diarios por visitante (preguntas a la IA, subidas, escrituras).
- No hay restauración nocturna: `restore_snapshot` se niega a correr si existe una copropiedad real, porque
  vacía todas las tablas.

## Puesta en marcha en producción

1. `DEMO_MODE=false` en `api`, `worker` y `beat` (Railway → Variables).
2. Cuenta del dueño (una vez): `python -m app.scripts.plataforma dueno --email … --nombre "…"`. Envía el enlace de
   activación por correo; nunca lo imprime.
3. El dueño entra a `/plataforma` → «Nueva copropiedad» (nombre, NIT, ciudad y el correo de la administradora).
   Además del correo automático, la ventana muestra el enlace de activación para enviarlo por WhatsApp. Si la
   administradora no lo usó, «Enlace» en la fila genera uno nuevo (anula el anterior; solo para administradores
   que aún no activan: a una cuenta activa nunca se le genera enlace).
4. La administradora activa su cuenta con el correo, importa las unidades (Excel), configura la cartera e invita a su
   equipo y a los residentes.
