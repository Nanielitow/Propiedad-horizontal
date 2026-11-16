// Salud del sistema para Docker y para monitores externos (UptimeRobot, Better Stack).
// Es la única forma de comprobar la API desde fuera: la API no es pública.
import { API_URL } from "@/lib/config";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${API_URL}/health/ready`, { cache: "no-store", signal: AbortSignal.timeout(3000) });
    const api = (await res.json().catch(() => ({}))) as Record<string, string>;
    return Response.json({ web: "ok", ...api }, { status: res.ok ? 200 : 503 });
  } catch {
    return Response.json({ web: "ok", api: "sin respuesta" }, { status: 503 });
  }
}
