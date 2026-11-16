"use client";

// Cliente HTTP del navegador. Todas las llamadas van a /api/proxy/* (route handler
// de Next.js), que añade el token desde la cookie httpOnly y reenvía a FastAPI.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public data?: unknown,
  ) {
    super(message);
  }
}

/** Extrae un mensaje legible del formato de error de FastAPI. */
export function errorMessage(data: unknown, fallback = "Ocurrió un error inesperado"): string {
  if (!data || typeof data !== "object") return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return fallback;
}

export function redirectToLogin() {
  const next = encodeURIComponent(window.location.pathname);
  window.location.href = `/login?expired=1&next=${next}`;
}

interface ApiInit extends Omit<RequestInit, "body"> {
  json?: unknown;
}

export async function api<T>(path: string, init: ApiInit = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(`/api/proxy${path}`, {
    ...rest,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : undefined,
  });
  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError(401, "Tu sesión expiró");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, errorMessage(data, `Error ${res.status}`), data);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const fetcher = <T,>(path: string) => api<T>(path);
