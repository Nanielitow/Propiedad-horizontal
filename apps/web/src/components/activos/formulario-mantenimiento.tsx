"use client";

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, mensajeError } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api, fetcher } from "@/lib/api";
import {
  type Actividad,
  type ActivosPagina,
  baseActivos,
  type Contratista,
  ESTADO_ACTIVO,
  type EstadoActivo,
  type MantenimientoDetalle,
  type Novedad,
  type Plan,
  PRIORIDAD_RECOMENDACION,
  type PrioridadRecomendacion,
  TIPO_MANTENIMIENTO,
  type TipoMantenimiento,
} from "@/lib/activos";
import { fechaCorta, hoyBogota } from "@/lib/recaudos";

import { Campo, FotosPendientes, subirEvidencia, textareaClase } from "./comunes";

type Resultado = "HECHO" | "NO_APLICA" | "PENDIENTE";
interface RecForm {
  descripcion: string;
  prioridad: PrioridadRecomendacion;
  costo_estimado: string;
  fecha_limite: string;
}

const vacio = (v: string) => (v.trim() === "" ? null : v.trim());

/**
 * Registro de un mantenimiento ejecutado. Desde una actividad del plan (preventivo, con su
 * lista de chequeo), desde una novedad (correctivo) o suelto. Es inmutable: un error se
 * corrige anulando. Las fotos se suben después de guardar el registro.
 */
export function MantenimientoSheet({
  abierto,
  onCambio,
  activoId,
  actividad,
  novedad,
  onGuardado,
}: {
  abierto: boolean;
  onCambio: (v: boolean) => void;
  activoId?: string;
  actividad?: Actividad | null;
  novedad?: Novedad | null;
  onGuardado: (m: MantenimientoDetalle) => void;
}) {
  const { tenant, user } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const fijo = actividad?.activo.id ?? novedad?.activo.id ?? activoId;
  const { data: activos } = useSWR<ActivosPagina>(abierto && !fijo ? `${b}?page_size=100` : null, fetcher);
  const { data: contratistas } = useSWR<Contratista[]>(abierto ? `${b}/contratistas` : null, fetcher);
  const { data: plan } = useSWR<Plan>(abierto && actividad ? `${b}/planes/${actividad.plan.id}` : null, fetcher);

  const [activo, setActivo] = useState("");
  const [tipo, setTipo] = useState<TipoMantenimiento>("PREVENTIVO");
  const [fecha, setFecha] = useState(hoyBogota());
  const [tecnico, setTecnico] = useState("");
  const [contratista, setContratista] = useState("");
  const [horas, setHoras] = useState("");
  const [diagnostico, setDiagnostico] = useState("");
  const [realizado, setRealizado] = useState("");
  const [repuestos, setRepuestos] = useState("");
  const [hallazgos, setHallazgos] = useState("");
  const [checklist, setChecklist] = useState<{ actividad: string; resultado: Resultado }[]>([]);
  const [estado, setEstado] = useState<EstadoActivo>("OPERATIVO");
  const [manoObra, setManoObra] = useState("");
  const [costoRepuestos, setCostoRepuestos] = useState("");
  const [proximo, setProximo] = useState("");
  const [recs, setRecs] = useState<RecForm[]>([]);
  const [antes, setAntes] = useState<File[]>([]);
  const [despues, setDespues] = useState<File[]>([]);
  const [enviando, setEnviando] = useState<string | null>(null);

  // Al abrir: valores por defecto según desde dónde se registra
  useEffect(() => {
    if (!abierto) return;
    setActivo(fijo ?? "");
    setTipo(actividad ? "PREVENTIVO" : novedad ? "CORRECTIVO" : "PREVENTIVO");
    setFecha(hoyBogota());
    setTecnico(tenant.role === "MANTENIMIENTO" ? user.full_name.replace(/\s*\(.*\)/, "") : "");
    setContratista(actividad?.contratista?.id ?? novedad?.contratista_asignado?.id ?? "");
    setDiagnostico(novedad?.diagnostico ?? "");
    setRealizado(actividad ? actividad.plan.nombre : "");
    setHoras("");
    setRepuestos("");
    setHallazgos("");
    setEstado("OPERATIVO");
    setManoObra("");
    setCostoRepuestos("");
    setProximo("");
    setRecs([]);
    setAntes([]);
    setDespues([]);
  }, [abierto, fijo, actividad, novedad, tenant.role, user.full_name]);

  useEffect(() => {
    setChecklist(plan ? plan.actividades_checklist.map((a) => ({ actividad: a, resultado: "HECHO" as Resultado })) : []);
  }, [plan]);

  // Con contratista, el técnico por defecto es su contacto
  useEffect(() => {
    if (!contratista || tecnico) return;
    const c = contratistas?.find((x) => x.id === contratista);
    if (c?.contacto_nombre) setTecnico(`${c.contacto_nombre} (${c.razon_social})`);
  }, [contratista, contratistas, tecnico]);

  const valido = activo && fecha && tecnico.trim().length >= 2 && realizado.trim().length >= 5 && recs.every((r) => r.descripcion.trim().length >= 5);

  async function guardar() {
    setEnviando("Guardando…");
    try {
      const m = await api<MantenimientoDetalle>(`${b}/mantenimientos`, {
        method: "POST",
        json: {
          activo_id: activo,
          tipo,
          fecha_ejecucion: fecha,
          nombre_tecnico: tecnico.trim(),
          contratista_id: contratista || null,
          tiempo_ejecucion_horas: horas || null,
          diagnostico_inicial: vacio(diagnostico),
          actividades_realizadas: realizado.trim(),
          repuestos_utilizados: vacio(repuestos),
          novedades_encontradas: vacio(hallazgos),
          checklist,
          estado_post_intervencion: estado,
          costo_mano_obra: manoObra || "0",
          costo_repuestos: costoRepuestos || "0",
          fecha_proximo_recomendado: proximo || null,
          actividad_id: actividad?.id ?? null,
          novedad_id: novedad?.id ?? null,
          recomendaciones: recs.map((r) => ({
            descripcion: r.descripcion.trim(),
            prioridad: r.prioridad,
            costo_estimado: r.costo_estimado || null,
            fecha_limite: r.fecha_limite || null,
          })),
        },
      });
      const fotos = [...antes.map((f) => ["ANTES", f] as const), ...despues.map((f) => ["DESPUES", f] as const)];
      for (const [i, [momento, f]] of fotos.entries()) {
        setEnviando(`Subiendo fotos ${i + 1} de ${fotos.length}…`);
        try {
          await subirEvidencia(tenant.tenant_id, "MANTENIMIENTO", m.id, momento, f);
        } catch (e) {
          toast.error(`No se pudo subir ${f.name}: ${mensajeError(e)}`);
        }
      }
      toast.success(`Mantenimiento ${m.codigo} registrado`);
      onGuardado(m);
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(null);
    }
  }

  const origen = actividad
    ? `Cumple la actividad «${actividad.plan.nombre}» del ${fechaCorta(actividad.fecha_programada)}.`
    : novedad
      ? `Resuelve la novedad ${novedad.codigo}: ${novedad.descripcion}`
      : "Intervención no programada.";

  return (
    <Sheet open={abierto} onOpenChange={onCambio}>
      <SheetContent className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Registrar mantenimiento</SheetTitle>
          <SheetDescription>{origen} El registro no se edita después: un error se corrige anulándolo.</SheetDescription>
        </SheetHeader>

        <div className="grid gap-3 px-4 sm:grid-cols-2">
          {!fijo && (
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
          <Campo label="Tipo">
            <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoMantenimiento)} disabled={!!actividad} className={campoClase()}>
              {(Object.keys(TIPO_MANTENIMIENTO) as TipoMantenimiento[]).map((t) => (
                <option key={t} value={t}>
                  {TIPO_MANTENIMIENTO[t].label}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Fecha de ejecución">
            <input type="date" max={hoyBogota()} value={fecha} onChange={(e) => setFecha(e.target.value)} className={campoClase()} />
          </Campo>
          <Campo label="Lo hizo">
            <select value={contratista} onChange={(e) => setContratista(e.target.value)} className={campoClase()}>
              <option value="">Personal interno</option>
              {contratistas?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.razon_social}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Técnico">
            <Input value={tecnico} onChange={(e) => setTecnico(e.target.value)} placeholder="Nombre de quien ejecutó" />
          </Campo>

          {checklist.length > 0 && (
            <fieldset className="space-y-1.5 sm:col-span-2">
              <legend className="mb-1 text-sm font-medium">Lista de chequeo</legend>
              {checklist.map((c, i) => (
                <div key={c.actividad} className="flex items-center justify-between gap-2 rounded-md border px-3 py-1.5 text-sm">
                  <span className="min-w-0 flex-1">{c.actividad}</span>
                  <select
                    aria-label={`Resultado: ${c.actividad}`}
                    value={c.resultado}
                    onChange={(e) => setChecklist(checklist.map((x, j) => (j === i ? { ...x, resultado: e.target.value as Resultado } : x)))}
                    className="h-8 rounded-md border bg-card px-2 text-sm"
                  >
                    <option value="HECHO">Hecho</option>
                    <option value="NO_APLICA">No aplica</option>
                    <option value="PENDIENTE">Pendiente</option>
                  </select>
                </div>
              ))}
            </fieldset>
          )}

          {tipo !== "PREVENTIVO" && (
            <Campo label="Diagnóstico inicial" className="sm:col-span-2">
              <textarea value={diagnostico} onChange={(e) => setDiagnostico(e.target.value)} className={textareaClase()} />
            </Campo>
          )}
          <Campo label="Trabajo realizado" className="sm:col-span-2">
            <textarea value={realizado} onChange={(e) => setRealizado(e.target.value)} className={textareaClase()} placeholder="Qué se hizo, en detalle" />
          </Campo>
          <Campo label="Repuestos utilizados">
            <Input value={repuestos} onChange={(e) => setRepuestos(e.target.value)} />
          </Campo>
          <Campo label="Tiempo (horas)">
            <Input type="number" inputMode="decimal" step="0.5" min={0} value={horas} onChange={(e) => setHoras(e.target.value)} />
          </Campo>
          <Campo label="Hallazgos" ayuda="Lo que encontró y conviene vigilar" className="sm:col-span-2">
            <textarea value={hallazgos} onChange={(e) => setHallazgos(e.target.value)} className={textareaClase()} />
          </Campo>
          <Campo label="Estado en que queda el equipo">
            <select value={estado} onChange={(e) => setEstado(e.target.value as EstadoActivo)} className={campoClase()}>
              {(Object.keys(ESTADO_ACTIVO) as EstadoActivo[])
                .filter((e) => e !== "DADO_DE_BAJA")
                .map((e) => (
                  <option key={e} value={e}>
                    {ESTADO_ACTIVO[e].label}
                  </option>
                ))}
            </select>
          </Campo>
          <Campo label="Próxima intervención recomendada">
            <input type="date" min={fecha} value={proximo} onChange={(e) => setProximo(e.target.value)} className={campoClase()} />
          </Campo>
          <Campo label="Mano de obra ($)">
            <Input type="number" inputMode="numeric" min={0} value={manoObra} onChange={(e) => setManoObra(e.target.value)} />
          </Campo>
          <Campo label="Repuestos ($)">
            <Input type="number" inputMode="numeric" min={0} value={costoRepuestos} onChange={(e) => setCostoRepuestos(e.target.value)} />
          </Campo>

          <div className="space-y-2 sm:col-span-2">
            <p className="text-sm font-medium">Recomendaciones</p>
            <p className="text-xs text-muted-foreground">Cada una queda como tarea con responsable y seguimiento; las que tienen costo entran al presupuesto.</p>
            {recs.map((r, i) => (
              <div key={i} className="space-y-2 rounded-md border p-2">
                <div className="flex gap-2">
                  <Input
                    value={r.descripcion}
                    onChange={(e) => setRecs(recs.map((x, j) => (j === i ? { ...x, descripcion: e.target.value } : x)))}
                    placeholder="Cambiar rodamientos en 6 meses"
                    aria-label="Recomendación"
                  />
                  <Button type="button" variant="ghost" size="icon" onClick={() => setRecs(recs.filter((_, j) => j !== i))} aria-label="Quitar recomendación">
                    <Trash2 className="size-4" />
                  </Button>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <select
                    aria-label="Prioridad"
                    value={r.prioridad}
                    onChange={(e) => setRecs(recs.map((x, j) => (j === i ? { ...x, prioridad: e.target.value as PrioridadRecomendacion } : x)))}
                    className={campoClase()}
                  >
                    {(Object.keys(PRIORIDAD_RECOMENDACION) as PrioridadRecomendacion[]).map((p) => (
                      <option key={p} value={p}>
                        Prioridad {PRIORIDAD_RECOMENDACION[p].label.toLowerCase()}
                      </option>
                    ))}
                  </select>
                  <Input
                    type="number"
                    min={0}
                    value={r.costo_estimado}
                    onChange={(e) => setRecs(recs.map((x, j) => (j === i ? { ...x, costo_estimado: e.target.value } : x)))}
                    placeholder="Costo $"
                    aria-label="Costo estimado"
                  />
                  <input
                    type="date"
                    min={fecha}
                    value={r.fecha_limite}
                    onChange={(e) => setRecs(recs.map((x, j) => (j === i ? { ...x, fecha_limite: e.target.value } : x)))}
                    className={campoClase()}
                    aria-label="Fecha límite"
                  />
                </div>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRecs([...recs, { descripcion: "", prioridad: "MEDIA", costo_estimado: "", fecha_limite: "" }])}
            >
              <Plus className="size-4" /> Agregar recomendación
            </Button>
          </div>

          <div className="grid gap-3 sm:col-span-2 sm:grid-cols-2">
            <FotosPendientes etiqueta="Fotos de antes" archivos={antes} onCambio={setAntes} />
            <FotosPendientes etiqueta="Fotos de después" archivos={despues} onCambio={setDespues} />
          </div>
        </div>

        <SheetFooter className="flex-row justify-end gap-2">
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!valido || !!enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            {enviando ?? "Registrar"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
