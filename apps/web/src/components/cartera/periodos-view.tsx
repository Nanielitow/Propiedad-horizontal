"use client";

import { AlertTriangle, CalendarPlus, ChevronDown, Loader2, Plus, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, mensajeError, MotivoDialog, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import { baseCartera, type Cargo, type ConceptoCartera, METODO, type Periodo, puedeCartera } from "@/lib/cartera";
import { fechaCorta, hoyBogota, pesos } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { FacturarDialog, useRefrescarCartera } from "./comunes";

export function PeriodosView() {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const permitido = puedeCartera(tenant.role, "ver");
  const { data } = useSWR<Periodo[]>(permitido ? `${b}/periodos` : null, fetcher);
  const refrescar = useRefrescarCartera();
  const [facturar, setFacturar] = useState(false);
  const [extra, setExtra] = useState(false);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [anular, setAnular] = useState<Periodo | null>(null);
  const admin = puedeCartera(tenant.role, "facturar");

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Facturación"
        description="Periodos emitidos con sus cuotas e intereses, y cobros extraordinarios."
        actions={
          admin && (
            <>
              <Button variant="outline" onClick={() => setExtra(true)} className="hidden sm:inline-flex">
                <Plus className="size-4" /> Cuota extraordinaria o multa
              </Button>
              <Button onClick={() => setFacturar(true)}>
                <CalendarPlus className="size-4" /> Facturar mes
              </Button>
            </>
          )
        }
      />
      <div className="space-y-3 p-4 sm:p-6">
        {!data ? (
          <Skeleton className="h-64" />
        ) : !data.length ? (
          <div className="rounded-lg border bg-card">
            <Vacio icono={CalendarPlus} titulo="Aún no se ha facturado ningún mes" texto="Use «Facturar mes»: verá una vista previa con la cuota de cada unidad antes de emitir." />
          </div>
        ) : (
          data.map((p) => {
            const total = Number(p.total_cuotas) + Number(p.total_intereses);
            const pct = total ? Math.round((Number(p.recaudado) / total) * 100) : 0;
            return (
              <div key={p.id} className={cn("rounded-lg border bg-card", p.estado === "ANULADO" && "opacity-70")}>
                <button type="button" onClick={() => setAbierto(abierto === p.id ? null : p.id)} className="flex w-full flex-wrap items-center gap-x-5 gap-y-1 px-4 py-3 text-left" aria-expanded={abierto === p.id}>
                  <span className="w-40 font-medium">{p.nombre}</span>
                  {p.estado === "ANULADO" ? (
                    <Etiqueta tono="danger">Anulado</Etiqueta>
                  ) : (
                    <>
                      <span className="text-sm text-muted-foreground">
                        {p.unidades_facturadas} unidades · vence {fechaCorta(p.fecha_vencimiento)}
                      </span>
                      <span className="text-sm tabular-nums">
                        {pesos(p.total_cuotas)}
                        {Number(p.total_intereses) > 0 && <span className="text-muted-foreground"> + {pesos(p.total_intereses)} intereses</span>}
                      </span>
                      <span className="ml-auto text-sm text-muted-foreground tabular-nums">Recaudado {pct} %</span>
                    </>
                  )}
                  <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", abierto === p.id && "rotate-180")} />
                </button>
                {abierto === p.id && (
                  <DetallePeriodo
                    p={p}
                    puedeAnular={puedeCartera(tenant.role, "anular") && p.estado === "EMITIDO"}
                    onAnular={() => setAnular(p)}
                  />
                )}
              </div>
            );
          })
        )}
      </div>
      <FacturarDialog tenantId={tenant.tenant_id} abierto={facturar} onCambio={setFacturar} onEmitido={() => refrescar(tenant.tenant_id)} />
      <ExtraordinariaDialog abierto={extra} onCambio={setExtra} onCreado={() => refrescar(tenant.tenant_id)} />
      <MotivoDialog
        abierto={!!anular}
        onCambio={(v) => !v && setAnular(null)}
        titulo={`Anular la facturación de ${anular?.nombre.toLowerCase() ?? ""}`}
        descripcion="Solo es posible si nadie ha pagado sobre estas cuotas. Las cuotas quedan anuladas (no se borran) y el mes se puede volver a facturar."
        boton="Anular periodo"
        onConfirmar={async (motivo) => {
          if (!anular) return;
          await api(`${b}/periodos/${anular.id}/anular`, { method: "POST", json: { motivo } });
          toast.success("Periodo anulado");
          void refrescar(tenant.tenant_id);
        }}
      />
    </div>
  );
}

function DetallePeriodo({ p, puedeAnular, onAnular }: { p: Periodo; puedeAnular: boolean; onAnular: () => void }) {
  const { tenant } = useTenant();
  const { data: cargos } = useSWR<Cargo[]>(`${baseCartera(tenant.tenant_id)}/periodos/${p.id}/cargos`, fetcher);
  return (
    <div className="space-y-3 border-t px-4 py-3">
      <p className="text-sm text-muted-foreground">
        {METODO[p.metodo].label}
        {p.presupuesto_mensual && ` · presupuesto ${pesos(p.presupuesto_mensual)}`}
        {Number(p.descuento_pct) > 0 && p.fecha_limite_descuento && ` · ${Number(p.descuento_pct)} % de descuento hasta ${fechaCorta(p.fecha_limite_descuento)}`}
        {p.tasa_mora_mensual && ` · mora ${Number(p.tasa_mora_mensual)} % mensual`}
        {` · emitido el ${fechaCorta(p.fecha_emision)}`}
      </p>
      {p.motivo_anulacion && <p className="text-sm text-destructive">Anulado: {p.motivo_anulacion}</p>}
      {p.advertencias.map((a) => (
        <p key={a} className="flex gap-2 text-sm text-warning">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {a}
        </p>
      ))}
      {!cargos ? (
        <Skeleton className="h-24" />
      ) : (
        <div className="max-h-80 overflow-y-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-muted text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-1.5 text-left font-medium">Unidad</th>
                <th className="px-3 py-1.5 text-left font-medium">Concepto</th>
                <th className="px-3 py-1.5 text-right font-medium">Valor</th>
                <th className="px-3 py-1.5 text-right font-medium">Saldo</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {cargos.map((c) => (
                <tr key={c.id} className={cn(c.estado === "ANULADO" && "text-muted-foreground line-through")}>
                  <td className="px-3 py-1.5 font-medium">{c.unidad}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{c.tipo_concepto === "INTERES" ? "Intereses" : "Cuota"}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{pesos(c.valor)}</td>
                  <td className={cn("px-3 py-1.5 text-right tabular-nums", Number(c.saldo) > 0 ? "font-medium" : "text-success")}>{Number(c.saldo) > 0 ? pesos(c.saldo) : "Pagado"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {puedeAnular && (
        <Button variant="ghost" size="sm" className="text-destructive" onClick={onAnular}>
          <Undo2 className="size-4" /> Anular este periodo
        </Button>
      )}
    </div>
  );
}

function ExtraordinariaDialog({ abierto, onCambio, onCreado }: { abierto: boolean; onCambio: (v: boolean) => void; onCreado: () => void }) {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const { data: conceptos } = useSWR<ConceptoCartera[]>(abierto ? `${b}/conceptos` : null, fetcher);
  const manuales = conceptos?.filter((c) => c.activo && c.tipo !== "ORDINARIA" && c.tipo !== "INTERES") ?? [];
  const [concepto, setConcepto] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [modo, setModo] = useState<"TOTAL_POR_COEFICIENTE" | "VALOR_POR_UNIDAD">("TOTAL_POR_COEFICIENTE");
  const [valor, setValor] = useState("");
  const [cuotas, setCuotas] = useState("1");
  const [vence, setVence] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    setDescripcion("");
    setValor("");
    setCuotas("1");
    setVence("");
    setModo("TOTAL_POR_COEFICIENTE");
  }, [abierto]);
  useEffect(() => {
    if (!concepto && manuales[0]) setConcepto(manuales[0].id);
  }, [concepto, manuales]);

  async function crear() {
    setEnviando(true);
    try {
      const r = await api<{ cargos: number; unidades: number; total: string }>(`${b}/cargos`, {
        method: "POST",
        json: { concepto_id: concepto, descripcion: descripcion.trim(), todas: true, modo, valor: valor.replace(/[^\d.]/g, ""), numero_cuotas: Number(cuotas), primer_vencimiento: vence },
      });
      toast.success(`${r.cargos} cargos creados para ${r.unidades} unidades (${pesos(r.total)})`);
      onCreado();
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
          <DialogTitle>Cuota extraordinaria para todas las unidades</DialogTitle>
          <DialogDescription>Por ejemplo, la aprobada en asamblea para una obra. Se puede repartir por coeficiente y diferir en cuotas mensuales.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo label="Concepto">
            <select value={concepto} onChange={(e) => setConcepto(e.target.value)} className={campoClase()}>
              {manuales.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Cómo se cobra">
            <select value={modo} onChange={(e) => setModo(e.target.value as typeof modo)} className={campoClase()}>
              <option value="TOTAL_POR_COEFICIENTE">Total repartido por coeficiente</option>
              <option value="VALOR_POR_UNIDAD">Mismo valor por unidad</option>
            </select>
          </Campo>
          <Campo label="Descripción" className="sm:col-span-2">
            <Input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} placeholder="Impermeabilización de cubiertas (acta 015)" />
          </Campo>
          <Campo label={modo === "TOTAL_POR_COEFICIENTE" ? "Valor total aprobado" : "Valor por unidad"}>
            <Input value={valor} onChange={(e) => setValor(e.target.value)} inputMode="numeric" />
          </Campo>
          <Campo label="Número de cuotas" ayuda="Una por mes">
            <Input value={cuotas} onChange={(e) => setCuotas(e.target.value)} type="number" min={1} max={24} />
          </Campo>
          <Campo label="Primer vencimiento" className="sm:col-span-2">
            <input type="date" value={vence} min={hoyBogota()} onChange={(e) => setVence(e.target.value)} className={campoClase()} />
          </Campo>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!concepto || descripcion.trim().length < 3 || Number(valor.replace(/[^\d.]/g, "")) <= 0 || !vence || enviando} onClick={crear}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Crear cobro
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
