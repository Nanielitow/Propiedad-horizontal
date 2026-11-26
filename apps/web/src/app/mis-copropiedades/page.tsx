import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ConsolidadoView } from "@/components/consolidado/consolidado-view";
import { REFRESH_COOKIE } from "@/lib/config";
import { getMe } from "@/lib/server-api";

export const metadata: Metadata = { title: "Mis copropiedades" };

export default async function Page() {
  const me = await getMe();
  if (!me) {
    if ((await cookies()).get(REFRESH_COOKIE)) redirect("/api/auth/refresh?next=/mis-copropiedades");
    redirect("/login?next=/mis-copropiedades");
  }
  return <ConsolidadoView me={me} />;
}
