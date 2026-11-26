import { LinkIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export function EnlaceInvalido({ recuperacion }: { recuperacion?: boolean }) {
  return (
    <div>
      <div className="flex size-10 items-center justify-center rounded-full bg-muted">
        <LinkIcon className="size-5 text-muted-foreground" />
      </div>
      <h2 className="mt-4 text-2xl font-semibold tracking-tight">El enlace ya no sirve</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Los enlaces son de un solo uso y vencen {recuperacion ? "en 1 hora" : "en 7 días"}. Si ya definió su
        contraseña, entre normalmente. Si no, pida un enlace nuevo: le llegará al mismo correo.
      </p>
      <div className="mt-6 flex flex-col gap-2">
        <Button asChild className="h-10">
          <Link href="/recuperar">Pedir un enlace nuevo</Link>
        </Button>
        <Button asChild variant="outline" className="h-10">
          <Link href="/login">Ir a iniciar sesión</Link>
        </Button>
      </div>
    </div>
  );
}
