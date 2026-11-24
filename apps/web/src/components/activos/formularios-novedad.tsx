"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, mensajeError } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, fetcher } from "@/lib/api";
import {
  type ActivosPagina,
  baseActivos,
  type Contratista,
  ESTADO_NOVEDAD,
  ESTADO_RECOMENDACION,
  type EstadoNovedad,
  type EstadoRecomendacion,
  type Novedad,
  type PersonaAsignable,
  PRIORIDAD_NOVEDAD,
  PRIORIDAD_RECOMENDACION,
  type PrioridadNovedad,
  type PrioridadRecomendacion,
  puedeActivos,
  type Recomendacion,
  TRANSICIONES,
} from "@/lib/activos";
import { hoyBogota } from "@/lib/recaudos";
import type { ComparisonSummary } from "@/lib/types";

import { Campo, FotosPendientes, subirEvidencia, textareaClase } from "./comunes";

const vacio = (v: string) => (v.trim() === "" ? null : v.trim());

// --- Reportar una novedad ------------------------------------------------------------------

export function NovedadFormDialog({
  abierto,
  onCambio,
  activoId,
  onGuardado,
}: {
  abierto: boolean;
  onCambio: (v: boolean) => void;
  activoId?: string;
  onGuardado: (n: Novedad) => void;
}) {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const { data: activos } = useSWR<ActivosPagina>(abierto && !activoId ? `${b}?page_size=100` : null, fetcher);
  const [activo, setActivo] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [prioridad, setPrioridad] = useState<PrioridadNovedad>("MEDIA");
  const [riesgo, setRiesgo] = useState("");
  const [fuera, setFuera] = useState(false);
  const [fotos, setFotos] = useState<File[]>([]);
  const [enviando, setEnviando] = useState<string | null>(null);
  const esTecnico = tenant.role === "MANTENIMIENTO";

  useEffect(() => {
    if (!abierto) return;
    setActivo(activoId ?? "");
    setDescripcion("");
    setPrioridad("MEDIA");
    setRiesgo("");
    setFuera(false);
    setFotos([]);
  }, [abierto, activoId]);

  async function guardar() {
    setEnviando("Enviando…");
    try {
      const n = await api<Novedad>(`${b}/novedades`, {
        method: "POST",
        json: {
          activo_id: activo,
          descripcion: descripcion.trim(),
          prioridad,
          riesgo_identificado: vacio(riesgo),
          poner_fuera_de_servicio: prioridad === "CRITICA" && fuera,
        },
      });
      for (const [i, f] of fotos.entries()) {
        setEnviando(`Subiendo fotos ${i + 1} de ${fotos.length}…`);
        try {
          await subirEvidencia(tenant.tenant_id, "NOVEDAD", n.id, "EVIDENCIA", f);
        } catch (e) {
          toast.error(`No se pudo subir ${f.name}: ${mensajeError(e)}`);
        }
      }
      toast.success(prioridad === "CRITICA" ? `${n.codigo} reportada: la administración recibió un correo` : `Novedad ${n.codigo} reportada`);
      onGuardado(n);
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(null);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Reportar una falla</DialogTitle>
          <DialogDescription>La administración la recibe en su bandeja de novedades. Las críticas llegan además por correo.</DialogDescription>
        </DialogHeader>
        {!activoId && (
          <Campo label="Activo">
            <select value={activo} onChange={(e) => setActivo(e.target.value)} className={campoClase()}>
              <option value="">Seleccione…</option>
              {activos?.items.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.codigo_interno} · {a.nombre}
                </option>
              ))}
            </select>
          </Campo>
        )}
        <Campo label="¿Qué pasa?">
          <textarea value={descripcion} onChange={(e) => setDescripcion(e.target.value)} className={textareaClase()} placeholder="Describa la falla como la ve" autoFocus />
        </Campo>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Prioridad</legend>
          <div className="grid grid-cols-4 gap-1.5">
            {(["BAJA", "MEDIA", "ALTA", "CRITICA"] as PrioridadNovedad[]).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPrioridad(p)}
                aria-pressed={prioridad === p}
                className={`h-9 rounded-md border text-sm font-medium transition-colors ${
                  prioridad === p
                    ? p === "CRITICA"
                      ? "border-destructive bg-destructive text-white"
                      : "border-primary bg-primary text-primary-foreground"
                    : "bg-card hover:bg-accent"
                }`}
              >
                {PRIORIDAD_NOVEDAD[p].label}
              </button>
            ))}
          </div>
        </fieldset>
        <Campo label="Riesgo" ayuda="Opcional: qué puede pasar si no se atiende">
          <Input value={riesgo} onChange={(e) => setRiesgo(e.target.value)} placeholder="Personas atrapadas, inundación…" />
        </Campo>
        {prioridad === "CRITICA" && !esTecnico && (
          <label className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
            <input type="checkbox" checked={fuera} onChange={(e) => setFuera(e.target.checked)} className="mt-0.5 size-4" />
            <span>
              <span className="font-medium">Poner el equipo fuera de servicio</span>
              <span className="block text-xs text-muted-foreground">Queda en la auditoría con el código de esta novedad.</span>
            </span>
          </label>
        )}
        {prioridad === "CRITICA" && esTecnico && (
          <p className="flex gap-2 text-xs text-muted-foreground">
            <AlertTriangle className="size-4 shrink-0 text-warning" />
            La administración decidirá si el equipo queda fuera de servicio.
          </p>
        )}
        <FotosPendientes etiqueta="Fotos de la falla" archivos={fotos} onCambio={setFotos} />
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button variant={prioridad === "CRITICA" ? "destructive" : "default"} disabled={!activo || descripcion.trim().length < 5 || !!enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            {enviando ?? "Reportar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Avanzar en el flujo --------------------------------------------------------------------

const VERBO: Record<EstadoNovedad, string> = {
  REPORTADA: "Reportada",
  EN_GESTION: "Atender (en gestión)",
  PENDIENTE_COTIZACION: "Pedir cotización",
  PROGRAMADA: "Programar reparación",
  EN_EJECUCION: "Iniciar reparación",
  CERRADA: "Cerrar",
  DESCARTADA: "Descartar",
};

export function NovedadAvanceDialog({
  abierto,
  onCambio,
  novedad,
  destinoInicial,
  onGuardado,
}: {
  abierto: boolean;
  onCambio: (v: boolean) => void;
  novedad: Novedad | null;
  destinoInicial?: EstadoNovedad;
  onGuardado: (n: Novedad) => void;
}) {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const admin = puedeActivos(tenant.role, "cerrarNovedad");
  const gestiona = tenant.role !== "MANTENIMIENTO";
  const { data: personal } = useSWR<PersonaAsignable[]>(abierto && gestiona ? `${b}/personal` : null, fetcher);
  const { data: contratistas } = useSWR<Contratista[]>(abierto && gestiona ? `${b}/contratistas` : null, fetcher);
  const { data: cotizaciones } = useSWR<ComparisonSummary[]>(abierto && admin ? `/tenants/${tenant.tenant_id}/quote-comparisons` : null, fetcher);

  const opciones = novedad ? TRANSICIONES[novedad.estado].filter((e) => admin || (e !== "CERRADA" && e !== "DESCARTADA")) : [];
  const [destino, setDestino] = useState<EstadoNovedad | "">("");
  const [asignado, setAsignado] = useState("");
  const [contratista, setContratista] = useState("");
  const [cotizacion, setCotizacion] = useState("");
  const [diagnostico, setDiagnostico] = useState("");
  const [solucion, setSolucion] = useState("");
  const [costo, setCosto] = useState("");
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!abierto || !novedad) return;
    setDestino(destinoInicial ?? opciones[0] ?? "");
    setAsignado(novedad.asignado_a?.id ?? "");
    setContratista(novedad.contratista_asignado?.id ?? "");
    setCotizacion(novedad.cotizacion_id ?? "");
    setDiagnostico(novedad.diagnostico ?? "");
    setSolucion(novedad.solucion_implementada ?? "");
    setCosto("");
    setMotivo("");
    // Solo al abrir (o al cambiar de novedad): no reiniciar lo que el usuario está escribiendo
  }, [abierto, novedad?.id]);

  if (!novedad) return null;
  const tieneMto = novedad.mantenimientos.length > 0;
  const valido =
    destino &&
    (destino !== "DESCARTADA" || motivo.trim().length >= 10) &&
    (destino !== "CERRADA" || tieneMto || solucion.trim().length > 0);

  async function guardar() {
    if (!novedad || !destino) return;
    setEnviando(true);
    try {
      const json: Record<string, unknown> = { estado: destino };
      if (gestiona && ["EN_GESTION", "PROGRAMADA", "PENDIENTE_COTIZACION"].includes(destino)) {
        json.asignado_a_id = asignado || null;
        json.contratista_asignado_id = contratista || null;
      }
      if (destino === "PENDIENTE_COTIZACION" && cotizacion) json.cotizacion_id = cotizacion;
      if (diagnostico.trim() && diagnostico.trim() !== (novedad.diagnostico ?? "")) json.diagnostico = diagnostico.trim();
      if (destino === "CERRADA") {
        if (solucion.trim()) json.solucion_implementada = solucion.trim();
        if (costo) json.costo_reparacion = costo;
      }
      if (destino === "DESCARTADA") json.motivo_descarte = motivo.trim();
      const n = await api<Novedad>(`${b}/novedades/${novedad.id}/estado`, { method: "POST", json });
      toast.success(`${n.codigo}: ${ESTADO_NOVEDAD[n.estado].label.toLowerCase()}`);
      onGuardado(n);
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {novedad.codigo} · {ESTADO_NOVEDAD[novedad.estado].label}
          </DialogTitle>
          <DialogDescription>{novedad.descripcion}</DialogDescription>
        </DialogHeader>
        {opciones.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {novedad.estado === "EN_EJECUCION" ? "Solo la administración la cierra." : "No hay pasos disponibles para su rol."}
          </p>
        ) : (
          <>
            <fieldset>
              <legend className="mb-1.5 text-sm font-medium">Siguiente paso</legend>
              <div className="flex flex-wrap gap-1.5">
                {opciones.map((e) => (
                  <button
                    key={e}
                    type="button"
                    onClick={() => setDestino(e)}
                    aria-pressed={destino === e}
                    className={`h-9 rounded-md border px-3 text-sm font-medium transition-colors ${
                      destino === e ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-accent"
                    }`}
                  >
                    {VERBO[e]}
                  </button>
                ))}
              </div>
            </fieldset>

            {gestiona && destino && ["EN_GESTION", "PROGRAMADA", "PENDIENTE_COTIZACION"].includes(destino) && (
              <div className="grid gap-3 sm:grid-cols-2">
                <Campo label="Responsable interno">
                  <select value={asignado} onChange={(e) => setAsignado(e.target.value)} className={campoClase()}>
                    <option value="">Sin asignar</option>
                    {personal?.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.nombre.replace(/\s*\(.*\)/, "")}
                      </option>
                    ))}
                  </select>
                </Campo>
                <Campo label="Contratista">
                  <select value={contratista} onChange={(e) => setContratista(e.target.value)} className={campoClase()}>
                    <option value="">Ninguno</option>
                    {contratistas?.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.razon_social}
                      </option>
                    ))}
                  </select>
                </Campo>
              </div>
            )}
            {destino === "PENDIENTE_COTIZACION" && admin && (
              <Campo label="Comparación de cotizaciones" ayuda="Opcional: vincúlela cuando la cree en Cotizaciones">
                <select value={cotizacion} onChange={(e) => setCotizacion(e.target.value)} className={campoClase()}>
                  <option value="">Sin vincular</option>
                  {cotizaciones?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
                </select>
              </Campo>
            )}
            {destino && destino !== "DESCARTADA" && destino !== "CERRADA" && (
              <Campo label="Diagnóstico">
                <textarea value={diagnostico} onChange={(e) => setDiagnostico(e.target.value)} className={textareaClase()} />
              </Campo>
            )}
            {destino === "CERRADA" && (
              <>
                {tieneMto ? (
                  <p className="rounded-md border bg-success-soft/50 px-3 py-2 text-sm">
                    Resuelta con {novedad.mantenimientos.map((m) => m.nombre).join(", ")}. Puede agregar una nota de la solución.
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">Sin mantenimiento registrado: describa la solución para poder cerrarla.</p>
                )}
                <Campo label="Solución implementada">
                  <textarea value={solucion} onChange={(e) => setSolucion(e.target.value)} className={textareaClase()} />
                </Campo>
                {!tieneMto && (
                  <Campo label="Costo de la reparación ($)">
                    <Input type="number" min={0} value={costo} onChange={(e) => setCosto(e.target.value)} />
                  </Campo>
                )}
              </>
            )}
            {destino === "DESCARTADA" && (
              <Campo label="Motivo del descarte" ayuda="Mínimo 10 caracteres; queda en la auditoría">
                <textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} className={textareaClase()} placeholder="Duplicada de NOV-0003" />
              </Campo>
            )}
          </>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          {opciones.length > 0 && (
            <Button variant={destino === "DESCARTADA" ? "destructive" : "default"} disabled={!valido || enviando} onClick={guardar}>
              {enviando && <Loader2 className="size-4 animate-spin" />}
              {destino ? VERBO[destino] : "Guardar"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Recomendaciones ----------------------------------------------------------------------------

export function RecomendacionDialog({
  abierto,
  onCambio,
  recomendacion,
  activoId,
  onGuardado,
}: {
  abierto: boolean;
  onCambio: (v: boolean) => void;
  recomendacion?: Recomendacion | null;
  activoId?: string;
  onGuardado: () => void;
}) {
  const { tenant, user } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const admin = puedeActivos(tenant.role, "descartarRecomendacion");
  const tecnico = tenant.role === "MANTENIMIENTO";
  const verCostos = tenant.role === "ADMIN" || tenant.role === "CONTABILIDAD";
  const { data: personal } = useSWR<PersonaAsignable[]>(abierto && !tecnico ? `${b}/personal` : null, fetcher);
  const { data: activos } = useSWR<ActivosPagina>(abierto && !recomendacion && !activoId ? `${b}?page_size=100` : null, fetcher);

  const [activo, setActivo] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [estado, setEstado] = useState<EstadoRecomendacion>("PENDIENTE");
  const [prioridad, setPrioridad] = useState<PrioridadRecomendacion>("MEDIA");
  const [responsable, setResponsable] = useState("");
  const [limite, setLimite] = useState("");
  const [costo, setCosto] = useState("");
  const [observaciones, setObservaciones] = useState("");
  const [justificacion, setJustificacion] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    const r = recomendacion;
    setActivo(activoId ?? "");
    setDescripcion("");
    setEstado(r?.estado ?? "PENDIENTE");
    setPrioridad(r?.prioridad ?? "MEDIA");
    setResponsable(r?.responsable?.id ?? "");
    setLimite(r?.fecha_limite ?? "");
    setCosto(r?.costo_estimado ? String(Math.round(Number(r.costo_estimado))) : "");
    setObservaciones(r?.observaciones_administracion ?? "");
    setJustificacion("");
  }, [abierto, recomendacion, activoId]);

  const nueva = !recomendacion;
  const estados: EstadoRecomendacion[] = admin
    ? ["PENDIENTE", "EN_PROCESO", "EJECUTADA", "DESCARTADA_CON_JUSTIFICACION"]
    : ["PENDIENTE", "EN_PROCESO", "EJECUTADA"];
  const valido = nueva
    ? activo && descripcion.trim().length >= 5
    : estado !== "DESCARTADA_CON_JUSTIFICACION" || justificacion.trim().length >= 10;

  async function guardar() {
    setEnviando(true);
    try {
      if (nueva) {
        await api(`${b}/recomendaciones`, {
          method: "POST",
          json: {
            activo_id: activo,
            descripcion: descripcion.trim(),
            prioridad,
            costo_estimado: costo || null,
            fecha_limite: limite || null,
            responsable_id: responsable || null,
          },
        });
        toast.success("Recomendación registrada");
      } else if (recomendacion) {
        const json: Record<string, unknown> = {};
        if (estado !== recomendacion.estado) json.estado = estado;
        if (!tecnico) {
          if (prioridad !== recomendacion.prioridad) json.prioridad = prioridad;
          if ((responsable || null) !== (recomendacion.responsable?.id ?? null)) json.responsable_id = responsable || null;
          if ((limite || null) !== recomendacion.fecha_limite) json.fecha_limite = limite || null;
          if (verCostos && costo && Number(costo) !== Number(recomendacion.costo_estimado ?? -1)) json.costo_estimado = costo;
          if (observaciones.trim() !== (recomendacion.observaciones_administracion ?? "")) json.observaciones_administracion = vacio(observaciones);
        }
        if (estado === "DESCARTADA_CON_JUSTIFICACION") json.justificacion_descarte = justificacion.trim();
        if (!Object.keys(json).length) {
          onCambio(false);
          return;
        }
        await api(`${b}/recomendaciones/${recomendacion.id}`, { method: "PATCH", json });
        toast.success("Recomendación actualizada");
      }
      onGuardado();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  const soloAvance = tecnico && recomendacion?.responsable?.id !== undefined;

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{nueva ? "Nueva recomendación" : `Recomendación · ${recomendacion?.activo_codigo}`}</DialogTitle>
          <DialogDescription>
            {nueva
              ? "Una acción sugerida que hay que hacer seguimiento (por ejemplo, tras una inspección)."
              : recomendacion?.descripcion}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          {nueva && !activoId && (
            <Campo label="Activo" className="sm:col-span-2">
              <select value={activo} onChange={(e) => setActivo(e.target.value)} className={campoClase()}>
                <option value="">Seleccione…</option>
                {activos?.items.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.codigo_interno} · {a.nombre}
                  </option>
                ))}
              </select>
            </Campo>
          )}
          {nueva && (
            <Campo label="Recomendación" className="sm:col-span-2">
              <textarea value={descripcion} onChange={(e) => setDescripcion(e.target.value)} className={textareaClase()} autoFocus />
            </Campo>
          )}
          {!nueva && (
            <Campo label="Estado" className={soloAvance ? "sm:col-span-2" : undefined}>
              <select value={estado} onChange={(e) => setEstado(e.target.value as EstadoRecomendacion)} className={campoClase()}>
                {estados.map((e) => (
                  <option key={e} value={e}>
                    {ESTADO_RECOMENDACION[e].label}
                  </option>
                ))}
              </select>
            </Campo>
          )}
          {!tecnico && (
            <>
              <Campo label="Prioridad">
                <select value={prioridad} onChange={(e) => setPrioridad(e.target.value as PrioridadRecomendacion)} className={campoClase()}>
                  {(Object.keys(PRIORIDAD_RECOMENDACION) as PrioridadRecomendacion[]).map((p) => (
                    <option key={p} value={p}>
                      {PRIORIDAD_RECOMENDACION[p].label}
                    </option>
                  ))}
                </select>
              </Campo>
              <Campo label="Responsable">
                <select value={responsable} onChange={(e) => setResponsable(e.target.value)} className={campoClase()}>
                  <option value="">Sin responsable</option>
                  {personal?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre.replace(/\s*\(.*\)/, "")}
                    </option>
                  ))}
                </select>
              </Campo>
              <Campo label="Fecha límite">
                <input type="date" min={nueva ? hoyBogota() : undefined} value={limite} onChange={(e) => setLimite(e.target.value)} className={campoClase()} />
              </Campo>
              {(verCostos || nueva) && (
                <Campo label="Costo estimado ($)" ayuda="Entra en la proyección del presupuesto">
                  <Input type="number" min={0} value={costo} onChange={(e) => setCosto(e.target.value)} />
                </Campo>
              )}
              {!nueva && (
                <Campo label="Observaciones de la administración" className="sm:col-span-2">
                  <textarea value={observaciones} onChange={(e) => setObservaciones(e.target.value)} className={textareaClase()} />
                </Campo>
              )}
            </>
          )}
          {estado === "DESCARTADA_CON_JUSTIFICACION" && recomendacion?.estado !== "DESCARTADA_CON_JUSTIFICACION" && (
            <Campo label="Justificación del descarte" ayuda="Mínimo 10 caracteres" className="sm:col-span-2">
              <textarea value={justificacion} onChange={(e) => setJustificacion(e.target.value)} className={textareaClase()} placeholder="El consejo la aplazó por presupuesto" />
            </Campo>
          )}
        </div>
        {tecnico && recomendacion && recomendacion.responsable?.nombre && (
          <p className="text-xs text-muted-foreground">A cargo de {recomendacion.responsable.nombre.replace(/\s*\(.*\)/, "") === user.full_name.replace(/\s*\(.*\)/, "") ? "usted" : recomendacion.responsable.nombre}.</p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!valido || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
