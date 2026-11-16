import { redirect } from "next/navigation";

export default async function TenantHome({ params }: { params: Promise<{ tenantSlug: string }> }) {
  const { tenantSlug } = await params;
  redirect(`/${tenantSlug}/search`);
}
