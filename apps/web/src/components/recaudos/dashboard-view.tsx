"use client";

import { AlertTriangle, ArrowRight, Banknote, CalendarRange, Clock, Landmark, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import {
  type Alerta,
  base,
  type Dashboard,
  ESTADO,
  type EstadoRecaudo,
  ESTADOS_ORDEN,
  fechaHora,
  MEDIO,
  type MedioPago,
  pesos,
  puede,
  SEVERIDAD,
} from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { Etiqueta, Kpi, Seccion, SinAcceso, TONO } from "./comunes";

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

function compacto(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toLocaleString("es-CO", { maximumFractionDigits: 1 })} M`;
  if (v >= 1_000) return `$${Math.round(v / 1_000)} mil`;
  return `$${v}`;
}

/** Recaudo diario del mes: barras de una sola serie (sin leyenda), valor exacto al pasar el mouse. */
function GraficoDiario({ periodo, serie }: { periodo: string; serie: Dashboard["serie_diaria"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [anio, mes] = periodo.split("-").map(Number) as [number, number];
  const dias = new Date(anio, mes, 0).getDate();
  const porDia = new Map(serie.map((d) => [Number(d.dia.slice(8, 10)), Number(d.total)]));
  const valores = Array.from({ length: dias }, (_, i) => porDia.get(i + 1) ?? 0);
  const max = Math.max(...valores, 1);
  // Tres líneas guía en valores redondos
  const paso = Math.pow(10, Math.floor(Math.log10(max)));
  const tope = Math.ceil(max / paso) * paso;
  const guias = [tope, tope * (2 / 3), tope / 3];
  const H = 160;

  return (
    <div>
      <div className="relative flex gap-2">
        <div className="relative w-12 shrink-0 text-right text-[11px] text-muted-foreground" style={{ height: H }}>
          {guias.map((g) => (
            <span key={g} className="absolute right-0 -translate-y-1/2 tabular-nums" style={{ top: H - (g / tope) * H }}>
              {compacto(Math.round(g))}
            </span>
          ))}
        </div>
        <div className="relative flex-1" style={{ height: H }} onMouseLeave={() => setHover(null)}>
          {guias.map((g) => (
            <div key={g} className="absolute inset-x-0 border-t border-border/70" style={{ top: H - (g / tope) * H }} />
          ))}
          <div className="absolute inset-0 flex items-end gap-[2px]">
            {valores.map((v, i) => (
              <div key={i} className="relative flex h-full flex-1 items-end" onMouseEnter={() => setHover(i)}>
                <div
                  className={cn("w-full rounded-t-[4px] bg-primary/80 transition-colors", hover === i && "bg-primary", v === 0 && "bg-transparent")}
                  style={{ height: v ? Math.max(2, (v / tope) * H) : 0 }}
                />
              </div>
            ))}
          </div>
          {hover !== null && (
            <div
              className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full rounded-md border bg-popover px-2.5 py-1.5 text-xs shadow-md"
              style={{ left: `${((hover + 0.5) / dias) * 100}%` }}
            >
              <p className="text-muted-foreground">
                {hover + 1} de {MESES[mes - 1]}
              </p>
              <p className="font-semibold tabular-nums">{pesos(valores[hover] ?? 0)}</p>
            </div>
          )}
        </div>
      </div>
      <div className="ml-14 mt-1.5 flex justify-between text-[11px] text-muted-foreground">
        {[1, 5, 10, 15, 20, 25, dias].map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">Ver como tabla</summary>
        <table className="mt-2 w-full max-w-sm text-xs">
          <tbody className="divide-y">
            {valores.map((v, i) =>
              v ? (
                <tr key={i}>
                  <td className="py-1">
                    {i + 1} de {MESES[mes - 1]}
                  </td>
                  <td className="py-1 text-right tabular-nums">{pesos(v)}</td>
                </tr>
              ) : null,
            )}
          </tbody>
        </table>
      </details>
    </div>
  );
}

/** Barras horizontales de una serie: etiqueta y valor siempre visibles (no depende del color). */
function Barras({ filas, total }: { filas: { clave: string; etiqueta: React.ReactNode; valor: number }[]; total: number }) {
  const max = Math.max(...filas.map((f) => f.valor), 1);
  return (
    <ul className="space-y-3">
      {filas.map((f) => (
        <li key={f.clave}>
          <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
            <span className="min-w-0 truncate">{f.etiqueta}</span>
            <span className="shrink-0 tabular-nums">
              <span className="font-medium">{pesos(f.valor)}</span>
              <span className="ml-1.5 text-xs text-muted-foreground">{total ? Math.round((f.valor / total) * 100) : 0} %</span>
            </span>
          </div>
          <div className="h-2 rounded-full bg-secondary">
            <div className="h-2 rounded-full bg-primary/80" style={{ width: `${(f.valor / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function DashboardView() {
  const { tenant } = useTenant();
  const b = base(tenant.tenant_id);
  const permitido = puede(tenant.role, "resumen");
  const verAlertas = puede(tenant.role, "alertas");
  const hoy = new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" }).slice(0, 7);
  const [periodo, setPeriodo] = useState(hoy);
  const [anio, mes] = periodo.split("-").map(Number) as [number, number];
  const { data: d } = useSWR<Dashboard>(permitido ? `${b}/dashboard?anio=${anio}&mes=${mes}` : null, fetcher, { keepPreviousData: true });
  const { data: alertas } = useSWR<Alerta[]>(verAlertas ? `${b}/alertas` : null, fetcher);

  if (!permitido) return <SinAcceso />;

  const totalMes = Number(d?.total_mes ?? 0);
  const efectivoPendiente = Number(d?.efectivo_en_caja ?? 0) + Number(d?.efectivo_en_administracion ?? 0);
  const ruta = (r: string) => `/${tenant.tenant_slug}/recaudos/${r}`;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Recaudos"
        description="Ingresos extraordinarios: parqueadero de visitantes, zonas sociales, aseo y otros."
        actions={
          <label className="flex items-center gap-2 text-sm">
            <CalendarRange className="size-4 text-muted-foreground" />
            <span className="sr-only">Periodo</span>
            <input
              type="month"
              value={periodo}
              max={hoy}
              onChange={(e) => e.target.value && setPeriodo(e.target.value)}
              className="h-9 rounded-md border bg-card px-2 text-sm"
            />
          </label>
        }
      />

      <div className="space-y-6 p-4 sm:p-6">
        {!d ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-28" />
            ))}
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Kpi
                icono={TrendingUp}
                titulo={`Recaudado en ${MESES[mes - 1]}`}
                valor={pesos(totalMes)}
                detalle={`${d.cantidad_mes} movimientos · sin anulados`}
              />
              <Kpi icono={Landmark} titulo={`Acumulado ${anio}`} valor={pesos(d.total_anio)} detalle={`Enero a ${MESES[mes - 1]}`} />
              <Kpi
                icono={Banknote}
                titulo="Efectivo sin consignar"
                valor={pesos(efectivoPendiente)}
                destacado={efectivoPendiente > 0}
                detalle={`En caja ${pesos(d.efectivo_en_caja)} · en administración ${pesos(d.efectivo_en_administracion)}`}
              />
              <Kpi
                icono={Clock}
                titulo="Transferencias por verificar"
                valor={String(d.transferencias_pendientes.cantidad)}
                detalle={`${pesos(d.transferencias_pendientes.total)} sin validar en el extracto`}
              />
            </div>

            <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <Seccion titulo="Recaudo diario" descripcion={`${MESES[mes - 1]} de ${anio}`}>
                <div className="p-4">
                  {totalMes ? <GraficoDiario periodo={d.periodo} serie={d.serie_diaria} /> : <p className="py-10 text-center text-sm text-muted-foreground">Sin recaudos en este periodo.</p>}
                </div>
              </Seccion>

              <Seccion titulo="Por concepto" descripcion="Incluye los rubros desglosados (p. ej. el aseo de un alquiler).">
                <div className="p-4">
                  <Barras
                    total={totalMes}
                    filas={d.por_concepto.map((c) => ({ clave: c.codigo, etiqueta: c.concepto, valor: Number(c.total) }))}
                  />
                </div>
              </Seccion>
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
              <Seccion titulo="Por medio de pago">
                <div className="p-4">
                  <Barras
                    total={totalMes}
                    filas={(Object.keys(MEDIO) as MedioPago[])
                      .filter((m) => d.por_medio[m])
                      .map((m) => ({ clave: m, etiqueta: MEDIO[m], valor: Number(d.por_medio[m]) }))}
                  />
                </div>
              </Seccion>

              <Seccion titulo="Estado del dinero" descripcion="Recaudos del mes según dónde está el dinero.">
                <ul className="divide-y">
                  {ESTADOS_ORDEN.filter((e): e is EstadoRecaudo => e !== "ANULADO" && Boolean(d.por_estado[e])).map((e) => (
                    <li key={e} className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
                      <Etiqueta tono={ESTADO[e].tono}>{ESTADO[e].label}</Etiqueta>
                      <span className="tabular-nums">{pesos(d.por_estado[e])}</span>
                    </li>
                  ))}
                </ul>
              </Seccion>

              {verAlertas ? (
                <Seccion
                  titulo="Alertas activas"
                  acciones={
                    <Link href={ruta("alertas")} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
                      Ver todas <ArrowRight className="size-3" />
                    </Link>
                  }
                >
                  {!alertas?.length ? (
                    <p className="px-4 py-6 text-center text-sm text-muted-foreground">Sin alertas abiertas.</p>
                  ) : (
                    <ul className="divide-y">
                      {alertas.slice(0, 4).map((a) => (
                        <li key={a.id} className="px-4 py-2.5 text-sm">
                          <div className="flex items-center gap-2">
                            <span className={cn("size-2 shrink-0 rounded-full border", TONO[SEVERIDAD[a.severidad].tono])} />
                            <span className="text-xs text-muted-foreground">{fechaHora(a.created_at)}</span>
                          </div>
                          <p className="mt-0.5 line-clamp-2">{a.mensaje}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Seccion>
              ) : (
                <Seccion titulo="Control">
                  <div className="flex items-start gap-3 p-4 text-sm">
                    <AlertTriangle className="mt-0.5 size-4 text-warning" />
                    <p>
                      Hay <strong>{d.alertas_abiertas}</strong> alertas de auditoría abiertas, en revisión por la administración.
                    </p>
                  </div>
                </Seccion>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
