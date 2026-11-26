import { Building } from "lucide-react";
import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { BotonSalir } from "@/components/auth/boton-salir";

export const metadata: Metadata = { title: "Sin copropiedades" };

export default function Page() {
  return (
    <AuthShell>
      <div className="flex size-10 items-center justify-center rounded-full bg-muted">
        <Building className="size-5 text-muted-foreground" />
      </div>
      <h2 className="mt-4 text-2xl font-semibold tracking-tight">Su cuenta aún no tiene copropiedades</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Su contraseña quedó guardada, pero ninguna copropiedad le ha dado acceso todavía (o se lo retiraron).
        Comuníquese con la administración de su copropiedad.
      </p>
      <BotonSalir className="mt-6 h-10 w-full" />
    </AuthShell>
  );
}
