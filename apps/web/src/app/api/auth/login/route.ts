import { cookies } from "next/headers";

import { API_URL } from "@/lib/config";
import { setSession } from "@/lib/session";

export async function POST(request: Request) {
  const body = await request.text();
  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // IP real del usuario para el límite de intentos por red
        "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "",
      },
      body,
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "No se pudo conectar con el servidor. ¿Está corriendo la API?" }, { status: 503 });
  }

  const data = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    const headers = new Headers();
    const retry = upstream.headers.get("retry-after");
    if (retry) headers.set("retry-after", retry);
    return Response.json(data ?? { detail: "Error al iniciar sesión" }, { status: upstream.status, headers });
  }

  // Los tokens NUNCA llegan al JavaScript del navegador: cookies httpOnly.
  setSession(await cookies(), data);
  return Response.json({ user: data.user, memberships: data.memberships });
}
