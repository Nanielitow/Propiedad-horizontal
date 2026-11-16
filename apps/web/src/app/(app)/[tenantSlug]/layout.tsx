import { cookies } from "next/headers";
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
    // Acceso vencido pero hay refresh: renovar (un route handler sí puede escribir cookies)
    if ((await cookies()).get(REFRESH_COOKIE)) redirect(`/api/auth/refresh?next=/${tenantSlug}`);
    redirect(`/login?expired=1&next=/${tenantSlug}/search`);
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
