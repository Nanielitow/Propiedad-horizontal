"use client";

import { ArrowLeft, Building2, Lock, Loader2, MailCheck, Send, Undo2, UserCheck, Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo, textareaClase } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, mensajeError, MotivoDialog, Seccion, SinAcceso } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, fetcher } from "@/lib/api";
import type { ActivosPagina, PersonaAsignable } from "@/lib/activos";
import { basePortal, CANAL_PQRS, CATEGORIA_PQRS, type PqrsDetalle, PRIORIDAD_PQRS, type PrioridadPqrs, TIPO_PQRS } from "@/lib/portal";
import { fechaCorta } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { type AdjuntoNuevo, AdjuntosInput, Estrellas, EstadoPqrsBadge, ListaAdjuntos, Plazo, PrioridadBadge, useRefrescarPortal } from "./comunes";

const fechaHora = (iso: string) => new Date(iso).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Bogota" });

export function PqrsDetalleView({ pqrsId }: { pqrsId: string }) {
  const { tenant } = useTenant();
  const clave = `${basePortal(tenant.tenant_id)}/pqrs/${pqrsId}`;
  const { data: p, error, mutate } = useSWR<PqrsDetalle>(clave, fetcher);
  const refrescar = useRefrescarPortal();
  const [texto, setTexto] = useState("");
  const [adjuntos, setAdjuntos] = useState<AdjuntoNuevo[]>([]);
  const [enviando, setEnviando] = useState<string | null>(null);
  const [calificacion, setCalificacion] = useState(0);
  const [comentario, setComentario] = useState("");
  const [desistir, setDesistir] = useState(false);
  const [novedad, setNovedad] = useState(false);
  const residente = tenant.role === "RESIDENTE";
  const volver = `/${tenant.tenant_slug}/${residente ? "mi-portal" : "portal"}/pqrs`;

  if (error instanceof ApiError && error.status === 404) return <SinAcceso texto="La PQRS no existe o no tiene acceso a ella" />;
  if (!p) return <div className="space-y-3 p-6"><Skeleton className="h-10 w-80" /><Skeleton className="h-64" /></div>;

  const abierta = p.estado === "RADICADA" || p.estado === "EN_TRAMITE";
  const actualizado = (nueva: PqrsDetalle) => {
    void mutate(nueva, { revalidate: false });
    void refrescar(tenant.tenant_id);
  };

  async function enviar(accion: "mensaje" | "nota" | "responder" | "reabrir") {
    setEnviando(accion);
    try {
      const ruta = { mensaje: "mensajes", nota: "mensajes", responder: "responder", reabrir: "reabrir" }[accion];
      const body = accion === "reabrir" ? { texto: texto.trim() } : { texto: texto.trim(), adjuntos, ...(accion === "nota" ? { interno: true } : {}) };
      actualizado(await api<PqrsDetalle>(`${clave}/${ruta}`, { method: "POST", json: body }));
      setTexto("");
      setAdjuntos([]);
      toast.success({ mensaje: "Mensaje enviado", nota: "Nota interna guardada", responder: "Respuesta enviada: el solicitante recibirá un correo", reabrir: "PQRS reabierta" }[accion]);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(null);
    }
  }

  async function gestionar(json: Record<string, unknown>, ok: string) {
    try {
      actualizado(await api<PqrsDetalle>(clave, { method: "PATCH", json }));
      toast.success(ok);
    } catch (e) {
      toast.error(mensajeError(e));
    }
  }

  async function calificar() {
    setEnviando("calificar");
    try {
      actualizado(await api<PqrsDetalle>(`${clave}/calificar`, { method: "POST", json: { calificacion, comentario: comentario.trim() || null } }));
      toast.success("Gracias por calificar la atención");
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(null);
    }
  }

  const puedeEscribir = abierta && (p.es_mia || p.puede_gestionar);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title={p.asunto}
        description={`${p.radicado} · ${TIPO_PQRS[p.tipo].label} · ${CATEGORIA_PQRS[p.categoria]}`}
        actions={
          <Button variant="ghost" size="icon" asChild aria-label="Volver">
            <Link href={volver}>
              <ArrowLeft className="size-4" />
            </Link>
          </Button>
        }
      />
      <div className="grid gap-4 p-4 sm:p-6 lg:grid-cols-[1fr_300px]">
        <div className="min-w-0 space-y-4">
          {/* Solicitud original */}
          <div className="rounded-lg border bg-card p-4">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <EstadoPqrsBadge estado={p.estado} />
              {p.prioridad !== "MEDIA" && <PrioridadBadge prioridad={p.prioridad} />}
              <span>
                {p.solicitante_nombre}
                {p.unidad && ` · ${p.unidad}`} · {fechaHora(p.created_at)}
                {p.canal !== "PORTAL" && ` · recibida por ${CANAL_PQRS[p.canal].toLowerCase()}`}
              </span>
            </div>
            <p className="mt-3 text-sm whitespace-pre-wrap">{p.descripcion}</p>
            <div className="mt-3">
              <ListaAdjuntos adjuntos={p.adjuntos} />
            </div>
          </div>

          {/* Conversación */}
          <ol className="space-y-3">
            {p.hilo.map((m) => (
              <li
                key={m.id}
                className={cn(
                  "rounded-lg border p-3 text-sm",
                  m.interno ? "border-dashed border-warning/40 bg-warning-soft/30" : m.es_respuesta ? "border-success/30 bg-success-soft/30" : m.autor_rol === "RESIDENTE" ? "bg-card" : "bg-accent/30",
                  m.es_mio && !m.interno && "sm:ml-10",
                )}
              >
                <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{m.es_mio ? "Usted" : m.autor}</span>
                  {m.interno && (
                    <span className="inline-flex items-center gap-1 text-warning">
                      <Lock className="size-3" /> Nota interna (el residente no la ve)
                    </span>
                  )}
                  {m.es_respuesta && (
                    <span className="inline-flex items-center gap-1 text-success">
                      <MailCheck className="size-3.5" /> Respuesta oficial
                    </span>
                  )}
                  <span>· {fechaHora(m.created_at)}</span>
                </div>
                <p className="whitespace-pre-wrap">{m.texto}</p>
                {m.adjuntos.length > 0 && (
                  <div className="mt-2">
                    <ListaAdjuntos adjuntos={m.adjuntos} />
                  </div>
                )}
              </li>
            ))}
          </ol>

          {/* Calificar o reabrir (residente, con respuesta) */}
          {p.es_mia && p.estado === "RESPONDIDA" && (
            <Seccion titulo="¿Quedó resuelta su solicitud?" descripcion="Califique la atención para cerrarla, o explique qué falta para que la administración siga trabajando en ella.">
              <div className="space-y-3 p-4">
                <Estrellas valor={calificacion} onCambio={setCalificacion} />
                <Input value={comentario} onChange={(e) => setComentario(e.target.value)} placeholder="Comentario (opcional)" />
                <div className="flex flex-wrap gap-2">
                  <Button disabled={!calificacion || enviando !== null} onClick={calificar}>
                    {enviando === "calificar" && <Loader2 className="size-4 animate-spin" />}
                    Calificar y cerrar
                  </Button>
                </div>
                <div className="border-t pt-3">
                  <Campo label="No quedó resuelta: explique qué falta">
                    <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={2} className={textareaClase()} />
                  </Campo>
                  <Button variant="outline" className="mt-2" disabled={texto.trim().length < 5 || enviando !== null} onClick={() => enviar("reabrir")}>
                    <Undo2 className="size-4" /> Reabrir la PQRS
                  </Button>
                </div>
              </div>
            </Seccion>
          )}
          {p.calificacion && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-card p-3 text-sm">
              <span className="text-muted-foreground">Calificación del solicitante:</span>
              <Estrellas valor={p.calificacion} tam="size-4" />
              {p.comentario_calificacion && <span className="italic">«{p.comentario_calificacion}»</span>}
            </div>
          )}

          {/* Escribir */}
          {puedeEscribir && (
            <div className="space-y-2 rounded-lg border bg-card p-3">
              <textarea
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                rows={3}
                className={textareaClase()}
                placeholder={p.puede_gestionar ? "Escriba la respuesta para el solicitante, un mensaje o una nota interna…" : "Agregue información o pregunte por su solicitud…"}
                aria-label="Mensaje"
              />
              <AdjuntosInput tenantId={tenant.tenant_id} valor={adjuntos} onCambio={setAdjuntos} />
              <div className="flex flex-wrap justify-end gap-2">
                {p.puede_gestionar && (
                  <Button variant="outline" disabled={!texto.trim() || enviando !== null} onClick={() => enviar("nota")}>
                    {enviando === "nota" ? <Loader2 className="size-4 animate-spin" /> : <Lock className="size-4" />} Nota interna
                  </Button>
                )}
                <Button variant={p.puede_gestionar ? "outline" : "default"} disabled={!texto.trim() || enviando !== null} onClick={() => enviar("mensaje")}>
                  {enviando === "mensaje" ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />} Enviar mensaje
                </Button>
                {p.puede_gestionar && (
                  <Button disabled={texto.trim().length < 10 || enviando !== null} onClick={() => enviar("responder")} title="Marca la PQRS como respondida y avisa por correo">
                    {enviando === "responder" ? <Loader2 className="size-4 animate-spin" /> : <MailCheck className="size-4" />} Responder oficialmente
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Panel lateral */}
        <aside className="space-y-3">
          <div className="space-y-2 rounded-lg border bg-card p-4 text-sm">
            <p className="flex justify-between gap-2">
              <span className="text-muted-foreground">Radicado</span>
              <span className="font-mono">{p.radicado}</span>
            </p>
            <p className="flex justify-between gap-2">
              <span className="text-muted-foreground">Fecha límite</span>
              <span className="text-right">
                {fechaCorta(p.fecha_limite)}
                <br />
                <Plazo p={p} />
              </span>
            </p>
            {p.respondida_at && (
              <p className="flex justify-between gap-2">
                <span className="text-muted-foreground">Respondida</span>
                <span>{fechaCorta(p.respondida_at)}</span>
              </p>
            )}
            {p.puede_gestionar && p.solicitante_contacto && (
              <p className="flex justify-between gap-2">
                <span className="text-muted-foreground">Contacto</span>
                <span className="truncate">{p.solicitante_contacto}</span>
              </p>
            )}
            {p.novedad_codigo && (
              <p className="flex justify-between gap-2">
                <span className="text-muted-foreground">Mantenimiento</span>
                <Link href={`/${tenant.tenant_slug}/activos/novedades`} className="font-medium text-primary hover:underline">
                  {p.novedad_codigo}
                </Link>
              </p>
            )}
          </div>

          {p.puede_gestionar && <PanelGestion p={p} onGestionar={gestionar} onNovedad={() => setNovedad(true)} />}

          {abierta && (p.es_mia || tenant.role === "ADMIN" || tenant.role === "AUXILIAR") && (
            <Button variant="ghost" size="sm" className="w-full text-muted-foreground" onClick={() => setDesistir(true)}>
              {p.es_mia ? "Ya no necesito esta solicitud" : "Registrar desistimiento"}
            </Button>
          )}
        </aside>
      </div>

      <MotivoDialog
        abierto={desistir}
        onCambio={setDesistir}
        titulo="Desistir de la PQRS"
        descripcion="La solicitud se cierra sin respuesta. Queda en el historial."
        boton="Desistir"
        minimo={5}
        onConfirmar={async (motivo) => {
          actualizado(await api<PqrsDetalle>(`${clave}/desistir`, { method: "POST", json: { texto: motivo } }));
          toast.success("PQRS cerrada por desistimiento");
        }}
      />
      {p.puede_gestionar && <NovedadDialog abierto={novedad} onCambio={setNovedad} pqrs={p} onCreada={actualizado} />}
    </div>
  );
}

function PanelGestion({ p, onGestionar, onNovedad }: { p: PqrsDetalle; onGestionar: (json: Record<string, unknown>, ok: string) => Promise<void>; onNovedad: () => void }) {
  const { tenant } = useTenant();
  const admin = tenant.role === "ADMIN" || tenant.role === "AUXILIAR";
  const { data: personal } = useSWR<PersonaAsignable[]>(admin ? `/tenants/${tenant.tenant_id}/activos/personal` : null, fetcher);
  const abierta = p.estado === "RADICADA" || p.estado === "EN_TRAMITE";
  return (
    <div className="space-y-3 rounded-lg border bg-card p-4 text-sm">
      <p className="font-semibold">Gestión</p>
      {admin && (
        <Campo label="Responsable">
          <select
            value={personal?.find((x) => x.nombre === p.asignado_a)?.id ?? ""}
            onChange={(e) => void onGestionar(e.target.value ? { asignado_a_id: e.target.value } : { quitar_asignacion: true }, e.target.value ? "PQRS asignada" : "Asignación quitada")}
            className={campoClase()}
          >
            <option value="">Sin asignar</option>
            {personal?.map((x) => (
              <option key={x.id} value={x.id}>
                {x.nombre}
              </option>
            ))}
          </select>
        </Campo>
      )}
      <Campo label="Prioridad">
        <select value={p.prioridad} onChange={(e) => void onGestionar({ prioridad: e.target.value }, "Prioridad actualizada")} className={campoClase()} disabled={!abierta}>
          {(Object.keys(PRIORIDAD_PQRS) as PrioridadPqrs[]).map((k) => (
            <option key={k} value={k}>
              {PRIORIDAD_PQRS[k].label}
            </option>
          ))}
        </select>
      </Campo>
      {p.estado === "RADICADA" && (
        <Button variant="outline" size="sm" className="w-full" onClick={() => void onGestionar({ estado: "EN_TRAMITE" }, "PQRS en trámite")}>
          <UserCheck className="size-4" /> Pasar a trámite
        </Button>
      )}
      {p.estado === "RESPONDIDA" && admin && (
        <Button variant="outline" size="sm" className="w-full" onClick={() => void onGestionar({ estado: "CERRADA" }, "PQRS cerrada")} title="Si el solicitante no la califica, la administración puede cerrarla">
          Cerrar sin calificación
        </Button>
      )}
      {admin && !p.novedad_id && abierta && (
        <Button variant="outline" size="sm" className="w-full" onClick={onNovedad}>
          <Wrench className="size-4" /> Crear novedad de mantenimiento
        </Button>
      )}
      {p.unidad && (
        <p className="flex items-center gap-1 text-xs text-muted-foreground">
          <Building2 className="size-3.5" /> Unidad {p.unidad}
        </p>
      )}
      {p.asignado_a && !admin && <Etiqueta tono="info">Asignada a usted</Etiqueta>}
    </div>
  );
}

function NovedadDialog({ abierto, onCambio, pqrs, onCreada }: { abierto: boolean; onCambio: (v: boolean) => void; pqrs: PqrsDetalle; onCreada: (p: PqrsDetalle) => void }) {
  const { tenant } = useTenant();
  const [busqueda, setBusqueda] = useState("");
  const [activo, setActivo] = useState("");
  const [prioridad, setPrioridad] = useState("MEDIA");
  const [enviando, setEnviando] = useState(false);
  const { data } = useSWR<ActivosPagina>(abierto ? `/tenants/${tenant.tenant_id}/activos?page_size=50${busqueda.trim() ? `&texto=${encodeURIComponent(busqueda.trim())}` : ""}` : null, fetcher, { keepPreviousData: true });

  async function crear() {
    setEnviando(true);
    try {
      onCreada(await api<PqrsDetalle>(`${basePortal(tenant.tenant_id)}/pqrs/${pqrs.id}/novedad`, { method: "POST", json: { activo_id: activo, prioridad } }));
      toast.success("Novedad de mantenimiento creada y enlazada");
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Crear novedad de mantenimiento</DialogTitle>
          <DialogDescription>La falla queda registrada en la hoja de vida del activo y el equipo de mantenimiento la atiende desde su módulo.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Input value={busqueda} onChange={(e) => setBusqueda(e.target.value)} placeholder="Buscar el activo afectado (cubierta, motobomba, ascensor…)" />
          <ul className="max-h-56 divide-y overflow-y-auto rounded-md border text-sm" role="listbox" aria-label="Activos">
            {data?.items.map((a) => (
              <li key={a.id}>
                <button type="button" role="option" aria-selected={activo === a.id} onClick={() => setActivo(a.id)} className={cn("w-full px-3 py-2 text-left hover:bg-accent", activo === a.id && "bg-accent")}>
                  <span className="font-medium">{a.nombre}</span>
                  <span className="block text-xs text-muted-foreground">
                    {a.codigo_interno} · {a.ubicacion}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <Campo label="Prioridad">
            <select value={prioridad} onChange={(e) => setPrioridad(e.target.value)} className={campoClase()}>
              <option value="BAJA">Baja</option>
              <option value="MEDIA">Media</option>
              <option value="ALTA">Alta</option>
              <option value="CRITICA">Crítica</option>
            </select>
          </Campo>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!activo || enviando} onClick={crear}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Crear novedad
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
