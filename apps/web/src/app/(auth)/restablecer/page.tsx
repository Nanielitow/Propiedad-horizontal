import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { EnlaceDesdeFragmento } from "@/components/auth/enlace-desde-fragmento";

export const metadata: Metadata = { title: "Restablecer contraseña" };

export default function Page() {
  return (
    <AuthShell>
      <EnlaceDesdeFragmento modo="restablecer" />
    </AuthShell>
  );
}
