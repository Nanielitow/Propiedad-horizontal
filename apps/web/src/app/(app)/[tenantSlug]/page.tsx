import { redirect } from "next/navigation";

import { getMe } from "@/lib/server-api";

/** Entrada a la copropiedad según el rol: el técnico va a su lista de trabajo. */
export default async function TenantHome({ params }: { params: Promise<{ tenantSlug: string }> }) {
  const { tenantSlug } = await params;
  const me = await getMe();
  const rol = me?.memberships.find((m) => m.tenant_slug === tenantSlug)?.role;
  redirect(rol === "MANTENIMIENTO" ? `/${tenantSlug}/activos/mi-trabajo` : `/${tenantSlug}/search`);
}
