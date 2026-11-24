import { cookies, headers } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { REFRESH_COOKIE } from "@/lib/config";
import { getMe } from "@/lib/server-api";

export default async function TenantLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ tenantSlug: string }>;
}) {
  const { tenantSlug } = await params;
  const me = await getMe();
  if (!me) {
    // Volver a la página pedida tras iniciar sesión (la pone src/proxy.ts); solo rutas de esta copropiedad
    const pedida = (await headers()).get("x-ruta");
    const destino = pedida?.startsWith(`/${tenantSlug}/`) ? pedida : `/${tenantSlug}/search`;
    // Acceso vencido pero hay refresh: renovar (un route handler sí puede escribir cookies)
    if ((await cookies()).get(REFRESH_COOKIE)) redirect(`/api/auth/refresh?next=${encodeURIComponent(destino)}`);
    redirect(`/login?expired=1&next=${encodeURIComponent(destino)}`);
  }

  const membership = me.memberships.find((m) => m.tenant_slug === tenantSlug);
  // Copropiedad a la que el usuario no pertenece: igual que la API, no se revela si existe
  if (!membership) notFound();

  return (
    <AppShell user={me.user} memberships={me.memberships} current={membership}>
      {children}
    </AppShell>
  );
}
