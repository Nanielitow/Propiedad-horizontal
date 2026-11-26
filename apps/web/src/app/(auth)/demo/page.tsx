import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Demostración" };

// Entrada a los conjuntos de ejemplo (datos ficticios) para presentaciones comerciales.
// El login normal no muestra estas cuentas.
export default function Page() {
  return (
    <AuthShell>
      <Suspense>
        <LoginForm demo />
      </Suspense>
    </AuthShell>
  );
}
