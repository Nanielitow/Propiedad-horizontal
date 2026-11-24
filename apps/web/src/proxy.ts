// Proxy de Next.js (antes "middleware"): pasa la ruta pedida al layout en una cabecera.
// Los layouts no reciben el pathname; sin esto, al pedir iniciar sesión se perdía a
// dónde iba el usuario (p. ej. al escanear el QR de un activo sin sesión abierta).
import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.set("x-ruta", request.nextUrl.pathname + request.nextUrl.search);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  // Solo páginas: ni la API, ni los recursos estáticos, ni archivos con extensión
  matcher: ["/((?!api/|_next/|favicon.ico|.*\\.[a-z0-9]+$).*)"],
};
