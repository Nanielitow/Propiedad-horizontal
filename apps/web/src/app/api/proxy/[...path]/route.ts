// BFF (Backend For Frontend): reenvía /api/proxy/* a FastAPI /api/v1/* añadiendo
// el token de la cookie httpOnly. Ventajas:
//  - el token no es accesible desde JavaScript (mitiga robo por XSS)
//  - mismo origen para el navegador: sin CORS entre web y API
//  - transmite el cuerpo como stream, así el SSE del chat llega palabra por palabra
//  - renovación transparente: si el acceso venció, se renueva y se repite la petición
import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { API_URL, TOKEN_COOKIE } from "@/lib/config";
import { refreshSession } from "@/lib/session";

export const dynamic = "force-dynamic";

const FORWARD_RESPONSE_HEADERS = ["content-type", "content-disposition", "cache-control", "x-accel-buffering", "retry-after"];

async function handler(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const store = await cookies();
  let token = store.get(TOKEN_COOKIE)?.value ?? (await refreshSession(store));
  if (!token) return Response.json({ detail: "No autenticado" }, { status: 401 });

  const { path } = await context.params;
  const url = `${API_URL}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  // El cuerpo se lee una vez: puede hacer falta reenviarlo tras renovar el token
  const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();

  const send = (accessToken: string) => {
    const headers = new Headers({ Authorization: `Bearer ${accessToken}` });
    for (const name of ["content-type", "accept"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    const forwardedFor = request.headers.get("x-forwarded-for");
    if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
    return fetch(url, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: request.signal, // si el usuario cierra la pestaña, se corta también hacia la API
    });
  };

  let upstream: Response;
  try {
    upstream = await send(token);
    if (upstream.status === 401) {
      // Token de acceso expirado entre una petición y otra: renovar y repetir UNA vez
      const renewed = await refreshSession(store);
      if (!renewed) return Response.json({ detail: "La sesión expiró" }, { status: 401 });
      token = renewed;
      upstream = await send(token);
    }
  } catch {
    return Response.json({ detail: "No se pudo conectar con el servidor" }, { status: 503 });
  }

  const responseHeaders = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  if (upstream.headers.get("content-type")?.startsWith("text/event-stream")) {
    // no-transform: evita que la compresión de Next acumule el stream
    responseHeaders.set("cache-control", "no-cache, no-transform");
  }

  const nullBody = upstream.status === 204 || upstream.status === 304;
  return new Response(nullBody ? null : upstream.body, { status: upstream.status, headers: responseHeaders });
}

export { handler as DELETE, handler as GET, handler as PATCH, handler as POST, handler as PUT };
