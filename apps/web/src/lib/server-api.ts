import "server-only";

import { cookies } from "next/headers";

import { API_URL, TOKEN_COOKIE } from "./config";
import type { Me } from "./types";

/** Usuario actual desde un Server Component. null si no hay sesión válida. */
export async function getMe(): Promise<Me | null> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (!token) return null;
  try {
    const res = await fetch(`${API_URL}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    return res.ok ? ((await res.json()) as Me) : null;
  } catch {
    return null;
  }
}
