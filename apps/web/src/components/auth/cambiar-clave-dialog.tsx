"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { CamposClave, claveValida } from "@/components/auth/clave-form";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";

export function CambiarClaveDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [actual, setActual] = useState("");
  const [clave, setClave] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!open) return;
    setActual("");
    setClave("");
    setConfirmar("");
    setError(null);
  }, [open]);

  async function guardar() {
    setEnviando(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/cambiar-clave", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actual, nueva: clave }),
      });
      if (!res.ok) {
        setError(errorMessage(await res.json().catch(() => null), "No se pudo cambiar la contraseña."));
        return;
      }
      toast.success("Contraseña actualizada. Se cerraron las sesiones abiertas en otros equipos.");
      onOpenChange(false);
    } catch {
      setError("No se pudo conectar con el servidor.");
    } finally {
      setEnviando(false);
    }
  }

  const listo = actual.length > 0 && claveValida(clave, confirmar);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Cambiar contraseña</DialogTitle>
          <DialogDescription>Las sesiones abiertas en otros equipos se cerrarán; en este seguirá dentro.</DialogDescription>
        </DialogHeader>
        <form
          id="cambiar-clave"
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (listo) void guardar();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="actual">Contraseña actual</Label>
            <Input
              id="actual"
              type="password"
              autoComplete="current-password"
              value={actual}
              onChange={(e) => setActual(e.target.value)}
              required
              autoFocus
              className="h-10"
            />
          </div>
          <CamposClave clave={clave} confirmar={confirmar} onClave={setClave} onConfirmar={setConfirmar} />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="submit" form="cambiar-clave" disabled={!listo || enviando}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar contraseña
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
