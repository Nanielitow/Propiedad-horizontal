import { cookies } from "next/headers";

import { API_URL, REFRESH_COOKIE } from "@/lib/config";
import { clearSession } from "@/lib/session";

export async function POST() {
  const store = await cookies();
  const refresh = store.get(REFRESH_COOKIE)?.value;
  if (refresh) {
    // Revoca el refresh token en el servidor: aunque alguien lo hubiera copiado, ya no sirve
    await fetch(`${API_URL}/api/v1/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    }).catch(() => undefined);
  }
  clearSession(store);
  return new Response(null, { status: 204 });
}
