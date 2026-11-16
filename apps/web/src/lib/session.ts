import "server-only";

import { API_URL, REFRESH_COOKIE, TOKEN_COOKIE } from "./config";

/*
  Sesión en cookies httpOnly (el JavaScript del navegador nunca ve los tokens):
    ph_token    token de acceso, 15 min
    ph_refresh  token de renovación, 7 días; la API lo ROTA en cada uso
*/

interface CookieStore {
  get(name: string): { value: string } | undefined;
  set(name: string, value: string, options: Record<string, unknown>): unknown;
  delete(name: string): unknown;
}

export interface TokenPair {
  access_token: string;
  expires_in: number;
  refresh_token: string;
  refresh_expires_in: number;
}

const base = { httpOnly: true, sameSite: "lax" as const, secure: process.env.NODE_ENV === "production", path: "/" };

export function setSession(store: CookieStore, tokens: TokenPair) {
  store.set(TOKEN_COOKIE, tokens.access_token, { ...base, maxAge: tokens.expires_in });
  store.set(REFRESH_COOKIE, tokens.refresh_token, { ...base, maxAge: tokens.refresh_expires_in });
}

export function clearSession(store: CookieStore) {
  store.delete(TOKEN_COOKIE);
  store.delete(REFRESH_COOKIE);
}

/** Renueva la sesión con el refresh token. Devuelve el nuevo token de acceso o
 *  null (refresh ausente, expirado, revocado o ya usado: hay que volver a entrar). */
export async function refreshSession(store: CookieStore): Promise<string | null> {
  const refresh = store.get(REFRESH_COOKIE)?.value;
  if (!refresh) return null;
  try {
    const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    });
    if (!res.ok) {
      clearSession(store);
      return null;
    }
    const tokens = (await res.json()) as TokenPair;
    setSession(store, tokens);
    return tokens.access_token;
  } catch {
    return null; // API caída: no se borra la sesión
  }
}
