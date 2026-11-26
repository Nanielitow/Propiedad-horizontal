import type { Metadata } from "next";

import { AuthShell } from "@/components/auth/auth-shell";
import { ClaveDesdeEnlace } from "@/components/auth/clave-form";
import { EnlaceInvalido } from "@/components/auth/enlace-invalido";
import { leerEnlace } from "@/lib/enlace";

export const metadata: Metadata = { title: "Restablecer contraseña" };
export const dynamic = "force-dynamic";

export default async function Page({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  const enlace = await leerEnlace(token);
  return (
    <AuthShell>
      {enlace && token && enlace.tipo === "RECUPERACION" ? (
        <ClaveDesdeEnlace
          modo="restablecer"
          token={token}
          nombre={enlace.nombre}
          email={enlace.email}
          copropiedad={enlace.copropiedad}
          requierePolitica={false}
        />
      ) : (
        <EnlaceInvalido recuperacion />
      )}
    </AuthShell>
  );
}
