// URL de la API vista desde el SERVIDOR de Next.js (route handlers, server components).
// El navegador nunca llama a la API directamente: pasa por /api/proxy (mismo origen),
// así el token vive en una cookie httpOnly que JavaScript no puede leer.
export const API_URL = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const TOKEN_COOKIE = "ph_token"; // acceso: 15 min
export const REFRESH_COOKIE = "ph_refresh"; // renovación: 7 días, rotativo

export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
