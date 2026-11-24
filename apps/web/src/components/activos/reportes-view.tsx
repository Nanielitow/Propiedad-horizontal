"use client";

import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, mensajeError, SinAcceso } from "@/components/recaudos/comunes";
import { TablaReporte } from "@/components/recaudos/reportes-view";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { baseActivos, puedeActivos, REPORTES_ACTIVOS, type TipoReporteActivos } from "@/lib/activos";
import { hoyBogota, type ReporteJson } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

export function ReportesActivosView() {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const disponibles = (Object.keys(REPORTES_ACTIVOS) as TipoReporteActivos[]).filter((t) => REPORTES_ACTIVOS[t].roles.includes(tenant.role));
  const pedido = params.get("tipo") as TipoReporteActivos | null;
  const tipo = pedido && disponibles.includes(pedido) ? pedido : disponibles[0];
  const hoy = hoyBogota();
  const desde = params.get("desde") ?? `${hoy.slice(0, 4)}-01-01`;
  const hasta = params.get("hasta") ?? hoy;

  const conPeriodo = tipo ? REPORTES_ACTIVOS[tipo].periodo : false;
  const rango = conPeriodo ? `desde=${desde}&hasta=${hasta}` : "";
  const ruta = tipo ? `${b}/reportes/${tipo}` : null;
  const { data: reporte, isLoading, error } = useSWR<ReporteJson>(ruta && puedeActivos(tenant.role, "reportes") ? `${ruta}?${rango}` : null, fetcher);

  function setParam(cambios: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    router.replace(`${pathname}?${p}`, { scroll: false });
  }

  if (!puedeActivos(tenant.role, "reportes") || !tipo) return <SinAcceso />;
  const descarga = (formato: "xlsx" | "pdf") => `/api/proxy${ruta}?formato=${formato}${rango ? `&${rango}` : ""}`;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Reportes de mantenimiento" description="En pantalla, en Excel (para analizar) o en PDF (para la asamblea o el consejo)." />
      <div className="grid gap-4 p-4 sm:p-6 lg:grid-cols-[18rem_1fr]">
        <nav aria-label="Informes" className="space-y-1">
          {disponibles.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setParam({ tipo: t })}
              aria-current={t === tipo ? "page" : undefined}
              className={cn("w-full rounded-md border px-3 py-2.5 text-left transition-colors", t === tipo ? "border-primary bg-accent" : "bg-card hover:bg-accent/50")}
            >
              <span className="block text-sm font-medium">{REPORTES_ACTIVOS[t].titulo}</span>
              <span className="block text-xs text-muted-foreground">{REPORTES_ACTIVOS[t].descripcion}</span>
            </button>
          ))}
          <p className="px-1 pt-2 text-xs text-muted-foreground">La hoja de vida individual de cada activo (con su QR) se descarga desde su ficha.</p>
        </nav>

        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-end gap-2 rounded-lg border bg-card p-3">
            {conPeriodo ? (
              <>
                <label className="flex flex-col text-xs text-muted-foreground">
                  Desde
                  <input type="date" value={desde} max={hasta} onChange={(e) => setParam({ desde: e.target.value || null })} className={cn(campoClase(), "mt-1 w-40")} />
                </label>
                <label className="flex flex-col text-xs text-muted-foreground">
                  Hasta
                  <input type="date" value={hasta} min={desde} onChange={(e) => setParam({ hasta: e.target.value || null })} className={cn(campoClase(), "mt-1 w-40")} />
                </label>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Corte a hoy: muestra el estado actual.</p>
            )}
            <div className="ml-auto flex gap-2">
              <Button variant="outline" asChild>
                <a href={descarga("xlsx")} download>
                  <FileSpreadsheet className="size-4" /> Excel
                </a>
              </Button>
              <Button asChild>
                <a href={descarga("pdf")} download>
                  <Download className="size-4" /> PDF
                </a>
              </Button>
            </div>
          </div>

          {error ? (
            <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{mensajeError(error)}</p>
          ) : isLoading || !reporte ? (
            <Skeleton className="h-96" />
          ) : (
            <div className="space-y-5 rounded-lg border bg-card p-4">
              <div>
                <h2 className="flex items-center gap-2 text-base font-semibold">
                  <FileText className="size-4 text-muted-foreground" /> {reporte.titulo}
                </h2>
                <p className="text-sm text-muted-foreground">
                  {reporte.copropiedad} · {reporte.periodo}
                </p>
              </div>
              <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2 xl:grid-cols-3">
                {reporte.resumen.map((r) => (
                  <div key={r.etiqueta} className="rounded-md bg-secondary/50 px-3 py-2">
                    <dt className="text-xs text-muted-foreground">{r.etiqueta}</dt>
                    <dd className="text-sm font-semibold tabular-nums">{r.valor}</dd>
                  </div>
                ))}
              </dl>
              {reporte.tablas.map((t) => (
                <TablaReporte key={t.titulo} t={t} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
