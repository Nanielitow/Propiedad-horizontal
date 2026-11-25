"use client";

import { Inbox, Loader2, MessageSquare, Plus, Search, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo, textareaClase } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Kpi, mensajeError, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import {
  basePortal,
  CANAL_PQRS,
  type CanalPqrs,
  CATEGORIA_PQRS,
  type CategoriaPqrs,
  type PqrsDetalle,
  type PqrsResumen,
  puedePortal,
  type ResumenBandeja,
  TIPO_PQRS,
  type TipoPqrs,
} from "@/lib/portal";
import { fechaCorta } from "@/lib/recaudos";
import { baseUnidades, type UnidadesPagina, type UnidadDetalle } from "@/lib/unidades";
import { cn } from "@/lib/utils";

import { type AdjuntoNuevo, AdjuntosInput, EstadoPqrsBadge, Plazo, PrioridadBadge, useRefrescarPortal } from "./comunes";

type Vista = "abiertas" | "vencidas" | "sin_asignar" | "mias" | "todas";

export function PqrsListaView() {
  const { tenant } = useTenant();
  const b = basePortal(tenant.tenant_id);
  const residente = puedePortal(tenant.role, "residente");
  const personal = puedePortal(tenant.role, "verPqrs");
  const router = useRouter();
  const [vista, setVista] = useState<Vista>(residente ? "todas" : "abiertas");
  const [categoria, setCategoria] = useState("");
  const [texto, setTexto] = useState("");
  const [nueva, setNueva] = useState(false);

  const consulta = useMemo(() => {
    const q = new URLSearchParams();
    if (vista === "abiertas") q.set("solo_abiertas", "true");
    if (vista === "vencidas") q.set("vencidas", "true");
    if (vista === "sin_asignar") { q.set("sin_asignar", "true"); q.set("solo_abiertas", "true"); }
    if (vista === "mias") q.set("asignadas_a_mi", "true");
    if (categoria) q.set("categoria", categoria);
    if (texto.trim()) q.set("texto", texto.trim());
    return q.toString();
  }, [vista, categoria, texto]);
  const { data, isLoading } = useSWR<PqrsResumen[]>(residente || personal ? `${b}/pqrs?${consulta}` : null, fetcher, { keepPreviousData: true });
  const { data: resumen } = useSWR<ResumenBandeja>(personal ? `${b}/pqrs/resumen` : null, fetcher);

  if (!residente && !personal) return <SinAcceso />;
  const base = residente ? "mi-portal" : "portal";
  const puedeRadicar = residente || puedePortal(tenant.role, "gestionarPqrs");

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title={residente ? "Mis PQRS" : "PQRS"}
        description={residente ? "Peticiones, quejas, reclamos, sugerencias y felicitaciones a la administración." : "Bandeja de peticiones, quejas, reclamos y sugerencias de los residentes."}
        actions={
          puedeRadicar && (
            <Button onClick={() => setNueva(true)}>
              <Plus className="size-4" /> {residente ? "Nueva PQRS" : "Radicar PQRS"}
            </Button>
          )
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        {resumen && (
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            <Kpi titulo="Abiertas" valor={String(resumen.abiertas)} detalle={resumen.sin_asignar ? `${resumen.sin_asignar} sin asignar` : "Todas asignadas"} />
            <Kpi titulo="Vencidas" valor={String(resumen.vencidas)} destacado={resumen.vencidas > 0} detalle={resumen.por_vencer ? `${resumen.por_vencer} vencen en 3 días hábiles o menos` : "Plazo: 15 días hábiles"} />
            <Kpi titulo="Tiempo de respuesta" valor={resumen.tiempo_respuesta_promedio_dias ? `${Number(resumen.tiempo_respuesta_promedio_dias).toLocaleString("es-CO")} días` : "—"} detalle="Promedio en días hábiles" />
            <Kpi titulo="Satisfacción" valor={resumen.satisfaccion_promedio ? `${Number(resumen.satisfaccion_promedio).toLocaleString("es-CO")} / 5` : "—"} detalle="Calificación de los residentes" />
          </div>
        )}

        <div className="flex flex-wrap items-end gap-2">
          {personal && (
            <div className="flex flex-wrap gap-1 rounded-lg bg-muted p-1 text-sm" role="group" aria-label="Vista">
              {(
                [
                  ["abiertas", "Abiertas"],
                  ["vencidas", "Vencidas"],
                  ["sin_asignar", "Sin asignar"],
                  ["mias", "Asignadas a mí"],
                  ["todas", "Todas"],
                ] as [Vista, string][]
              ).map(([v, label]) => (
                <button key={v} type="button" aria-pressed={vista === v} onClick={() => setVista(v)} className={cn("rounded-md px-3 py-1.5 font-medium", vista === v ? "bg-card shadow-sm" : "text-muted-foreground")}>
                  {label}
                </button>
              ))}
            </div>
          )}
          <div className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder={personal ? "Asunto, solicitante o número" : "Buscar"} className="pl-8" aria-label="Buscar PQRS" />
          </div>
          {personal && (
            <select aria-label="Categoría" value={categoria} onChange={(e) => setCategoria(e.target.value)} className={cn(campoClase(), "w-48")}>
              <option value="">Toda categoría</option>
              {(Object.keys(CATEGORIA_PQRS) as CategoriaPqrs[]).map((c) => (
                <option key={c} value={c}>
                  {CATEGORIA_PQRS[c]}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="rounded-lg border bg-card">
          {isLoading && !data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : !data?.length ? (
            <Vacio icono={Inbox} titulo={residente ? "No ha radicado PQRS" : "No hay PQRS en esta vista"} texto={residente ? "Si tiene una petición, queja, reclamo o sugerencia, radíquela aquí y siga su respuesta." : undefined} />
          ) : (
            <ul className="divide-y">
              {data.map((p) => (
                <li key={p.id}>
                  <Link href={`/${tenant.tenant_slug}/${base}/pqrs/${p.id}`} className="flex flex-wrap items-start gap-x-4 gap-y-1 px-4 py-3 hover:bg-accent/40">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs text-muted-foreground">{p.radicado}</span>
                        <EstadoPqrsBadge estado={p.estado} />
                        {p.prioridad === "ALTA" && <PrioridadBadge prioridad="ALTA" />}
                      </div>
                      <p className="mt-0.5 font-medium">{p.asunto}</p>
                      <p className="text-xs text-muted-foreground">
                        {TIPO_PQRS[p.tipo].label} · {CATEGORIA_PQRS[p.categoria]}
                        {personal && ` · ${p.solicitante_nombre}${p.unidad ? ` (${p.unidad})` : ""}`}
                        {personal && p.canal !== "PORTAL" && ` · ${CANAL_PQRS[p.canal].toLowerCase()}`}
                        {personal && (p.asignado_a ? ` · asignada a ${p.asignado_a}` : " · sin asignar")}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-0.5 text-right">
                      <span className="text-xs text-muted-foreground">{fechaCorta(p.created_at)}</span>
                      <Plazo p={p} />
                      {p.mensajes > 0 && (
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                          <MessageSquare className="size-3.5" /> {p.mensajes}
                        </span>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <NuevaPqrsDialog abierto={nueva} onCambio={setNueva} onRadicada={(p) => router.push(`/${tenant.tenant_slug}/${base}/pqrs/${p.id}`)} />
    </div>
  );
}

function NuevaPqrsDialog({ abierto, onCambio, onRadicada }: { abierto: boolean; onCambio: (v: boolean) => void; onRadicada: (p: PqrsDetalle) => void }) {
  const { tenant } = useTenant();
  const residente = tenant.role === "RESIDENTE";
  const refrescar = useRefrescarPortal();
  // El residente elige entre sus unidades; el personal, entre todas
  const { data: misUnidades } = useSWR<UnidadDetalle[]>(abierto && residente ? `/tenants/${tenant.tenant_id}/mi-unidad` : null, fetcher);
  const { data: todas } = useSWR<UnidadesPagina>(abierto && !residente ? `${baseUnidades(tenant.tenant_id)}?solo_principales=true&page_size=200` : null, fetcher);
  const opciones = residente ? (misUnidades ?? []).map((u) => ({ id: u.id, etiqueta: u.etiqueta })) : (todas?.items ?? []).map((u) => ({ id: u.id, etiqueta: u.etiqueta }));
  const [tipo, setTipo] = useState<TipoPqrs>("PETICION");
  const [categoria, setCategoria] = useState<CategoriaPqrs>("ADMINISTRACION");
  const [asunto, setAsunto] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [unidad, setUnidad] = useState("");
  const [canal, setCanal] = useState<CanalPqrs>("PRESENCIAL");
  const [solicitante, setSolicitante] = useState("");
  const [contacto, setContacto] = useState("");
  const [adjuntos, setAdjuntos] = useState<AdjuntoNuevo[]>([]);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    setTipo("PETICION"); setCategoria("ADMINISTRACION"); setAsunto(""); setDescripcion(""); setUnidad("");
    setCanal("PRESENCIAL"); setSolicitante(""); setContacto(""); setAdjuntos([]);
  }, [abierto]);
  useEffect(() => {
    if (residente && !unidad && opciones.length === 1) setUnidad(opciones[0]!.id);
  }, [residente, unidad, opciones]);

  const valido = asunto.trim().length >= 5 && descripcion.trim().length >= 10 && (residente || solicitante.trim().length >= 2);

  async function radicar() {
    setEnviando(true);
    try {
      const p = await api<PqrsDetalle>(`${basePortal(tenant.tenant_id)}/pqrs`, {
        method: "POST",
        json: {
          tipo, categoria, asunto: asunto.trim(), descripcion: descripcion.trim(), unidad_id: unidad || null, adjuntos,
          ...(residente ? {} : { canal, solicitante_nombre: solicitante.trim(), solicitante_contacto: contacto.trim() || null }),
        },
      });
      toast.success(`PQRS radicada con el número ${p.radicado}`);
      void refrescar(tenant.tenant_id);
      onCambio(false);
      onRadicada(p);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{residente ? "Nueva PQRS" : "Radicar PQRS a nombre de un residente"}</DialogTitle>
          <DialogDescription>La administración debe responder en 15 días hábiles. Recibirá un aviso por correo con la respuesta.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-5" role="radiogroup" aria-label="Tipo">
            {(Object.keys(TIPO_PQRS) as TipoPqrs[]).map((t) => (
              <button key={t} type="button" role="radio" aria-checked={tipo === t} title={TIPO_PQRS[t].ayuda} onClick={() => setTipo(t)} className={cn("rounded-md border px-2 py-1.5 text-sm", tipo === t ? "border-primary bg-accent font-medium" : "hover:bg-accent/50")}>
                {TIPO_PQRS[t].label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">{TIPO_PQRS[tipo].ayuda}.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo label="Tema">
              <select value={categoria} onChange={(e) => setCategoria(e.target.value as CategoriaPqrs)} className={campoClase()}>
                {(Object.keys(CATEGORIA_PQRS) as CategoriaPqrs[]).map((c) => (
                  <option key={c} value={c}>
                    {CATEGORIA_PQRS[c]}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo label="Unidad (opcional)">
              <select value={unidad} onChange={(e) => setUnidad(e.target.value)} className={campoClase()}>
                <option value="">Ninguna en particular</option>
                {opciones.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.etiqueta}
                  </option>
                ))}
              </select>
            </Campo>
            {!residente && (
              <>
                <Campo label="A nombre de">
                  <Input value={solicitante} onChange={(e) => setSolicitante(e.target.value)} placeholder="Nombre de quien la presenta" />
                </Campo>
                <Campo label="Cómo llegó">
                  <select value={canal} onChange={(e) => setCanal(e.target.value as CanalPqrs)} className={campoClase()}>
                    {(["PRESENCIAL", "CORREO", "TELEFONO"] as CanalPqrs[]).map((c) => (
                      <option key={c} value={c}>
                        {CANAL_PQRS[c]}
                      </option>
                    ))}
                  </select>
                </Campo>
                <Campo label="Correo o teléfono del solicitante" ayuda="Si deja un correo, recibirá allí la respuesta" className="sm:col-span-2">
                  <Input value={contacto} onChange={(e) => setContacto(e.target.value)} />
                </Campo>
              </>
            )}
          </div>
          <Campo label="Asunto">
            <Input value={asunto} onChange={(e) => setAsunto(e.target.value)} placeholder="Resumen en una línea" maxLength={200} />
          </Campo>
          <Campo label="Descripción" ayuda="Cuente qué pasa, desde cuándo y dónde. Mínimo 10 caracteres.">
            <textarea value={descripcion} onChange={(e) => setDescripcion(e.target.value)} rows={4} className={textareaClase()} />
          </Campo>
          <AdjuntosInput tenantId={tenant.tenant_id} valor={adjuntos} onCambio={setAdjuntos} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            <X className="size-4" /> Cancelar
          </Button>
          <Button disabled={!valido || enviando} onClick={radicar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Radicar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
