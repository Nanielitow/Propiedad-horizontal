"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { campoClase, mensajeError } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, fetcher } from "@/lib/api";
import {
  type Actividad,
  type ActivosPagina,
  baseActivos,
  type BaseCalculo,
  type Contratista,
  PERIODICIDAD,
  type Periodicidad,
  type PersonaAsignable,
  type Plan,
  puedeActivos,
} from "@/lib/activos";
import { fechaCorta, hoyBogota } from "@/lib/recaudos";
import { ROLE_LABEL } from "@/lib/labels";
import type { Role } from "@/lib/types";

import { Campo, textareaClase } from "./comunes";

interface PropsDialogo {
  tenantId: string;
  abierto: boolean;
  onCambio: (v: boolean) => void;
}

export function PlanFormDialog({
  tenantId,
  rol,
  abierto,
  onCambio,
  activoId,
  onGuardado,
}: PropsDialogo & { rol: Role; activoId?: string; onGuardado: (p: Plan) => void }) {
  const b = baseActivos(tenantId);
  const { data: activos } = useSWR<ActivosPagina>(abierto && !activoId ? `${b}?page_size=100` : null, fetcher);
  const { data: contratistas } = useSWR<Contratista[]>(abierto ? `${b}/contratistas` : null, fetcher);
  const [activo, setActivo] = useState(activoId ?? "");
  const [nombre, setNombre] = useState("");
  const [periodicidad, setPeriodicidad] = useState<Periodicidad>("MENSUAL");
  const [horas, setHoras] = useState("");
  const [baseCalculo, setBaseCalculo] = useState<BaseCalculo>("CALENDARIO_FIJO");
  const [inicio, setInicio] = useState(hoyBogota());
  const [contratista, setContratista] = useState("");
  const [costo, setCosto] = useState("");
  const [checklist, setChecklist] = useState("");
  const [aprobar, setAprobar] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const aprueba = puedeActivos(rol, "aprobarPlan");

  useEffect(() => {
    if (abierto) setActivo(activoId ?? "");
  }, [abierto, activoId]);

  const porHoras = periodicidad === "POR_HORAS_USO";
  const valido = activo && nombre.trim().length >= 3 && inicio && (!porHoras || Number(horas) > 0);

  async function guardar() {
    setEnviando(true);
    try {
      let plan = await api<Plan>(`${b}/planes`, {
        method: "POST",
        json: {
          activo_id: activo,
          nombre: nombre.trim(),
          periodicidad,
          intervalo_horas: porHoras ? Number(horas) : null,
          base_calculo: porHoras ? "CALENDARIO_FIJO" : baseCalculo,
          fecha_inicio: inicio,
          contratista_id: contratista || null,
          costo_estimado: costo || null,
          actividades_checklist: checklist.split("\n").map((s) => s.trim()).filter(Boolean),
        },
      });
      if (aprueba && aprobar) {
        plan = await api<Plan>(`${b}/planes/${plan.id}/aprobar`, { method: "POST" });
        toast.success("Plan aprobado: se programaron los próximos 12 meses");
      } else {
        toast.success(aprueba ? "Plan guardado sin aprobar" : "Plan propuesto: queda pendiente de aprobación de la administración");
      }
      setNombre("");
      setChecklist("");
      setCosto("");
      onGuardado(plan);
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Nuevo plan de mantenimiento</DialogTitle>
          <DialogDescription>
            La regla de cada cuánto se hace. Al aprobarlo se crean las fechas de los próximos 12 meses en el calendario.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          {!activoId && (
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
          <Campo label="Nombre del mantenimiento" className="sm:col-span-2">
            <Input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Mantenimiento preventivo mensual" />
          </Campo>
          <Campo label="Periodicidad">
            <select value={periodicidad} onChange={(e) => setPeriodicidad(e.target.value as Periodicidad)} className={campoClase()}>
              {(Object.keys(PERIODICIDAD) as Periodicidad[]).map((p) => (
                <option key={p} value={p}>
                  {PERIODICIDAD[p]}
                </option>
              ))}
            </select>
          </Campo>
          {porHoras ? (
            <Campo label="Cada cuántas horas de uso" ayuda="La fecha se estima con las lecturas del horómetro">
              <Input type="number" min={1} value={horas} onChange={(e) => setHoras(e.target.value)} placeholder="500" />
            </Campo>
          ) : (
            <Campo label="Cómo se cuenta" ayuda={baseCalculo === "CALENDARIO_FIJO" ? "Fechas fijas aunque se ejecute tarde" : "La siguiente fecha cuenta desde la ejecución real"}>
              <select value={baseCalculo} onChange={(e) => setBaseCalculo(e.target.value as BaseCalculo)} className={campoClase()}>
                <option value="CALENDARIO_FIJO">Calendario fijo</option>
                <option value="DESDE_ULTIMA_EJECUCION">Desde la última ejecución</option>
              </select>
            </Campo>
          )}
          <Campo label="Primera fecha">
            <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} className={campoClase()} />
          </Campo>
          <Campo label="Costo estimado por vez" ayuda="Alimenta la proyección del presupuesto">
            <Input type="number" min={0} value={costo} onChange={(e) => setCosto(e.target.value)} />
          </Campo>
          <Campo label="Lo ejecuta" className="sm:col-span-2">
            <select value={contratista} onChange={(e) => setContratista(e.target.value)} className={campoClase()}>
              <option value="">Personal interno</option>
              {contratistas?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.razon_social}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Lista de chequeo" ayuda="Una actividad por línea; el técnico la marca al registrar" className="sm:col-span-2">
            <textarea value={checklist} onChange={(e) => setChecklist(e.target.value)} className={textareaClase()} placeholder={"Revisión de frenos\nLubricación de guías"} />
          </Campo>
        </div>
        {aprueba && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={aprobar} onChange={(e) => setAprobar(e.target.checked)} className="size-4" />
            Aprobar y programar de una vez
          </label>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!valido || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            {aprueba ? "Guardar plan" : "Proponer plan"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ReprogramarDialog({
  tenantId,
  abierto,
  onCambio,
  actividad,
  onGuardado,
}: PropsDialogo & { actividad: Actividad | null; onGuardado: () => void }) {
  const [fecha, setFecha] = useState("");
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const hoy = hoyBogota();

  useEffect(() => {
    if (abierto) {
      setFecha("");
      setMotivo("");
    }
  }, [abierto]);

  if (!actividad) return null;
  const valido = fecha && fecha >= hoy && fecha !== actividad.fecha_programada && motivo.trim().length >= 10;

  async function guardar() {
    if (!actividad) return;
    setEnviando(true);
    try {
      await api(`${baseActivos(tenantId)}/actividades/${actividad.id}/reprogramar`, {
        method: "POST",
        json: { nueva_fecha: fecha, motivo: motivo.trim() },
      });
      toast.success("Actividad reprogramada");
      onGuardado();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Reprogramar</DialogTitle>
          <DialogDescription>
            {actividad.activo_codigo} {actividad.activo.nombre} · «{actividad.plan.nombre}», programada para el{" "}
            {fechaCorta(actividad.fecha_programada)}. El cambio queda en el historial con su motivo.
          </DialogDescription>
        </DialogHeader>
        <Campo label="Nueva fecha">
          <input type="date" min={hoy} value={fecha} onChange={(e) => setFecha(e.target.value)} className={campoClase()} />
        </Campo>
        <Campo label="Motivo" ayuda="Mínimo 10 caracteres">
          <textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} className={textareaClase()} placeholder="El contratista pidió el cambio" />
        </Campo>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!valido || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Reprogramar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function AsignarDialog({
  tenantId,
  abierto,
  onCambio,
  actividad,
  onGuardado,
}: PropsDialogo & { actividad: Actividad | null; onGuardado: () => void }) {
  const { data: personal } = useSWR<PersonaAsignable[]>(abierto ? `${baseActivos(tenantId)}/personal` : null, fetcher);
  const [persona, setPersona] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (abierto) setPersona(actividad?.asignado_a?.id ?? "");
  }, [abierto, actividad]);

  if (!actividad) return null;

  async function guardar() {
    if (!actividad) return;
    setEnviando(true);
    try {
      await api(`${baseActivos(tenantId)}/actividades/${actividad.id}/asignar`, {
        method: "POST",
        json: { asignado_a_id: persona || null },
      });
      toast.success(persona ? "Actividad asignada" : "Asignación quitada");
      onGuardado();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Asignar responsable</DialogTitle>
          <DialogDescription>
            {actividad.activo.nombre} · {fechaCorta(actividad.fecha_programada)}. La persona la verá en su lista de trabajo y recibirá los avisos.
          </DialogDescription>
        </DialogHeader>
        <select value={persona} onChange={(e) => setPersona(e.target.value)} className={campoClase()} aria-label="Responsable">
          <option value="">Sin asignar</option>
          {personal?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nombre.replace(/\s*\(.*\)/, "")} · {ROLE_LABEL[p.rol]}
            </option>
          ))}
        </select>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
