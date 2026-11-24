"use client";

import { AlertTriangle, Plus } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, Kpi, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import {
  baseActivos,
  ESTADO_NOVEDAD,
  horasTexto,
  type Novedad,
  PRIORIDAD_NOVEDAD,
  type PrioridadNovedad,
  puedeActivos,
  type Recomendacion,
} from "@/lib/activos";
import { fechaHora } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { useRefrescarActivos } from "./comunes";
import { NovedadDetalleSheet } from "./detalles";
import { NovedadFormDialog, RecomendacionDialog } from "./formularios-novedad";
import { ListaRecomendaciones } from "./hoja-vida-view";

const VISTAS = { abiertas: "Abiertas", cerradas: "Cerradas", todas: "Todas" } as const;
type Vista = keyof typeof VISTAS;

function useFiltros() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const setParam = (cambios: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    router.replace(`${pathname}?${p}`, { scroll: false });
  };
  return { params, setParam };
}

export function NovedadesView() {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const permitido = puedeActivos(tenant.role, "ver");
  const { params, setParam } = useFiltros();
  const refrescar = useRefrescarActivos();
  const [reportar, setReportar] = useState(false);
  const vista = (params.get("vista") as Vista) ?? "abiertas";
  const prioridad = params.get("prioridad") as PrioridadNovedad | null;
  const mias = params.get("mias") === "1";
  const abierta = params.get("id");

  const q = new URLSearchParams();
  if (vista === "abiertas") q.set("abiertas", "true");
  if (vista === "cerradas") ["CERRADA", "DESCARTADA"].forEach((e) => q.append("estado", e));
  if (prioridad) q.set("prioridad", prioridad);
  if (mias) q.set("mias", "true");
  const { data, isLoading } = useSWR<Novedad[]>(permitido ? `${b}/novedades?${q}` : null, fetcher, { keepPreviousData: true });
  const { data: abiertas } = useSWR<Novedad[]>(permitido ? `${b}/novedades?abiertas=true` : null, fetcher);

  if (!permitido) return <SinAcceso />;

  const sinAtender = abiertas?.filter((n) => n.estado === "REPORTADA") ?? [];
  const criticas = abiertas?.filter((n) => n.prioridad === "CRITICA") ?? [];
  const demoradas = sinAtender.filter((n) => (n.horas_sin_atender ?? 0) >= (n.prioridad === "CRITICA" ? 24 : 72));

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Novedades"
        description="Fallas reportadas y su atención: de reportada a cerrada, con trazabilidad."
        actions={
          puedeActivos(tenant.role, "reportarNovedad") && (
            <Button onClick={() => setReportar(true)}>
              <Plus className="size-4" /> Reportar falla
            </Button>
          )
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Kpi titulo="Abiertas" valor={String(abiertas?.length ?? "—")} />
          <Kpi titulo="Sin atender" valor={String(sinAtender.length)} destacado={sinAtender.length > 0} />
          <Kpi titulo="Críticas abiertas" valor={String(criticas.length)} destacado={criticas.length > 0} />
          <Kpi titulo="Demoradas" valor={String(demoradas.length)} detalle="Críticas > 24 h o altas > 72 h sin atender" destacado={demoradas.length > 0} />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-md border bg-card p-0.5" role="tablist">
            {(Object.keys(VISTAS) as Vista[]).map((v) => (
              <button
                key={v}
                type="button"
                role="tab"
                aria-selected={vista === v}
                onClick={() => setParam({ vista: v === "abiertas" ? null : v })}
                className={cn("h-8 rounded px-3 text-sm", vista === v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
              >
                {VISTAS[v]}
              </button>
            ))}
          </div>
          <select aria-label="Prioridad" value={prioridad ?? ""} onChange={(e) => setParam({ prioridad: e.target.value || null })} className={cn(campoClase(), "w-40")}>
            <option value="">Toda prioridad</option>
            {(Object.keys(PRIORIDAD_NOVEDAD) as PrioridadNovedad[]).map((p) => (
              <option key={p} value={p}>
                {PRIORIDAD_NOVEDAD[p].label}
              </option>
            ))}
          </select>
          <label className="inline-flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={mias} onChange={(e) => setParam({ mias: e.target.checked ? "1" : null })} className="size-4" />
            {tenant.role === "MANTENIMIENTO" ? "A mi cargo o reportadas por mí" : "Solo las mías"}
          </label>
        </div>

        <div className="rounded-lg border bg-card">
          {isLoading && !data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : !data?.length ? (
            <Vacio icono={AlertTriangle} titulo={vista === "abiertas" ? "No hay novedades abiertas" : "Sin novedades"} texto={vista === "abiertas" ? "Todo está atendido." : undefined} />
          ) : (
            <ul className="divide-y">
              {data.map((n) => (
                <li key={n.id}>
                  <button type="button" onClick={() => setParam({ id: n.id })} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-accent/40">
                    <span className={cn("mt-1.5 size-2.5 shrink-0 rounded-full", n.prioridad === "CRITICA" ? "bg-destructive" : n.prioridad === "ALTA" ? "bg-warning" : "bg-muted-foreground/40")} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium">
                        {n.codigo} · {n.activo.nombre}
                      </span>
                      <span className="block truncate text-sm text-muted-foreground">{n.descripcion}</span>
                      <span className="block text-xs text-muted-foreground">
                        {fechaHora(n.fecha_reporte)} · {n.reportado_por.nombre.replace(/\s*\(.*\)/, "")}
                        {n.asignado_a && ` · a cargo de ${n.asignado_a.nombre.replace(/\s*\(.*\)/, "")}`}
                        {n.contratista_asignado && ` · ${n.contratista_asignado.nombre}`}
                      </span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <Etiqueta tono={ESTADO_NOVEDAD[n.estado].tono}>{ESTADO_NOVEDAD[n.estado].label}</Etiqueta>
                      <Etiqueta tono={PRIORIDAD_NOVEDAD[n.prioridad].tono}>{PRIORIDAD_NOVEDAD[n.prioridad].label}</Etiqueta>
                      {n.horas_sin_atender !== null && n.horas_sin_atender >= 24 && (
                        <span className="text-xs font-medium text-destructive">{horasTexto(n.horas_sin_atender)} sin atender</span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <NovedadFormDialog abierto={reportar} onCambio={setReportar} onGuardado={(n) => { void refrescar(tenant.tenant_id); setParam({ id: n.id }); }} />
      <NovedadDetalleSheet id={abierta} onCerrar={() => setParam({ id: null })} />
    </div>
  );
}

export function RecomendacionesView() {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const permitido = puedeActivos(tenant.role, "ver");
  const { params, setParam } = useFiltros();
  const refrescar = useRefrescarActivos();
  const [rec, setRec] = useState<Recomendacion | null>(null);
  const [nueva, setNueva] = useState(false);
  const pendientes = params.get("todas") !== "1";
  const mias = params.get("mias") === "1";

  const q = new URLSearchParams();
  if (pendientes) q.set("pendientes", "true");
  if (mias) q.set("mias", "true");
  const prioridad = params.get("prioridad");
  if (prioridad) q.set("prioridad", prioridad);
  const { data } = useSWR<Recomendacion[]>(permitido ? `${b}/recomendaciones?${q}` : null, fetcher, { keepPreviousData: true });

  if (!permitido) return <SinAcceso />;

  const vencidas = data?.filter((r) => r.vencida).length ?? 0;
  const conCosto = data?.filter((r) => r.costo_estimado && (r.estado === "PENDIENTE" || r.estado === "EN_PROCESO")) ?? [];
  const totalCosto = conCosto.reduce((s, r) => s + Number(r.costo_estimado), 0);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Recomendaciones técnicas"
        description="Lo que los técnicos sugieren hacer, con responsable, fecha límite y costo estimado."
        actions={
          puedeActivos(tenant.role, "gestionarRecomendacion") &&
          tenant.role !== "MANTENIMIENTO" && (
            <Button onClick={() => setNueva(true)}>
              <Plus className="size-4" /> Nueva
            </Button>
          )
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Kpi titulo={pendientes ? "Pendientes" : "Recomendaciones"} valor={String(data?.length ?? "—")} />
          <Kpi titulo="Vencidas" valor={String(vencidas)} destacado={vencidas > 0} />
          {(tenant.role === "ADMIN" || tenant.role === "CONTABILIDAD") && (
            <Kpi titulo="Costo estimado pendiente" valor={totalCosto.toLocaleString("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 })} detalle="Entra en la proyección del presupuesto" />
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={!pendientes} onChange={(e) => setParam({ todas: e.target.checked ? "1" : null })} className="size-4" />
            Incluir ejecutadas y descartadas
          </label>
          <label className="inline-flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={mias} onChange={(e) => setParam({ mias: e.target.checked ? "1" : null })} className="size-4" />
            A mi cargo
          </label>
          <select aria-label="Prioridad" value={prioridad ?? ""} onChange={(e) => setParam({ prioridad: e.target.value || null })} className={cn(campoClase(), "w-40")}>
            <option value="">Toda prioridad</option>
            <option value="ALTA">Alta</option>
            <option value="MEDIA">Media</option>
            <option value="BAJA">Baja</option>
          </select>
        </div>
        {data ? <ListaRecomendaciones recs={data} onAbrir={setRec} mostrarActivo /> : <Skeleton className="h-48" />}
      </div>
      <RecomendacionDialog abierto={!!rec} onCambio={(v) => !v && setRec(null)} recomendacion={rec} onGuardado={() => void refrescar(tenant.tenant_id)} />
      <RecomendacionDialog abierto={nueva} onCambio={setNueva} onGuardado={() => void refrescar(tenant.tenant_id)} />
    </div>
  );
}
