"use client";

import { Camera, FileText, Loader2, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { Etiqueta, mensajeError } from "@/components/recaudos/comunes";
import { api, fetcher } from "@/lib/api";
import {
  baseActivos,
  type Color,
  CRITICIDAD,
  type Criticidad,
  type EntidadEvidencia,
  ESTADO_ACTIVO,
  type EstadoActivo,
  type Evidencia,
  MOMENTO,
  type MomentoEvidencia,
  SEMAFORO,
  TIPOS_EVIDENCIA,
} from "@/lib/activos";
import { fechaHora } from "@/lib/recaudos";
import { putWithProgress } from "@/lib/upload";
import { cn } from "@/lib/utils";

export function SemaforoBadge({ color, texto }: { color: Color | null; texto?: string }) {
  if (!color) return <Etiqueta tono="neutral">Sin plan</Etiqueta>;
  const s = SEMAFORO[color];
  return (
    <Etiqueta tono={s.tono} title={s.ayuda}>
      <span className={cn("mr-1.5 size-2 rounded-full", s.punto)} aria-hidden />
      {texto ?? s.label}
    </Etiqueta>
  );
}

export function SemaforoPunto({ color, className }: { color: Color | null; className?: string }) {
  return (
    <span
      className={cn("inline-block size-2.5 shrink-0 rounded-full", color ? SEMAFORO[color].punto : "bg-muted-foreground/30", className)}
      title={color ? SEMAFORO[color].ayuda : "Sin plan de mantenimiento"}
      aria-label={color ? SEMAFORO[color].label : "Sin plan"}
    />
  );
}

export function EstadoActivoBadge({ estado }: { estado: EstadoActivo }) {
  const e = ESTADO_ACTIVO[estado];
  return <Etiqueta tono={e.tono}>{e.label}</Etiqueta>;
}

export function CriticidadBadge({ criticidad }: { criticidad: Criticidad }) {
  const c = CRITICIDAD[criticidad];
  return <Etiqueta tono={c.tono}>{c.label}</Etiqueta>;
}

export function Fila({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="text-right font-medium">{v ?? "—"}</dd>
    </div>
  );
}

/** Campo de formulario con etiqueta y ayuda. */
export function Campo({
  label,
  ayuda,
  children,
  className,
}: {
  label: string;
  ayuda?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col gap-1.5 text-sm", className)}>
      <span className="font-medium">{label}</span>
      {children}
      {ayuda && <span className="text-xs text-muted-foreground">{ayuda}</span>}
    </label>
  );
}

export function textareaClase() {
  return "min-h-20 w-full rounded-md border bg-card px-3 py-2 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40";
}

/** Sube una evidencia: URL firmada, PUT directo al almacenamiento y registro en la API. */
export async function subirEvidencia(
  tenantId: string,
  entidad: EntidadEvidencia,
  entidadId: string,
  momento: MomentoEvidencia,
  file: File,
  onProgreso?: (p: number) => void,
): Promise<Evidencia> {
  const b = baseActivos(tenantId);
  const url = await api<{ storage_key: string; upload_url: string; headers: Record<string, string> }>(
    `${b}/evidencias/upload-url`,
    { method: "POST", json: { content_type: file.type, size_bytes: file.size } },
  );
  await putWithProgress(url.upload_url, file, url.headers, onProgreso ?? (() => {}));
  return api<Evidencia>(`${b}/evidencias`, {
    method: "POST",
    json: { entidad, entidad_id: entidadId, momento, storage_key: url.storage_key },
  });
}

/** Fotos y archivos de un registro, con botón para agregar (si el rol puede). */
export function Evidencias({
  tenantId,
  entidad,
  entidadId,
  momentos,
  puedeSubir,
}: {
  tenantId: string;
  entidad: EntidadEvidencia;
  entidadId: string;
  momentos: MomentoEvidencia[];
  puedeSubir: boolean;
}) {
  const clave = `${baseActivos(tenantId)}/evidencias?entidad=${entidad}&entidad_id=${entidadId}`;
  const { data, mutate } = useSWR<Evidencia[]>(clave, fetcher);
  const [momento, setMomento] = useState<MomentoEvidencia>(momentos[0] ?? "EVIDENCIA");
  const [progreso, setProgreso] = useState<number | null>(null);

  async function subir(files: FileList) {
    try {
      for (const f of Array.from(files)) {
        setProgreso(0);
        await subirEvidencia(tenantId, entidad, entidadId, momento, f, setProgreso);
      }
      toast.success("Evidencia guardada");
      await mutate();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setProgreso(null);
    }
  }

  return (
    <div className="space-y-3">
      {data && data.length > 0 ? (
        <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {data.map((e) => (
            <li key={e.id}>
              <a
                href={e.url}
                target="_blank"
                rel="noreferrer"
                className="group block overflow-hidden rounded-md border bg-secondary/40"
                title={`${MOMENTO[e.momento]} · ${fechaHora(e.created_at)}${e.subido_por ? ` · ${e.subido_por.nombre}` : ""}`}
              >
                {e.content_type.startsWith("image/") ? (
                  // <img> y no next/image: es una URL firmada temporal del almacenamiento
                  <img src={e.url} alt={MOMENTO[e.momento]} className="aspect-square w-full object-cover transition-opacity group-hover:opacity-90" />
                ) : (
                  <div className="flex aspect-square items-center justify-center">
                    <FileText className="size-6 text-muted-foreground" />
                  </div>
                )}
                <span className="block truncate px-1.5 py-1 text-[11px] text-muted-foreground">{MOMENTO[e.momento]}</span>
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{data ? "Sin fotos ni archivos." : "Cargando…"}</p>
      )}
      {puedeSubir && (
        <div className="flex flex-wrap items-center gap-2">
          {momentos.length > 1 && (
            <select
              aria-label="Tipo de evidencia"
              value={momento}
              onChange={(e) => setMomento(e.target.value as MomentoEvidencia)}
              className="h-9 rounded-md border bg-card px-2 text-sm"
            >
              {momentos.map((m) => (
                <option key={m} value={m}>
                  {MOMENTO[m]}
                </option>
              ))}
            </select>
          )}
          <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent/40">
            {progreso !== null ? <Loader2 className="size-4 animate-spin" /> : <Camera className="size-4" />}
            {progreso !== null ? `Subiendo… ${progreso} %` : "Agregar foto o PDF"}
            <input
              type="file"
              accept={TIPOS_EVIDENCIA}
              multiple
              className="sr-only"
              disabled={progreso !== null}
              onChange={(e) => {
                if (e.target.files?.length) void subir(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      )}
    </div>
  );
}

/** Selector de fotos para un formulario: se suben después de crear el registro. */
export function FotosPendientes({
  etiqueta,
  archivos,
  onCambio,
}: {
  etiqueta: string;
  archivos: File[];
  onCambio: (f: File[]) => void;
}) {
  return (
    <div className="space-y-1.5">
      <span className="text-sm font-medium">{etiqueta}</span>
      <div className="flex flex-wrap items-center gap-2">
        {archivos.map((f, i) => (
          <span key={`${f.name}-${i}`} className="inline-flex items-center gap-1 rounded-md border bg-secondary/50 px-2 py-1 text-xs">
            {f.name.length > 22 ? `${f.name.slice(0, 20)}…` : f.name}
            <button type="button" onClick={() => onCambio(archivos.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-foreground" aria-label={`Quitar ${f.name}`}>
              ×
            </button>
          </span>
        ))}
        <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-dashed px-2.5 text-xs text-muted-foreground hover:border-primary/40 hover:bg-accent/40">
          <Plus className="size-3.5" /> Foto
          <input
            type="file"
            accept={TIPOS_EVIDENCIA}
            multiple
            className="sr-only"
            onChange={(e) => {
              if (e.target.files) onCambio([...archivos, ...Array.from(e.target.files)]);
              e.target.value = "";
            }}
          />
        </label>
      </div>
    </div>
  );
}

/** Revalida todas las consultas del módulo (lista, hoja de vida, calendario…) tras un cambio. */
export function useRefrescarActivos() {
  const { mutate } = useSWRConfig();
  return (tenantId: string) =>
    mutate((clave) => typeof clave === "string" && clave.startsWith(baseActivos(tenantId)), undefined, { revalidate: true });
}
