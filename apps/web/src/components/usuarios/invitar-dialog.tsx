"use client";

import { Loader2, MailPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { campoClase } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { baseUsuarios, type InvitacionOut, ROLES_INVITABLES } from "@/lib/cuentas";
import type { Role } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  tenantId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInvitado: () => void;
  /** Para dar acceso al portal a una persona del censo: datos ya conocidos y rol fijo de residente. */
  persona?: { id: string; nombre: string; email: string };
}

export function InvitarDialog({ tenantId, open, onOpenChange, onInvitado, persona }: Props) {
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState<Role>("AUXILIAR");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reiniciar solo al abrir (no cuando cambian props refrescadas con el diálogo abierto)
  useEffect(() => {
    if (!open) return;
    setNombre(persona?.nombre ?? "");
    setEmail(persona?.email ?? "");
    setRol(persona ? "RESIDENTE" : "AUXILIAR");
    setError(null);
  }, [open, persona]);

  async function invitar() {
    setEnviando(true);
    setError(null);
    try {
      const r = await api<InvitacionOut>(baseUsuarios(tenantId), {
        method: "POST",
        json: { nombre: nombre.trim(), email: email.trim(), rol, ...(persona ? { persona_id: persona.id } : {}) },
      });
      toast.success(
        r.nuevo
          ? `Invitación enviada a ${r.usuario.email}. Tiene 7 días para activar su cuenta.`
          : `${r.usuario.nombre} ya tenía cuenta: se le agregó el acceso y se le avisó por correo.`,
      );
      if (!r.correo_enviado) toast.warning("El correo no está configurado en este servidor: el aviso no saldrá.");
      onOpenChange(false);
      onInvitado();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo enviar la invitación.");
    } finally {
      setEnviando(false);
    }
  }

  const listo = nombre.trim().length >= 2 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{persona ? "Dar acceso al portal" : "Invitar usuario"}</DialogTitle>
          <DialogDescription>
            {persona
              ? "Le llegará un correo para definir su contraseña y entrar al portal de residentes con su unidad."
              : "Le llegará un correo para definir su contraseña. Si ya usa PH Gestión en otra copropiedad, entra con la misma cuenta."}
          </DialogDescription>
        </DialogHeader>

        <form
          id="invitar"
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (listo) void invitar();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="inv-nombre">Nombre completo</Label>
            <input
              id="inv-nombre"
              className={campoClase()}
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              disabled={!!persona}
              required
              autoFocus={!persona}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="inv-email">Correo electrónico</Label>
            <input
              id="inv-email"
              type="email"
              className={campoClase()}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={!!persona}
              placeholder="nombre@correo.com"
              required
            />
          </div>
          {!persona && (
            <fieldset className="space-y-1.5">
              <legend className="text-sm font-medium">Rol en la copropiedad</legend>
              <div className="grid gap-1.5" role="radiogroup">
                {ROLES_INVITABLES.map((r) => (
                  <button
                    key={r.rol}
                    type="button"
                    role="radio"
                    aria-checked={rol === r.rol}
                    onClick={() => setRol(r.rol)}
                    className={cn(
                      "rounded-md border px-3 py-2 text-left transition-colors",
                      rol === r.rol ? "border-primary bg-accent" : "hover:bg-muted/50",
                    )}
                  >
                    <p className="text-sm font-medium">{r.etiqueta}</p>
                    <p className="text-xs text-muted-foreground">{r.descripcion}</p>
                  </button>
                ))}
              </div>
            </fieldset>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="submit" form="invitar" disabled={!listo || enviando}>
            {enviando ? <Loader2 className="size-4 animate-spin" /> : <MailPlus className="size-4" />}
            Enviar invitación
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
