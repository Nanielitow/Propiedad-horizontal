"use client";

import { Loader2, Lock, Paperclip, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { base, ESTADO, type EstadoRecaudo, type Tono } from "@/lib/recaudos";
import { putWithProgress } from "@/lib/upload";
import { cn } from "@/lib/utils";

export const TONO: Record<Tono, string> = {
  neutral: "bg-secondary text-secondary-foreground border-transparent",
  info: "bg-info-soft text-primary border-primary/15",
  success: "bg-success-soft text-success border-success/25",
  warning: "bg-warning-soft text-warning border-warning/25",
  danger: "bg-destructive/10 text-destructive border-destructive/25",
};

export function Etiqueta({ tono, children, title }: { tono: Tono; children: React.ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cn("inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONO[tono])}
    >
      {children}
    </span>
  );
}

export function EstadoBadge({ estado }: { estado: EstadoRecaudo }) {
  const e = ESTADO[estado];
  return (
    <Etiqueta tono={e.tono} title={e.ayuda}>
      {e.label}
    </Etiqueta>
  );
}

export function Kpi({
  titulo,
  valor,
  detalle,
  destacado,
  icono: Icono,
}: {
  titulo: string;
  valor: string;
  detalle?: React.ReactNode;
  destacado?: boolean;
  icono?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className={cn("rounded-lg border bg-card p-4", destacado && "border-warning/40 bg-warning-soft/40")}>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {Icono && <Icono className="size-4" />}
        {titulo}
      </div>
      <p className="mt-1.5 text-2xl font-semibold tracking-tight tabular-nums">{valor}</p>
      {detalle && <div className="mt-1 text-xs text-muted-foreground">{detalle}</div>}
    </div>
  );
}

export function Seccion({
  titulo,
  descripcion,
  acciones,
  children,
  className,
}: {
  titulo: string;
  descripcion?: string;
  acciones?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border bg-card", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">{titulo}</h2>
          {descripcion && <p className="text-xs text-muted-foreground">{descripcion}</p>}
        </div>
        {acciones && <div className="flex items-center gap-2">{acciones}</div>}
      </div>
      {children}
    </section>
  );
}

export function SinAcceso({ texto = "Su rol no tiene acceso a esta sección" }: { texto?: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
      <Lock className="size-6 text-muted-foreground" />
      <p className="mt-3 font-medium">{texto}</p>
    </div>
  );
}

export function Vacio({ icono: Icono, titulo, texto }: { icono: React.ComponentType<{ className?: string }>; titulo: string; texto?: string }) {
  return (
    <div className="px-4 py-10 text-center">
      <div className="mx-auto flex size-10 items-center justify-center rounded-lg bg-accent text-primary">
        <Icono className="size-5" />
      </div>
      <p className="mt-3 text-sm font-medium">{titulo}</p>
      {texto && <p className="mx-auto mt-1 max-w-sm text-xs text-muted-foreground">{texto}</p>}
    </div>
  );
}

export function mensajeError(e: unknown): string {
  return e instanceof ApiError || e instanceof Error ? e.message : "Ocurrió un error inesperado";
}

/** Diálogo que exige un motivo escrito (anular, rechazar). */
export function MotivoDialog({
  abierto,
  onCambio,
  titulo,
  descripcion,
  boton,
  minimo = 10,
  peligro = true,
  onConfirmar,
}: {
  abierto: boolean;
  onCambio: (v: boolean) => void;
  titulo: string;
  descripcion: string;
  boton: string;
  minimo?: number;
  peligro?: boolean;
  onConfirmar: (motivo: string) => Promise<void>;
}) {
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const valido = motivo.trim().length >= minimo;

  async function confirmar() {
    setEnviando(true);
    try {
      await onConfirmar(motivo.trim());
      setMotivo("");
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription>{descripcion}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="motivo">Motivo</Label>
          <Textarea id="motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} rows={3} autoFocus />
          <p className="text-xs text-muted-foreground">
            Queda registrado en la auditoría con su nombre. Mínimo {minimo} caracteres.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button variant={peligro ? "destructive" : "default"} disabled={!valido || enviando} onClick={confirmar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            {boton}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const TIPOS_SOPORTE = "application/pdf,image/jpeg,image/png,image/webp";

/** Selector de soporte: sube el archivo al almacenamiento y devuelve su clave. */
export function SoporteInput({
  tenantId,
  valor,
  onCambio,
}: {
  tenantId: string;
  valor: string | null;
  onCambio: (key: string | null) => void;
}) {
  const [progreso, setProgreso] = useState<number | null>(null);
  const [nombre, setNombre] = useState<string | null>(null);

  async function subir(file: File) {
    setProgreso(0);
    try {
      const r = await api<{ soporte_key: string; upload_url: string; headers: Record<string, string> }>(
        `${base(tenantId)}/soportes/upload-url`,
        { method: "POST", json: { content_type: file.type, size_bytes: file.size } },
      );
      await putWithProgress(r.upload_url, file, r.headers, setProgreso);
      setNombre(file.name);
      onCambio(r.soporte_key);
    } catch (e) {
      toast.error(mensajeError(e));
      onCambio(null);
    } finally {
      setProgreso(null);
    }
  }

  if (valor) {
    return (
      <div className="flex items-center gap-2 rounded-md border bg-secondary/50 px-3 py-2 text-sm">
        <Paperclip className="size-4 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate">{nombre ?? "Soporte adjunto"}</span>
        <button
          type="button"
          className="rounded p-0.5 text-muted-foreground hover:text-foreground"
          onClick={() => onCambio(null)}
          aria-label="Quitar soporte"
        >
          <X className="size-4" />
        </button>
      </div>
    );
  }
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent/40">
      {progreso !== null ? <Loader2 className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
      {progreso !== null ? `Subiendo… ${progreso} %` : "Adjuntar soporte (PDF o foto)"}
      <input
        type="file"
        accept={TIPOS_SOPORTE}
        className="sr-only"
        disabled={progreso !== null}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void subir(f);
          e.target.value = "";
        }}
      />
    </label>
  );
}

export function campoClase(error?: boolean) {
  return cn(
    "h-9 w-full rounded-md border bg-card px-3 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40",
    error && "border-destructive",
  );
}
