import { cookies } from "next/headers";

import { API_URL, TOKEN_COOKIE } from "@/lib/config";
import { refreshSession, setSession } from "@/lib/session";

// Cambiar la clave cierra las demás sesiones: la API devuelve tokens nuevos y aquí reemplazan
// a los de las cookies (el proxy genérico no puede escribir cookies de sesión).
export async function POST(request: Request) {
  const store = await cookies();
  const token = store.get(TOKEN_COOKIE)?.value ?? (await refreshSession(store));
  if (!token) return Response.json({ detail: "No autenticado" }, { status: 401 });
  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/api/v1/auth/cambiar-clave`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "",
      },
      body: await request.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "No se pudo conectar con el servidor." }, { status: 503 });
  }
  const data = await upstream.json().catch(() => null);
  if (!upstream.ok) return Response.json(data ?? { detail: "Ocurrió un error" }, { status: upstream.status });
  setSession(store, data);
  return Response.json({ ok: true });
}
