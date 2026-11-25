import { redirect } from "next/navigation";

import { getMe } from "@/lib/server-api";

/** Entrada a la copropiedad según el rol: el técnico va a su lista de trabajo y el residente a su inicio. */
export default async function TenantHome({ params }: { params: Promise<{ tenantSlug: string }> }) {
  const { tenantSlug } = await params;
  const me = await getMe();
  const rol = me?.memberships.find((m) => m.tenant_slug === tenantSlug)?.role;
  const destino = rol === "MANTENIMIENTO" ? "activos/mi-trabajo" : rol === "RESIDENTE" ? "inicio" : "search";
  redirect(`/${tenantSlug}/${destino}`);
}
