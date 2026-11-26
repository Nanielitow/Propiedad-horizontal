import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { PlataformaView } from "@/components/plataforma/plataforma-view";
import { REFRESH_COOKIE } from "@/lib/config";
import { getMe } from "@/lib/server-api";

export const metadata: Metadata = { title: "Plataforma" };

export default async function Page() {
  const me = await getMe();
  if (!me) {
    if ((await cookies()).get(REFRESH_COOKIE)) redirect("/api/auth/refresh?next=/plataforma");
    redirect("/login?next=/plataforma");
  }
  if (!me.user.is_platform_admin) notFound();
  return <PlataformaView me={me} />;
}
