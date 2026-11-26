import "server-only";

import { cookies } from "next/headers";

import { API_URL } from "./config";
import { setSession } from "./session";

/** Reenvía una petición pública de la cuenta a la API (con la IP real para los límites de uso).
 *  Si la API entrega tokens (activar, restablecer), abre la sesión en cookies httpOnly. */
export async function reenviarCuenta(request: Request, ruta: string, abrirSesion: boolean): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/api/v1/auth/${ruta}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "",
      },
      body: await request.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "No se pudo conectar con el servidor." }, { status: 503 });
  }
  const data = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    const headers = new Headers();
    const retry = upstream.headers.get("retry-after");
    if (retry) headers.set("retry-after", retry);
    return Response.json(data ?? { detail: "Ocurrió un error" }, { status: upstream.status, headers });
  }
  if (abrirSesion) {
    setSession(await cookies(), data);
    return Response.json({ user: data.user, memberships: data.memberships });
  }
  return Response.json(data, { status: upstream.status });
}
