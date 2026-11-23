// Configuración pública del selector de Google Drive, leída en TIEMPO DE EJECUCIÓN
// (no en el build): activar la integración solo requiere definir las variables de
// entorno del contenedor web. Son valores públicos por diseño de Google: el ID de
// cliente OAuth y una API key restringida a los dominios de la app.
export const dynamic = "force-dynamic";

export function GET() {
  const clientId = process.env.GOOGLE_CLIENT_ID ?? "";
  const apiKey = process.env.GOOGLE_API_KEY ?? "";
  const appId = process.env.GOOGLE_PROJECT_NUMBER ?? "";
  const enabled = Boolean(clientId && apiKey && appId);
  return Response.json(enabled ? { enabled, clientId, apiKey, appId } : { enabled: false });
}
