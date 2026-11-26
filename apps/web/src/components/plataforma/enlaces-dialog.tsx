"use client";

import { Check, Copy, MessageCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { campoClase } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { EnlaceInvitacion } from "@/lib/cuentas";

function mensaje(e: EnlaceInvitacion, copropiedad: string): string {
  return (
    `Hola, ${e.nombre.split(" ")[0]}. Le doy acceso a ${copropiedad} en PH Gestión. ` +
    `Para entrar, defina su contraseña con este enlace (vence en 7 días y solo sirve una vez):\n\n${e.enlace}\n\n` +
    `Después entra en https://app.propiedadhorizontal.app con su correo ${e.email}.`
  );
}

async function copiar(texto: string, aviso: string) {
  try {
    await navigator.clipboard.writeText(texto);
    toast.success(aviso);
  } catch {
    toast.error("No se pudo copiar: seleccione el texto y cópielo a mano.");
  }
}

/** Enlaces de activación para que el dueño los envíe él mismo (WhatsApp, chat). */
export function EnlacesDialog({
  enlaces,
  copropiedad,
  reemplazo,
  onOpenChange,
}: {
  enlaces: EnlaceInvitacion[] | null;
  copropiedad: string;
  /** true: los enlaces son nuevos y anularon los que se enviaron por correo */
  reemplazo: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [copiado, setCopiado] = useState<string | null>(null);

  return (
    <Dialog open={!!enlaces} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Enlace de activación</DialogTitle>
          <DialogDescription>
            {reemplazo
              ? "Se generó un enlace nuevo: el que se envió antes por correo ya no funciona. Envíelo por WhatsApp o chat."
              : "También se envió por correo. Si prefiere, cópielo y envíelo usted mismo por WhatsApp o chat."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-5">
          {enlaces?.map((e) => (
            <div key={e.email} className="space-y-2">
              <p className="text-sm">
                <span className="font-medium">{e.nombre}</span> <span className="text-muted-foreground">· {e.email}</span>
              </p>
              <input readOnly value={e.enlace} className={`${campoClase()} font-mono text-xs`} onFocus={(ev) => ev.target.select()} />
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  onClick={() => {
                    void copiar(e.enlace, "Enlace copiado");
                    setCopiado(e.email);
                  }}
                >
                  {copiado === e.email ? <Check className="size-4" /> : <Copy className="size-4" />}
                  Copiar enlace
                </Button>
                <Button size="sm" variant="outline" onClick={() => void copiar(mensaje(e, copropiedad), "Mensaje copiado: péguelo en WhatsApp")}>
                  <MessageCircle className="size-4" />
                  Copiar mensaje para WhatsApp
                </Button>
              </div>
            </div>
          ))}
          <p className="rounded-md border border-warning/25 bg-warning-soft px-3 py-2 text-xs text-warning">
            Quien tenga este enlace puede definir la contraseña de esa cuenta: envíelo solo a la persona, por un chat
            privado. Vence en 7 días y sirve una sola vez.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Listo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
