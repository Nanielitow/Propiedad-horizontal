import "server-only";

import { headers } from "next/headers";

import { API_URL } from "./config";

export interface Enlace {
  tipo: "INVITACION" | "RECUPERACION";
  email: string;
  nombre: string;
  copropiedad: string | null;
  requiere_politica: boolean;
  politica_version: string;
}

/** Datos del enlace del correo, consultados desde el servidor. null = inválido, usado o vencido. */
export async function leerEnlace(token: string | undefined): Promise<Enlace | null> {
  if (!token || token.length > 200) return null;
  try {
    const res = await fetch(`${API_URL}/api/v1/auth/enlaces/${encodeURIComponent(token)}`, {
      headers: { "x-forwarded-for": (await headers()).get("x-forwarded-for") ?? "" },
      cache: "no-store",
    });
    return res.ok ? ((await res.json()) as Enlace) : null;
  } catch {
    return null;
  }
}
