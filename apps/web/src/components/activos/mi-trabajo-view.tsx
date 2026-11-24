"use client";

import { AlertTriangle, CalendarCheck, QrCode } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Etiqueta, Seccion, SinAcceso } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { type Actividad, baseActivos, ESTADO_NOVEDAD, type Novedad, PRIORIDAD_NOVEDAD, puedeActivos, type Recomendacion } from "@/lib/activos";
import { fechaHora } from "@/lib/recaudos";

import { useRefrescarActivos } from "./comunes";
import { NovedadDetalleSheet } from "./detalles";
import { MantenimientoSheet } from "./formulario-mantenimiento";
import { NovedadFormDialog, RecomendacionDialog } from "./formularios-novedad";
import { ActividadFila, ListaRecomendaciones } from "./hoja-vida-view";

/** Entrada del técnico: lo que tiene asignado, ordenado por urgencia. */
export function MiTrabajoView() {
  const { tenant, user } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const permitido = puedeActivos(tenant.role, "ver");
  const refrescar = useRefrescarActivos();
  const { data: actividades } = useSWR<Actividad[]>(permitido ? `${b}/actividades?mias=true` : null, fetcher);
  const { data: novedades } = useSWR<Novedad[]>(permitido ? `${b}/novedades?abiertas=true&mias=true` : null, fetcher);
  const { data: recs } = useSWR<Recomendacion[]>(permitido ? `${b}/recomendaciones?pendientes=true&mias=true` : null, fetcher);
  const [ejecutar, setEjecutar] = useState<Actividad | null>(null);
  const [nov, setNov] = useState<string | null>(null);
  const [rec, setRec] = useState<Recomendacion | null>(null);
  const [falla, setFalla] = useState(false);

  if (!permitido) return <SinAcceso />;

  const urgentes = actividades?.filter((x) => (x.dias_restantes ?? 99) <= 0) ?? [];
  const proximas = actividades?.filter((x) => (x.dias_restantes ?? 99) > 0) ?? [];
  const nombre = user.full_name.replace(/\s*\(.*\)/, "").split(" ")[0];
  const actualizar = () => void refrescar(tenant.tenant_id);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title={`Hola, ${nombre}`} description="Su trabajo de mantenimiento: lo vencido y lo de hoy primero." />
      <div className="mx-auto w-full max-w-3xl space-y-4 p-4 sm:p-6">
        <div className="grid grid-cols-2 gap-2">
          <div className="flex items-start gap-2 rounded-lg border bg-card p-3 text-sm">
            <QrCode className="mt-0.5 size-5 shrink-0 text-primary" />
            <span>
              <span className="font-medium">Escanee la etiqueta</span>
              <span className="block text-xs text-muted-foreground">Con la cámara del celular, para ver el equipo y registrar en sitio.</span>
            </span>
          </div>
          <Button variant="outline" className="h-auto flex-col gap-1 border-destructive/30 py-3 text-destructive hover:bg-destructive/5" onClick={() => setFalla(true)}>
            <AlertTriangle className="size-5" /> Reportar falla
          </Button>
        </div>

        {!actividades ? (
          <Skeleton className="h-40" />
        ) : (
          <>
            <Seccion titulo={urgentes.length ? `Para hoy y vencidas (${urgentes.length})` : "Para hoy"}>
              {urgentes.length === 0 ? (
                <p className="flex items-center gap-2 px-4 py-5 text-sm text-muted-foreground">
                  <CalendarCheck className="size-4 text-success" /> No tiene nada vencido ni para hoy.
                </p>
              ) : (
                <ul className="divide-y">
                  {urgentes.map((x) => (
                    <ActividadFila key={x.id} x={x} rol={tenant.role} mostrarActivo onAccion={() => setEjecutar(x)} />
                  ))}
                </ul>
              )}
            </Seccion>
            {proximas.length > 0 && (
              <Seccion titulo="Próximos 60 días">
                <ul className="divide-y">
                  {proximas.map((x) => (
                    <ActividadFila key={x.id} x={x} rol={tenant.role} mostrarActivo onAccion={() => setEjecutar(x)} />
                  ))}
                </ul>
              </Seccion>
            )}
          </>
        )}

        <Seccion titulo="Novedades a mi cargo" descripcion="Las que le asignaron y las que usted reportó.">
          {!novedades ? (
            <Skeleton className="m-4 h-16" />
          ) : novedades.length === 0 ? (
            <p className="px-4 py-5 text-sm text-muted-foreground">Ninguna abierta.</p>
          ) : (
            <ul className="divide-y">
              {novedades.map((n) => (
                <li key={n.id}>
                  <button type="button" onClick={() => setNov(n.id)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-accent/40">
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium">
                        {n.codigo} · {n.activo.nombre}
                      </span>
                      <span className="block truncate text-sm text-muted-foreground">{n.descripcion}</span>
                      <span className="block text-xs text-muted-foreground">{fechaHora(n.fecha_reporte)}</span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <Etiqueta tono={ESTADO_NOVEDAD[n.estado].tono}>{ESTADO_NOVEDAD[n.estado].label}</Etiqueta>
                      <Etiqueta tono={PRIORIDAD_NOVEDAD[n.prioridad].tono}>{PRIORIDAD_NOVEDAD[n.prioridad].label}</Etiqueta>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Seccion>

        {recs && recs.length > 0 && (
          <div className="space-y-2">
            <h2 className="text-sm font-semibold">Recomendaciones a mi cargo</h2>
            <ListaRecomendaciones recs={recs} onAbrir={setRec} mostrarActivo />
          </div>
        )}
      </div>

      <MantenimientoSheet abierto={!!ejecutar} onCambio={(v) => !v && setEjecutar(null)} actividad={ejecutar} onGuardado={actualizar} />
      <NovedadDetalleSheet id={nov} onCerrar={() => setNov(null)} />
      <RecomendacionDialog abierto={!!rec} onCambio={(v) => !v && setRec(null)} recomendacion={rec} onGuardado={actualizar} />
      <NovedadFormDialog abierto={falla} onCambio={setFalla} onGuardado={actualizar} />
    </div>
  );
}
