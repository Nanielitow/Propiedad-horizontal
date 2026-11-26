import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { RecuperarForm } from "@/components/auth/recuperar-form";

export const metadata: Metadata = { title: "Recuperar contraseña" };

export default function Page() {
  return (
    <AuthShell>
      <RecuperarForm />
    </AuthShell>
  );
}
