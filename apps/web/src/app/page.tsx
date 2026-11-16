import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { REFRESH_COOKIE } from "@/lib/config";
import { getMe } from "@/lib/server-api";

export default async function Home() {
  const me = await getMe();
  const first = me?.memberships[0];
  if (first) redirect(`/${first.tenant_slug}/search`);
  if (!me && (await cookies()).get(REFRESH_COOKIE)) redirect("/api/auth/refresh?next=/");
  redirect("/login");
}
