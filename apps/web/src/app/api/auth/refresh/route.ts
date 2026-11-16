// Renovación para navegaciones de página: los Server Components no pueden escribir
// cookies, así que cuando el token de acceso venció, el layout redirige aquí; este
// route handler renueva la sesión y devuelve al usuario a donde iba.
import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

import { refreshSession } from "@/lib/session";

export async function GET(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get("next") ?? "/";
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/"; // evita redirecciones abiertas
  const token = await refreshSession(await cookies());
  const target = token ? next : `/login?expired=1&next=${encodeURIComponent(next)}`;
  return NextResponse.redirect(new URL(target, request.url));
}
