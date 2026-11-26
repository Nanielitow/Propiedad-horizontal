import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { EnlaceDesdeFragmento } from "@/components/auth/enlace-desde-fragmento";

export const metadata: Metadata = { title: "Activar cuenta" };

export default function Page() {
  return (
    <AuthShell>
      <EnlaceDesdeFragmento modo="activar" />
    </AuthShell>
  );
}
