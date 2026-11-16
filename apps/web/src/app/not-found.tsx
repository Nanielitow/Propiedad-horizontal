import { FileQuestion } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6 text-center">
      <FileQuestion className="size-8 text-muted-foreground" />
      <h1 className="mt-4 text-xl font-semibold">Página no encontrada</h1>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">
        La dirección no existe o no tiene acceso a esta copropiedad.
      </p>
      <Button asChild className="mt-6">
        <Link href="/">Volver al inicio</Link>
      </Button>
    </div>
  );
}
