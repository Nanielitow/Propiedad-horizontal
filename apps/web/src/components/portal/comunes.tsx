"use client";

import { FileText, ImageIcon, Loader2, Paperclip, Star, X } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { useSWRConfig } from "swr";

import { Etiqueta, mensajeError } from "@/components/recaudos/comunes";
import { api } from "@/lib/api";
import {
  type Adjunto,
  basePortal,
  ESTADO_PQRS,
  ESTADO_RESERVA,
  type EstadoPqrs,
  type EstadoReserva,
  PRIORIDAD_PQRS,
  type PrioridadPqrs,
  type PqrsResumen,
  textoPlazo,
} from "@/lib/portal";
import { putWithProgress } from "@/lib/upload";
import { cn } from "@/lib/utils";

export function EstadoPqrsBadge({ estado }: { estado: EstadoPqrs }) {
  const e = ESTADO_PQRS[estado];
  return (
    <Etiqueta tono={e.tono} title={e.ayuda}>
      {e.label}
    </Etiqueta>
  );
}

export function PrioridadBadge({ prioridad }: { prioridad: PrioridadPqrs }) {
  const p = PRIORIDAD_PQRS[prioridad];
  return <Etiqueta tono={p.tono}>Prioridad {p.label.toLowerCase()}</Etiqueta>;
}

export function EstadoReservaBadge({ estado }: { estado: EstadoReserva }) {
  const e = ESTADO_RESERVA[estado];
  return <Etiqueta tono={e.tono}>{e.label}</Etiqueta>;
}

/** Plazo de respuesta: rojo si venció, ámbar si quedan 3 días hábiles o menos. */
export function Plazo({ p }: { p: Pick<PqrsResumen, "dias_habiles_restantes" | "vencida"> }) {
  if (p.dias_habiles_restantes === null) return null;
  const tono = p.vencida ? "text-destructive" : p.dias_habiles_restantes <= 3 ? "text-warning" : "text-muted-foreground";
  return <span className={cn("text-xs", tono)}>{textoPlazo(p)}</span>;
}

export function Markdown({ texto, className }: { texto: string; className?: string }) {
  return (
    <div className={cn("answer text-sm", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-primary underline">
              {children}
            </a>
          ),
        }}
      >
        {texto}
      </ReactMarkdown>
    </div>
  );
}

export function Estrellas({ valor, onCambio, tam = "size-6" }: { valor: number; onCambio?: (v: number) => void; tam?: string }) {
  return (
    <div className="flex gap-1" role={onCambio ? "radiogroup" : undefined} aria-label="Calificación">
      {[1, 2, 3, 4, 5].map((n) =>
        onCambio ? (
          <button key={n} type="button" role="radio" aria-checked={valor === n} aria-label={`${n} de 5`} onClick={() => onCambio(n)} className="rounded p-0.5 hover:bg-accent">
            <Star className={cn(tam, n <= valor ? "fill-warning text-warning" : "text-muted-foreground")} />
          </button>
        ) : (
          <Star key={n} className={cn(tam, n <= valor ? "fill-warning text-warning" : "text-muted-foreground/40")} aria-hidden />
        ),
      )}
      {!onCambio && <span className="sr-only">{valor} de 5</span>}
    </div>
  );
}

export function ListaAdjuntos({ adjuntos }: { adjuntos: Adjunto[] }) {
  if (!adjuntos.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {adjuntos.map((a) => (
        <a key={a.url} href={a.url} target="_blank" rel="noreferrer" className="inline-flex max-w-56 items-center gap-1.5 rounded-md border bg-card px-2 py-1 text-xs hover:bg-accent">
          {a.tipo.startsWith("image/") ? <ImageIcon className="size-3.5 shrink-0" /> : <FileText className="size-3.5 shrink-0" />}
          <span className="truncate">{a.nombre}</span>
        </a>
      ))}
    </div>
  );
}

export interface AdjuntoNuevo {
  key: string;
  nombre: string;
}

const TIPOS = "image/jpeg,image/png,image/webp,application/pdf";

/** Sube fotos o PDF al almacenamiento (URL firmada) y devuelve sus claves. Máximo 5. */
export function AdjuntosInput({ tenantId, valor, onCambio }: { tenantId: string; valor: AdjuntoNuevo[]; onCambio: (v: AdjuntoNuevo[]) => void }) {
  const [subiendo, setSubiendo] = useState<number | null>(null);

  async function subir(archivos: FileList | null) {
    if (!archivos?.length) return;
    let lista = [...valor];
    for (const file of Array.from(archivos).slice(0, 5 - lista.length)) {
      setSubiendo(0);
      try {
        const r = await api<{ storage_key: string; upload_url: string; headers: Record<string, string> }>(`${basePortal(tenantId)}/adjuntos/upload-url`, {
          method: "POST",
          json: { content_type: file.type, size_bytes: file.size },
        });
        await putWithProgress(r.upload_url, file, r.headers, setSubiendo);
        lista = [...lista, { key: r.storage_key, nombre: file.name }];
        onCambio(lista);
      } catch (e) {
        toast.error(`${file.name}: ${mensajeError(e)}`);
      }
    }
    setSubiendo(null);
  }

  return (
    <div className="space-y-2">
      {valor.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {valor.map((a) => (
            <li key={a.key} className="inline-flex items-center gap-1 rounded-md border bg-secondary/50 px-2 py-1 text-xs">
              <Paperclip className="size-3.5" />
              <span className="max-w-40 truncate">{a.nombre}</span>
              <button type="button" onClick={() => onCambio(valor.filter((x) => x.key !== a.key))} aria-label={`Quitar ${a.nombre}`} className="rounded p-0.5 hover:bg-accent">
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {valor.length < 5 && (
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent/50">
          {subiendo !== null ? <Loader2 className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
          {subiendo !== null ? `Subiendo… ${subiendo} %` : "Adjuntar fotos o PDF"}
          <input type="file" accept={TIPOS} multiple className="sr-only" disabled={subiendo !== null} onChange={(e) => { void subir(e.target.files); e.target.value = ""; }} />
        </label>
      )}
    </div>
  );
}

export function useRefrescarPortal() {
  const { mutate } = useSWRConfig();
  return (tenantId: string) =>
    mutate((clave) => typeof clave === "string" && clave.startsWith(basePortal(tenantId)), undefined, { revalidate: true });
}
