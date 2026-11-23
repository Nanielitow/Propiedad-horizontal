"use client";

import { CalendarCheck, Download, FileSpreadsheet, FileText, Loader2, Play } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import {
  base,
  celdaReporte,
  type Corte,
  fechaHora,
  hoyBogota,
  pesos,
  puede,
  REPORTES,
  type ReporteJson,
  type TipoReporte,
} from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { campoClase, mensajeError, Seccion, SinAcceso, Vacio } from "./comunes";

const FILAS_VISTA = 200;
type Preset = "mes" | "anterior" | "anio" | "personalizado";

function rango(preset: Preset): { desde: string; hasta: string } {
  const hoy = hoyBogota();
  const [y, m] = hoy.split("-").map(Number) as [number, number];
  const fin = (anio: number, mes: number) => new Date(Date.UTC(anio, mes, 0)).toISOString().slice(0, 10);
  if (preset === "anterior") {
    const [ay, am] = m === 1 ? [y - 1, 12] : [y, m - 1];
    return { desde: `${ay}-${String(am).padStart(2, "0")}-01`, hasta: fin(ay, am) };
  }
  if (preset === "anio") return { desde: `${y}-01-01`, hasta: hoy };
  return { desde: `${y}-${String(m).padStart(2, "0")}-01`, hasta: fin(y, m) };
}

function TablaReporte({ t }: { t: ReporteJson["tablas"][number] }) {
  const numerica = (i: number) => ["dinero", "entero", "porcentaje"].includes(t.columnas[i]?.tipo ?? "");
  const filas = t.filas.slice(0, FILAS_VISTA);
  return (
    <div>
      <h3 className="mb-1.5 text-sm font-semibold">{t.titulo}</h3>
      {!t.filas.length ? (
        <p className="rounded-md border px-3 py-3 text-sm text-muted-foreground">Sin registros en el periodo.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs text-muted-foreground">
              <tr>
                {t.columnas.map((c, i) => (
                  <th key={c.titulo} className={cn("px-3 py-2 font-medium whitespace-nowrap", numerica(i) ? "text-right" : "text-left")}>
                    {c.titulo}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {filas.map((f, j) => (
                <tr key={j}>
                  {f.map((v, i) => (
                    <td key={i} className={cn("px-3 py-1.5", numerica(i) ? "text-right tabular-nums whitespace-nowrap" : "max-w-72 truncate")} title={typeof v === "string" ? v : undefined}>
                      {celdaReporte(v, t.columnas[i]?.tipo ?? "texto")}
                    </td>
                  ))}
                </tr>
              ))}
              {t.totales && (
                <tr className="bg-secondary/60 font-semibold">
                  {t.totales.map((v, i) => (
                    <td key={i} className={cn("px-3 py-1.5", numerica(i) && "text-right tabular-nums whitespace-nowrap")}>
                      {celdaReporte(v, t.columnas[i]?.tipo ?? "texto")}
                    </td>
                  ))}
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {t.filas.length > FILAS_VISTA && (
        <p className="mt-1 text-xs text-muted-foreground">
          Mostrando {FILAS_VISTA} de {t.filas.length.toLocaleString("es-CO")} filas: descargue el Excel o el PDF para verlas todas.
        </p>
      )}
      {t.nota && <p className="mt-1 text-xs text-muted-foreground italic">{t.nota}</p>}
    </div>
  );
}

function GenerarCorte({ onGenerado }: { onGenerado: () => void }) {
  const { tenant } = useTenant();
  const anterior = rango("anterior").desde.slice(0, 7);
  const [periodo, setPeriodo] = useState(anterior);
  const [enviando, setEnviando] = useState(false);

  async function generar() {
    const [anio, mes] = periodo.split("-");
    setEnviando(true);
    try {
      const c = await api<Corte>(`${base(tenant.tenant_id)}/cortes/${anio}/${Number(mes)}`, { method: "POST" });
      toast.success(`Corte de ${c.nombre} generado`);
      onGenerado();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <input type="month" aria-label="Mes del corte" value={periodo} max={anterior} onChange={(e) => setPeriodo(e.target.value)} className="h-8 rounded-md border bg-card px-2 text-sm" />
      <Button size="sm" variant="outline" disabled={!periodo || enviando} onClick={generar}>
        {enviando ? <Loader2 className="size-4 animate-spin" /> : <CalendarCheck className="size-4" />}
        Generar corte
      </Button>
    </div>
  );
}

export function ReportesView() {
  const { tenant } = useTenant();
  const b = base(tenant.tenant_id);
  const permitido = puede(tenant.role, "reportes");
  const verCortes = puede(tenant.role, "cortes");
  const disponibles = (Object.keys(REPORTES) as TipoReporte[]).filter((t) => REPORTES[t].roles.includes(tenant.role));

  const [tipo, setTipo] = useState<TipoReporte | undefined>(disponibles[0]);
  const [preset, setPreset] = useState<Preset>("mes");
  const [fechas, setFechas] = useState(rango("mes"));
  const [consulta, setConsulta] = useState<string | null>(null);
  const { data: reporte, isLoading, error } = useSWR<ReporteJson>(consulta, fetcher);
  const { data: listaCortes, mutate: refrescarCortes } = useSWR<Corte[]>(verCortes ? `${b}/cortes` : null, fetcher);

  const parametros = useMemo(() => new URLSearchParams(fechas).toString(), [fechas]);
  const descarga = (formato: "xlsx" | "pdf") => `/api/proxy${b}/reportes/${tipo}?${parametros}&formato=${formato}`;

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Reportes" description="Informes exportables a Excel y PDF, y cortes mensuales para el Consejo." />

      <div className="space-y-6 p-4 sm:p-6">
        {tipo && (
          <Seccion titulo="Generar informe" descripcion={REPORTES[tipo].descripcion}>
            <div className="space-y-4 p-4">
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3" role="radiogroup" aria-label="Tipo de informe">
                {disponibles.map((t) => (
                  <button
                    key={t}
                    type="button"
                    role="radio"
                    aria-checked={tipo === t}
                    onClick={() => {
                      setTipo(t);
                      setConsulta(null);
                    }}
                    className={cn(
                      "rounded-md border px-3 py-2 text-left text-sm transition-colors",
                      tipo === t ? "border-primary bg-accent/60 font-medium" : "hover:border-primary/40 hover:bg-accent/30",
                    )}
                  >
                    {REPORTES[t].titulo}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap items-end gap-2">
                <div className="inline-flex rounded-md border bg-secondary/50 p-0.5" role="radiogroup" aria-label="Periodo">
                  {(
                    [
                      ["mes", "Este mes"],
                      ["anterior", "Mes anterior"],
                      ["anio", "Este año"],
                      ["personalizado", "Personalizado"],
                    ] as [Preset, string][]
                  ).map(([p, etiqueta]) => (
                    <button
                      key={p}
                      type="button"
                      role="radio"
                      aria-checked={preset === p}
                      onClick={() => {
                        setPreset(p);
                        if (p !== "personalizado") setFechas(rango(p));
                        setConsulta(null);
                      }}
                      className={cn("rounded px-3 py-1.5 text-sm", preset === p ? "bg-card font-medium shadow-sm" : "text-muted-foreground hover:text-foreground")}
                    >
                      {etiqueta}
                    </button>
                  ))}
                </div>
                {preset === "personalizado" && (
                  <>
                    <label className="flex flex-col text-xs text-muted-foreground">
                      Desde
                      <input type="date" value={fechas.desde} onChange={(e) => setFechas((f) => ({ ...f, desde: e.target.value }))} className={cn(campoClase(), "mt-1 w-40")} />
                    </label>
                    <label className="flex flex-col text-xs text-muted-foreground">
                      Hasta
                      <input type="date" value={fechas.hasta} onChange={(e) => setFechas((f) => ({ ...f, hasta: e.target.value }))} className={cn(campoClase(), "mt-1 w-40")} />
                    </label>
                  </>
                )}
                <div className="ml-auto flex flex-wrap gap-2">
                  <Button onClick={() => setConsulta(`${b}/reportes/${tipo}?${parametros}`)}>
                    <Play className="size-4" /> Ver informe
                  </Button>
                  <Button variant="outline" asChild>
                    <a href={descarga("xlsx")} download>
                      <FileSpreadsheet className="size-4" /> Excel
                    </a>
                  </Button>
                  <Button variant="outline" asChild>
                    <a href={descarga("pdf")} download>
                      <FileText className="size-4" /> PDF
                    </a>
                  </Button>
                </div>
              </div>

              {consulta && (isLoading ? (
                <Skeleton className="h-48" />
              ) : error ? (
                <p className="text-sm text-destructive">{mensajeError(error)}</p>
              ) : reporte ? (
                <div className="space-y-5 border-t pt-4">
                  <div>
                    <h2 className="text-base font-semibold">{reporte.titulo}</h2>
                    <p className="text-sm text-muted-foreground">
                      {reporte.copropiedad} · {reporte.periodo}
                    </p>
                  </div>
                  <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
                    {reporte.resumen.map((r) => (
                      <div key={r.etiqueta} className="rounded-md border px-3 py-2">
                        <dt className="text-xs text-muted-foreground">{r.etiqueta}</dt>
                        <dd className="font-semibold tabular-nums">{r.valor}</dd>
                      </div>
                    ))}
                  </dl>
                  {reporte.tablas.map((t) => (
                    <TablaReporte key={t.titulo} t={t} />
                  ))}
                </div>
              ) : null)}
            </div>
          </Seccion>
        )}

        {verCortes && (
          <Seccion
            titulo="Cortes mensuales"
            descripcion="Resumen ejecutivo de cada mes cerrado. Se genera solo el día 1 y se envía a la administración y al consejo."
            acciones={puede(tenant.role, "generarCorte") && <GenerarCorte onGenerado={() => void refrescarCortes()} />}
          >
            {!listaCortes ? (
              <Skeleton className="m-4 h-20" />
            ) : !listaCortes.length ? (
              <Vacio icono={CalendarCheck} titulo="Aún no hay cortes mensuales" texto="El primer corte se genera automáticamente al cerrar el mes." />
            ) : (
              <ul className="divide-y">
                {listaCortes.map((c) => (
                  <li key={c.periodo} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <CalendarCheck className="size-5 text-primary" />
                    <div className="min-w-0 flex-1 text-sm">
                      <p className="font-medium">{c.nombre.charAt(0).toUpperCase() + c.nombre.slice(1)}</p>
                      <p className="text-muted-foreground">
                        {pesos(c.total_mes)} · {c.cantidad_mes} movimientos · generado {fechaHora(c.generado_at)}
                      </p>
                    </div>
                    {c.pdf_url && (
                      <Button size="sm" variant="outline" asChild>
                        <a href={c.pdf_url} target="_blank" rel="noreferrer">
                          <Download className="size-4" /> PDF
                        </a>
                      </Button>
                    )}
                    {c.xlsx_url && (
                      <Button size="sm" variant="outline" asChild>
                        <a href={c.xlsx_url}>
                          <Download className="size-4" /> Excel
                        </a>
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Seccion>
        )}
      </div>
    </div>
  );
}
