"use client";

import { AlertTriangle, ArrowRight, CalendarCheck, Clock, Gauge, PiggyBank, Table2, Wrench } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, Kpi, Seccion, SinAcceso } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import {
  baseActivos,
  type Categoria,
  type PanelActivos,
  PRIORIDAD_NOVEDAD,
  type PrioridadNovedad,
  puedeActivos,
  SEMAFORO,
  textoDias,
} from "@/lib/activos";
import { fechaCorta, pesos } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { NovedadDetalleSheet } from "./detalles";

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

function compacto(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toLocaleString("es-CO", { maximumFractionDigits: 1 })} M`;
  if (v >= 1_000) return `$${Math.round(v / 1_000)} mil`;
  return `$${v}`;
}

function porcentaje(parte: number, total: number) {
  return total ? Math.round((parte / total) * 1000) / 10 : null;
}

/** Hero de cumplimiento: el número manda; la barra solo lo acompaña. */
function Cumplimiento({ titulo, c }: { titulo: string; c: PanelActivos["cumplimiento"]["mes"] }) {
  const p = porcentaje(c.ejecutadas, c.programadas);
  const t = porcentaje(c.a_tiempo, c.programadas);
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <CalendarCheck className="size-4" /> {titulo}
      </p>
      <p className="mt-1.5 text-3xl font-semibold tracking-tight tabular-nums">{p === null ? "—" : `${p.toLocaleString("es-CO")} %`}</p>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary" aria-hidden>
        <div className={cn("h-full rounded-full", p !== null && p < 80 ? "bg-warning" : "bg-success")} style={{ width: `${p ?? 0}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {c.ejecutadas} de {c.programadas} con fecha cumplida · {t === null ? "—" : `${t.toLocaleString("es-CO")} %`} a tiempo
      </p>
    </div>
  );
}

/** Costo mensual apilado (preventivo abajo, correctivo arriba), con tabla alternativa. */
function CostoMensual({ serie, mesActual }: { serie: NonNullable<PanelActivos["costos"]>["serie"]; mesActual: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [tabla, setTabla] = useState(false);
  const totales = serie.map((s) => Number(s.preventivo) + Number(s.correctivo));
  const max = Math.max(...totales, 1);
  const paso = Math.pow(10, Math.floor(Math.log10(max)));
  const tope = Math.ceil(max / paso) * paso;
  const guias = [tope, tope / 2];
  const H = 170;
  const activo = hover !== null ? serie[hover] : null;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-4 text-xs text-muted-foreground" role="list" aria-label="Leyenda">
          <span role="listitem" className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-serie-preventivo" /> Preventivo
          </span>
          <span role="listitem" className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-serie-correctivo" /> Correctivo
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setTabla(!tabla)} aria-pressed={tabla}>
          <Table2 className="size-3.5" /> {tabla ? "Ver gráfico" : "Ver tabla"}
        </Button>
      </div>
      {tabla ? (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Mes</th>
                <th className="px-3 py-2 text-right font-medium">Preventivo</th>
                <th className="px-3 py-2 text-right font-medium">Correctivo</th>
                <th className="px-3 py-2 text-right font-medium">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y tabular-nums">
              {serie.map((s, i) => (
                <tr key={s.mes}>
                  <td className="px-3 py-1.5 capitalize">{MESES_LARGOS[s.mes - 1]}</td>
                  <td className="px-3 py-1.5 text-right">{pesos(s.preventivo)}</td>
                  <td className="px-3 py-1.5 text-right">{pesos(s.correctivo)}</td>
                  <td className="px-3 py-1.5 text-right font-medium">{pesos(totales[i])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative flex gap-2">
          <div className="relative w-12 shrink-0 text-right text-[11px] text-muted-foreground" style={{ height: H }}>
            {guias.map((g) => (
              <span key={g} className="absolute right-0 -translate-y-1/2 tabular-nums" style={{ top: H - (g / tope) * H }}>
                {compacto(g)}
              </span>
            ))}
          </div>
          <div className="relative flex-1">
            <div className="absolute inset-x-0 top-0" style={{ height: H }} aria-hidden>
              {guias.map((g) => (
                <div key={g} className="absolute inset-x-0 border-t border-dashed border-border" style={{ top: H - (g / tope) * H }} />
              ))}
              <div className="absolute inset-x-0 bottom-0 border-t border-border" />
            </div>
            <div className="relative flex items-end gap-1.5" style={{ height: H }} onMouseLeave={() => setHover(null)}>
              {serie.map((s, i) => {
                const prev = Number(s.preventivo);
                const corr = Number(s.correctivo);
                const hPrev = (prev / tope) * H;
                const hCorr = (corr / tope) * H;
                return (
                  <button
                    key={s.mes}
                    type="button"
                    className="group relative flex h-full flex-1 flex-col justify-end"
                    onMouseEnter={() => setHover(i)}
                    onFocus={() => setHover(i)}
                    onBlur={() => setHover(null)}
                    aria-label={`${MESES_LARGOS[s.mes - 1]}: preventivo ${pesos(prev)}, correctivo ${pesos(corr)}`}
                  >
                    {corr > 0 && (
                      <span
                        className={cn("mx-auto block w-full max-w-7 rounded-t bg-serie-correctivo transition-opacity", hover !== null && hover !== i && "opacity-40")}
                        style={{ height: Math.max(hCorr, 2), marginBottom: prev > 0 ? 2 : 0 }}
                      />
                    )}
                    {prev > 0 && (
                      <span
                        className={cn("mx-auto block w-full max-w-7 bg-serie-preventivo transition-opacity", corr > 0 ? "" : "rounded-t", hover !== null && hover !== i && "opacity-40")}
                        style={{ height: Math.max(hPrev, 2) }}
                      />
                    )}
                  </button>
                );
              })}
            </div>
            <div className="mt-1 flex gap-1.5">
              {serie.map((s) => (
                <span key={s.mes} className={cn("flex-1 text-center text-[11px] text-muted-foreground", s.mes === mesActual && "font-semibold text-foreground")}>
                  {MESES[s.mes - 1]}
                </span>
              ))}
            </div>
            {activo && hover !== null && (
              <div
                className="pointer-events-none absolute z-10 w-44 rounded-md border bg-popover p-2 text-xs shadow-md"
                style={{ left: `clamp(0px, calc(${((hover + 0.5) / 12) * 100}% - 88px), calc(100% - 176px))`, top: 0 }}
                role="tooltip"
              >
                <p className="mb-1 font-medium capitalize">{MESES_LARGOS[activo.mes - 1]}</p>
                <p className="flex justify-between gap-2">
                  <span className="inline-flex items-center gap-1 text-muted-foreground">
                    <span className="size-2 rounded-sm bg-serie-preventivo" /> Preventivo
                  </span>
                  <span className="tabular-nums">{pesos(activo.preventivo)}</span>
                </p>
                <p className="flex justify-between gap-2">
                  <span className="inline-flex items-center gap-1 text-muted-foreground">
                    <span className="size-2 rounded-sm bg-serie-correctivo" /> Correctivo
                  </span>
                  <span className="tabular-nums">{pesos(activo.correctivo)}</span>
                </p>
                <p className="mt-1 flex justify-between gap-2 border-t pt-1 font-medium">
                  <span>Total</span>
                  <span className="tabular-nums">{pesos(totales[hover])}</span>
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Barras horizontales de una serie: etiqueta y valor siempre visibles. */
function Barras({ filas, formato }: { filas: { clave: string; etiqueta: string; valor: number; detalle?: string }[]; formato: (v: number) => string }) {
  const max = Math.max(...filas.map((f) => f.valor), 1);
  return (
    <ul className="space-y-2.5">
      {filas.map((f) => (
        <li key={f.clave}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 truncate">{f.etiqueta}</span>
            <span className="shrink-0 font-medium tabular-nums">
              {formato(f.valor)}
              {f.detalle && <span className="ml-1 text-xs font-normal text-muted-foreground">{f.detalle}</span>}
            </span>
          </div>
          <div className="h-2 rounded-full bg-secondary">
            <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max((f.valor / max) * 100, f.valor ? 1.5 : 0)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function PanelView() {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const permitido = puedeActivos(tenant.role, "panel");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [ubicacion, setUbicacion] = useState(params.get("ubicacion") ?? "");
  const [nov, setNov] = useState<string | null>(null);

  const hoy = new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" });
  const anio = Number(params.get("anio") ?? hoy.slice(0, 4));
  const mes = Number(params.get("mes") ?? hoy.slice(5, 7));
  const q = new URLSearchParams({ anio: String(anio), mes: String(mes) });
  for (const k of ["categoria_id", "ubicacion"]) if (params.get(k)) q.set(k, params.get(k)!);
  const { data: d, isLoading } = useSWR<PanelActivos>(permitido ? `${b}/dashboard?${q}` : null, fetcher, { keepPreviousData: true });
  const { data: categorias } = useSWR<Categoria[]>(permitido && tenant.role !== "CONSEJO" ? `${b}/categorias` : null, fetcher);

  function setParam(cambios: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    router.replace(`${pathname}?${p}`, { scroll: false });
  }

  if (!permitido) return <SinAcceso />;

  const c = d?.costos;
  const proporcionCorrectiva = c ? porcentaje(Number(c.anio_correctivo), Number(c.anio)) : null;
  const abiertas = d ? Object.values(d.novedades.abiertas_por_prioridad).reduce((s, n) => s + (n ?? 0), 0) : 0;
  const anios = Array.from({ length: 4 }, (_, i) => Number(hoy.slice(0, 4)) - i);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Panel de mantenimiento"
        description={
          tenant.role === "CONSEJO"
            ? "Indicadores consolidados del mantenimiento de la copropiedad."
            : d?.puede_ver_costos
              ? "Cumplimiento, fallas, costos y proyección del presupuesto."
              : "Estado de los equipos, cumplimiento del plan y atención de fallas."
        }
        actions={
          puedeActivos(tenant.role, "reportes") && (
            <Button variant="outline" asChild>
              <Link href={`/${tenant.tenant_slug}/activos/reportes`}>Reportes</Link>
            </Button>
          )
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        {/* Filtros: una sola fila */}
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Mes" value={mes} onChange={(e) => setParam({ mes: e.target.value })} className={cn(campoClase(), "w-36")}>
            {MESES_LARGOS.map((m, i) => (
              <option key={m} value={i + 1}>
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </option>
            ))}
          </select>
          <select aria-label="Año" value={anio} onChange={(e) => setParam({ anio: e.target.value })} className={cn(campoClase(), "w-28")}>
            {anios.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          {categorias && (
            <select aria-label="Categoría" value={params.get("categoria_id") ?? ""} onChange={(e) => setParam({ categoria_id: e.target.value || null })} className={cn(campoClase(), "w-56")}>
              <option value="">Todas las categorías</option>
              {categorias.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.nombre}
                </option>
              ))}
            </select>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setParam({ ubicacion: ubicacion.trim() || null });
            }}
          >
            <Input value={ubicacion} onChange={(e) => setUbicacion(e.target.value)} onBlur={() => setParam({ ubicacion: ubicacion.trim() || null })} placeholder="Ubicación (p. ej. Torre 1)" className="w-52" aria-label="Ubicación" />
          </form>
        </div>

        {isLoading && !d ? (
          <div className="grid gap-3 sm:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-28" />
            ))}
          </div>
        ) : d ? (
          <>
            {/* Estado y semáforo */}
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Kpi titulo="Activos" valor={String(d.activos.total)} icono={Wrench} detalle={`${d.activos.por_estado.OPERATIVO ?? 0} operativos · ${d.activos.por_estado.OPERATIVO_CON_OBSERVACIONES ?? 0} con observaciones`} />
              <Kpi
                titulo="Fuera de servicio"
                valor={String(d.activos.por_estado.FUERA_DE_SERVICIO ?? 0)}
                destacado={(d.activos.por_estado.FUERA_DE_SERVICIO ?? 0) > 0}
                icono={AlertTriangle}
                detalle={d.activos.para_reemplazo ? `${d.activos.para_reemplazo} cerca del fin de su vida útil` : "Ninguno cerca del fin de su vida útil"}
              />
              <Kpi
                titulo="Mantenimientos vencidos"
                valor={String(d.semaforo.ROJO)}
                destacado={d.semaforo.ROJO > 0}
                icono={Clock}
                detalle={`${d.semaforo.AMARILLO} vencen en 15 días · ${d.semaforo.VERDE} al día`}
              />
              <Kpi
                titulo="Novedades abiertas"
                valor={String(abiertas)}
                destacado={(d.novedades.abiertas_por_prioridad.CRITICA ?? 0) > 0 || d.novedades.sin_atender > 0}
                icono={AlertTriangle}
                detalle={`${d.novedades.sin_atender} sin atender · ${d.novedades.abiertas_por_prioridad.CRITICA ?? 0} críticas`}
              />
            </div>

            <div className="grid gap-3 lg:grid-cols-3">
              <Cumplimiento titulo={`Cumplimiento de ${MESES_LARGOS[mes - 1]}`} c={d.cumplimiento.mes} />
              <Cumplimiento titulo={`Cumplimiento de ${anio}`} c={d.cumplimiento.anio} />
              <div className="rounded-lg border bg-card p-4">
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Gauge className="size-4" /> Atención de fallas en {anio}
                </p>
                <p className="mt-1.5 text-3xl font-semibold tracking-tight tabular-nums">
                  {d.novedades.respuesta_media_horas === null ? "—" : `${Number(d.novedades.respuesta_media_horas).toLocaleString("es-CO")} h`}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  Tiempo medio de respuesta · cierre en {d.novedades.cierre_medio_dias === null ? "—" : `${Number(d.novedades.cierre_medio_dias).toLocaleString("es-CO")} días`} ·{" "}
                  {d.novedades.reportadas_anio} reportadas
                </p>
              </div>
            </div>

            {/* Costos (quien los ve) */}
            {c && (
              <div className="grid gap-4 lg:grid-cols-3">
                <Seccion
                  titulo={`Costo de mantenimiento ${anio}`}
                  descripcion={`${pesos(c.anio)} en el año · ${pesos(c.mes)} en ${MESES_LARGOS[mes - 1]}`}
                  className="lg:col-span-2"
                  acciones={
                    proporcionCorrectiva !== null && (
                      <Etiqueta tono={proporcionCorrectiva > 40 ? "warning" : "neutral"} title="Una proporción alta de correctivo es señal de una administración reactiva">
                        {proporcionCorrectiva.toLocaleString("es-CO")} % correctivo
                      </Etiqueta>
                    )
                  }
                >
                  <div className="p-4">
                    <CostoMensual serie={c.serie} mesActual={mes} />
                  </div>
                </Seccion>
                <Seccion titulo="Por categoría" descripcion={`Costo de ${anio}`}>
                  <div className="p-4">
                    {c.por_categoria.length ? (
                      <Barras filas={c.por_categoria.map((x) => ({ clave: x.categoria, etiqueta: x.categoria, valor: Number(x.total) }))} formato={(v) => pesos(v)} />
                    ) : (
                      <p className="text-sm text-muted-foreground">Sin costos registrados.</p>
                    )}
                  </div>
                </Seccion>
              </div>
            )}

            {d.proyeccion && (
              <Seccion titulo={`Proyección del presupuesto ${d.proyeccion.anio}`} descripcion="Para preparar la asamblea: lo que costaría mantener todo al día el próximo año." acciones={<PiggyBank className="size-4 text-muted-foreground" />}>
                <div className="grid gap-px overflow-hidden bg-border sm:grid-cols-4">
                  {[
                    { t: "Plan preventivo", v: d.proyeccion.plan, a: "Ocurrencias del año × costo estimado (sin los planes cubiertos por un contrato)" },
                    { t: "Recomendaciones", v: d.proyeccion.recomendaciones, a: "Pendientes, ponderadas: alta 100 %, media 60 %, baja 30 %" },
                    { t: "Contratos anuales", v: d.proyeccion.contratos, a: "Valor de los contratos vigentes" },
                  ].map((x) => (
                    <div key={x.t} className="bg-card p-4">
                      <p className="text-sm text-muted-foreground">{x.t}</p>
                      <p className="mt-1 text-xl font-semibold tabular-nums">{pesos(x.v)}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{x.a}</p>
                    </div>
                  ))}
                  <div className="bg-accent/50 p-4">
                    <p className="text-sm font-medium">Total proyectado</p>
                    <p className="mt-1 text-2xl font-semibold tabular-nums">{pesos(d.proyeccion.total)}</p>
                    {puedeActivos(tenant.role, "reportes") && (
                      <Link href={`/${tenant.tenant_slug}/activos/reportes?tipo=costos`} className="mt-1 inline-flex items-center gap-1 text-xs text-primary hover:underline">
                        Ver el detalle <ArrowRight className="size-3" />
                      </Link>
                    )}
                  </div>
                </div>
              </Seccion>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              <Seccion titulo="Activos por categoría">
                <div className="p-4">
                  <Barras
                    filas={d.activos.por_categoria.map((x) => ({
                      clave: x.categoria,
                      etiqueta: x.categoria,
                      valor: x.total,
                      detalle: x.fuera_de_servicio ? `· ${x.fuera_de_servicio} fuera de servicio` : undefined,
                    }))}
                    formato={(v) => String(v)}
                  />
                </div>
              </Seccion>
              <Seccion titulo="Novedades abiertas por prioridad" descripcion={`${d.recomendaciones.alta_pendientes} recomendaciones de prioridad alta pendientes · ${d.recomendaciones.vencidas} vencidas`}>
                <ul className="divide-y">
                  {(["CRITICA", "ALTA", "MEDIA", "BAJA"] as PrioridadNovedad[]).map((p) => (
                    <li key={p} className="flex items-center justify-between px-4 py-2.5 text-sm">
                      <Etiqueta tono={PRIORIDAD_NOVEDAD[p].tono}>{PRIORIDAD_NOVEDAD[p].label}</Etiqueta>
                      <span className="font-semibold tabular-nums">{d.novedades.abiertas_por_prioridad[p] ?? 0}</span>
                    </li>
                  ))}
                </ul>
              </Seccion>
            </div>

            {/* Listas accionables (el Consejo no las recibe) */}
            {d.detalle && (
              <div className="grid gap-4 lg:grid-cols-2">
                <Seccion titulo="Mantenimientos vencidos" acciones={<Link href={`/${tenant.tenant_slug}/activos/calendario`} className="text-xs text-primary hover:underline">Calendario</Link>}>
                  {d.detalle.vencidas.length === 0 ? (
                    <p className="px-4 py-5 text-sm text-muted-foreground">Nada vencido.</p>
                  ) : (
                    <ul className="divide-y">
                      {d.detalle.vencidas.map((x) => (
                        <li key={x.id}>
                          <Link href={`/${tenant.tenant_slug}/activos/${x.activo.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-accent/40">
                            <span className={cn("size-2.5 rounded-full", SEMAFORO.ROJO.punto)} />
                            <span className="min-w-0 flex-1 text-sm">
                              <span className="font-medium">{x.activo.nombre}</span> · {x.plan.nombre}
                            </span>
                            <span className="text-xs text-destructive">{textoDias(x.dias_restantes)}</span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </Seccion>
                <Seccion titulo="Novedades urgentes" descripcion="Críticas y altas abiertas">
                  {d.detalle.novedades_urgentes.length === 0 ? (
                    <p className="px-4 py-5 text-sm text-muted-foreground">Ninguna.</p>
                  ) : (
                    <ul className="divide-y">
                      {d.detalle.novedades_urgentes.map((n) => (
                        <li key={n.id}>
                          <button type="button" onClick={() => setNov(n.id)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-accent/40">
                            <Etiqueta tono={PRIORIDAD_NOVEDAD[n.prioridad].tono}>{PRIORIDAD_NOVEDAD[n.prioridad].label}</Etiqueta>
                            <span className="min-w-0 flex-1 truncate text-sm">
                              <span className="font-medium">{n.activo.nombre}</span> · {n.descripcion}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </Seccion>
                {d.detalle.para_reemplazo.length > 0 && (
                  <Seccion titulo="Cerca del fin de su vida útil" descripcion="Conviene presupuestar su reemplazo">
                    <ul className="divide-y">
                      {d.detalle.para_reemplazo.map((x) => (
                        <li key={x.id}>
                          <Link href={`/${tenant.tenant_slug}/activos/${x.id}`} className="flex justify-between px-4 py-2.5 text-sm hover:bg-accent/40">
                            <span>
                              {x.codigo} {x.nombre}
                            </span>
                            <span className="tabular-nums text-muted-foreground">{Number(x.vida_util_consumida).toLocaleString("es-CO")} %</span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </Seccion>
                )}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Datos al {fechaCorta(d.hoy)}. El semáforo y el cumplimiento se calculan con la fecha de hoy.
            </p>
          </>
        ) : null}
      </div>
      <NovedadDetalleSheet id={nov} onCerrar={() => setNov(null)} />
    </div>
  );
}
