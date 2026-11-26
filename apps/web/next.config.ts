import type { NextConfig } from "next";

const securityHeaders = [
  // Nadie puede incrustar la app en un iframe (clickjacking)
  { key: "X-Frame-Options", value: "DENY" },
  // El navegador no "adivina" tipos de archivo (evita ejecutar un PDF como script)
  { key: "X-Content-Type-Options", value: "nosniff" },
  // No filtrar rutas internas (/los-pinos/documents/...) a sitios externos
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // La app no usa cámara, micrófono ni ubicación
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  // Solo HTTPS durante un año (el navegador lo ignora en http://localhost). Sin includeSubDomains
  // para no forzar HTTPS en otros subdominios del dominio.
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
];

const nextConfig: NextConfig = {
  // Bundle mínimo autocontenido para la imagen Docker de producción
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
