"use client";

import { Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, mensajeError, Seccion, SinAcceso } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, fetcher } from "@/lib/api";
import { baseCartera, type ConfigCartera, METODO, type MetodoCuota, puedeCartera } from "@/lib/cartera";
import { pesos } from "@/lib/recaudos";
import { TIPO_UNIDAD, type TipoUnidad } from "@/lib/unidades";
import { cn } from "@/lib/utils";

import { useRefrescarCartera } from "./comunes";

const num = (v: string) => v.replace(/[^\d.,]/g, "").replace(",", ".");

export function ConfiguracionCarteraView() {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const permitido = puedeCartera(tenant.role, "configurar");
  const { data: cfg, mutate, isLoading } = useSWR<ConfigCartera | null>(permitido ? `${b}/config` : null, fetcher);
  const refrescar = useRefrescarCartera();
  const [metodo, setMetodo] = useState<MetodoCuota>("COEFICIENTE");
  const [presupuesto, setPresupuesto] = useState("");
  const [tarifas, setTarifas] = useState<Partial<Record<TipoUnidad, string>>>({});
  const [redondeo, setRedondeo] = useState(100);
  const [vence, setVence] = useState("10");
  const [descuento, setDescuento] = useState("0");
  const [limite, setLimite] = useState("5");
  const [intereses, setIntereses] = useState(true);
  const [tasa, setTasa] = useState("1.5");
  const [nota, setNota] = useState("");
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    if (!cfg) return;
    setMetodo(cfg.metodo);
    setPresupuesto(cfg.presupuesto_mensual ? String(Number(cfg.presupuesto_mensual)) : "");
    setTarifas(Object.fromEntries(Object.entries(cfg.tarifas_por_tipo).map(([k, v]) => [k, String(Number(v))])));
    setRedondeo(cfg.redondeo);
    setVence(String(cfg.dia_vencimiento));
    setDescuento(String(Number(cfg.descuento_pct)));
    setLimite(String(cfg.dia_limite_descuento ?? 5));
    setIntereses(cfg.cobrar_intereses);
    setTasa(String(Number(cfg.tasa_mora_mensual)));
    setNota(cfg.nota_cuenta_cobro ?? "");
  }, [cfg]);

  if (!permitido) return <SinAcceso />;

  async function guardar() {
    setGuardando(true);
    try {
      const r = await api<ConfigCartera>(`${b}/config`, {
        method: "PUT",
        json: {
          metodo,
          presupuesto_mensual: metodo === "COEFICIENTE" ? num(presupuesto) || null : null,
          tarifas_por_tipo: Object.fromEntries(Object.entries(tarifas).filter(([, v]) => v && Number(num(v)) > 0).map(([k, v]) => [k, num(v!)])),
          redondeo,
          dia_vencimiento: Number(vence),
          descuento_pct: num(descuento) || "0",
          dia_limite_descuento: Number(num(descuento)) > 0 ? Number(limite) : null,
          cobrar_intereses: intereses,
          tasa_mora_mensual: num(tasa) || "0",
          nota_cuenta_cobro: nota.trim() || null,
          motivo: motivo.trim() || null,
        },
      });
      void mutate(r, { revalidate: false });
      void refrescar(tenant.tenant_id);
      setMotivo("");
      toast.success("Configuración guardada. Aplica desde el próximo mes que se facture.");
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setGuardando(false);
    }
  }

  const dias = Array.from({ length: 28 }, (_, i) => i + 1);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Configuración de la cartera" description="Cómo se calcula la cuota, cuándo vence, el descuento y los intereses de mora." />
      <div className="mx-auto w-full max-w-3xl space-y-4 p-4 sm:p-6">
        {isLoading ? null : (
          <>
            <Seccion titulo="Cuota de administración">
              <div className="space-y-4 p-4">
                <div className="grid gap-2 sm:grid-cols-2">
                  {(Object.keys(METODO) as MetodoCuota[]).map((m) => (
                    <button key={m} type="button" onClick={() => setMetodo(m)} className={cn("rounded-lg border p-3 text-left transition-colors", metodo === m ? "border-primary ring-2 ring-primary/20" : "hover:bg-accent/40")} aria-pressed={metodo === m}>
                      <span className="block text-sm font-medium">{METODO[m].label}</span>
                      <span className="block text-xs text-muted-foreground">{METODO[m].ayuda}</span>
                    </button>
                  ))}
                </div>
                {metodo === "COEFICIENTE" ? (
                  <Campo label="Presupuesto mensual de gastos" ayuda={presupuesto ? `Una unidad con coeficiente 1 % pagaría ${pesos(Number(num(presupuesto)) / 100)}` : "El aprobado por la asamblea, dividido entre 12"}>
                    <Input value={presupuesto} onChange={(e) => setPresupuesto(e.target.value)} inputMode="numeric" placeholder="42000000" />
                  </Campo>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-3">
                    {(Object.keys(TIPO_UNIDAD) as TipoUnidad[]).map((t) => (
                      <Campo key={t} label={TIPO_UNIDAD[t]}>
                        <Input value={tarifas[t] ?? ""} onChange={(e) => setTarifas((x) => ({ ...x, [t]: e.target.value }))} inputMode="numeric" placeholder="0 = no se cobra" />
                      </Campo>
                    ))}
                  </div>
                )}
                <div className="grid gap-3 sm:grid-cols-2">
                  <Campo label="Redondear cuotas a">
                    <select value={redondeo} onChange={(e) => setRedondeo(Number(e.target.value))} className={campoClase()}>
                      {[1, 10, 50, 100, 500, 1000].map((r) => (
                        <option key={r} value={r}>
                          {r === 1 ? "Al peso" : `Múltiplos de ${pesos(r)}`}
                        </option>
                      ))}
                    </select>
                  </Campo>
                  <Campo label="Día de vencimiento">
                    <select value={vence} onChange={(e) => setVence(e.target.value)} className={campoClase()}>
                      {dias.map((d) => (
                        <option key={d} value={d}>
                          Día {d} de cada mes
                        </option>
                      ))}
                    </select>
                  </Campo>
                </div>
              </div>
            </Seccion>

            <Seccion titulo="Descuento por pronto pago" descripcion="Solo aplica si la unidad queda al día y paga antes de la fecha límite.">
              <div className="grid gap-3 p-4 sm:grid-cols-2">
                <Campo label="Descuento (%)" ayuda="0 = sin descuento">
                  <Input value={descuento} onChange={(e) => setDescuento(e.target.value)} inputMode="decimal" />
                </Campo>
                {Number(num(descuento)) > 0 && (
                  <Campo label="Hasta el día">
                    <select value={limite} onChange={(e) => setLimite(e.target.value)} className={campoClase()}>
                      {dias.filter((d) => d <= Number(vence)).map((d) => (
                        <option key={d} value={d}>
                          Día {d}
                        </option>
                      ))}
                    </select>
                  </Campo>
                )}
              </div>
            </Seccion>

            <Seccion titulo="Intereses de mora" descripcion="Se cobran al facturar cada mes, sobre el capital vencido. Nunca intereses sobre intereses.">
              <div className="space-y-3 p-4">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={intereses} onChange={(e) => setIntereses(e.target.checked)} className="size-4" />
                  Cobrar intereses de mora
                </label>
                {intereses && (
                  <Campo label="Tasa mensual (%)" ayuda="Tope legal (Ley 675, art. 30): 1,5 veces el interés bancario corriente certificado por la Superintendencia Financiera. Revísela cada mes.">
                    <Input value={tasa} onChange={(e) => setTasa(e.target.value)} inputMode="decimal" className="w-40" />
                  </Campo>
                )}
              </div>
            </Seccion>

            <Seccion titulo="Nota en la cuenta de cobro">
              <div className="p-4">
                <textarea value={nota} onChange={(e) => setNota(e.target.value)} rows={2} className="min-h-16 w-full rounded-md border bg-card px-3 py-2 text-sm" placeholder="Pague por transferencia a la cuenta de ahorros … del banco …" />
              </div>
            </Seccion>

            <div className="flex flex-wrap items-end justify-end gap-3">
              {cfg && (
                <Campo label="Motivo del cambio (opcional)" className="min-w-64 flex-1">
                  <Input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Nuevo presupuesto aprobado en asamblea 2027" />
                </Campo>
              )}
              <Button onClick={guardar} disabled={guardando}>
                {guardando ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                Guardar configuración
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
