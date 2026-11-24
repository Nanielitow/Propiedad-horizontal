"use client";

import { Ban, CheckCircle2, CircleDashed, MinusCircle, Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { useTenant } from "@/components/layout/tenant-context";
import { Etiqueta, MotivoDialog } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import {
  baseActivos,
  ESTADO_NOVEDAD,
  ESTADO_RECOMENDACION,
  horasTexto,
  type MantenimientoDetalle,
  type Novedad,
  NOVEDAD_ABIERTA,
  PRIORIDAD_NOVEDAD,
  PRIORIDAD_RECOMENDACION,
  puedeActivos,
  TIPO_MANTENIMIENTO,
} from "@/lib/activos";
import { fechaCorta, fechaHora, pesos } from "@/lib/recaudos";

import { EstadoActivoBadge, Evidencias, Fila, useRefrescarActivos } from "./comunes";
import { MantenimientoSheet } from "./formulario-mantenimiento";
import { NovedadAvanceDialog } from "./formularios-novedad";

const RESULTADO_ICONO = {
  HECHO: <CheckCircle2 className="size-4 text-success" aria-label="Hecho" />,
  NO_APLICA: <MinusCircle className="size-4 text-muted-foreground" aria-label="No aplica" />,
  PENDIENTE: <CircleDashed className="size-4 text-warning" aria-label="Pendiente" />,
};

function Bloque({ titulo, texto }: { titulo: string; texto: string | null }) {
  if (!texto) return null;
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{titulo}</p>
      <p className="mt-0.5 text-sm whitespace-pre-line">{texto}</p>
    </div>
  );
}

export function MantenimientoDetalleSheet({ id, onCerrar }: { id: string | null; onCerrar: () => void }) {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const refrescar = useRefrescarActivos();
  const { data: m, mutate } = useSWR<MantenimientoDetalle>(id ? `${b}/mantenimientos/${id}` : null, fetcher);
  const [anular, setAnular] = useState(false);

  return (
    <Sheet open={!!id} onOpenChange={(v) => !v && onCerrar()}>
      <SheetContent className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-lg">
        {!m ? (
          <div className="space-y-3 p-4">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-32" />
          </div>
        ) : (
          <>
            <SheetHeader>
              <SheetTitle className="flex flex-wrap items-center gap-2">
                {m.codigo}
                <Etiqueta tono={TIPO_MANTENIMIENTO[m.tipo].tono}>{TIPO_MANTENIMIENTO[m.tipo].label}</Etiqueta>
                {m.anulado && <Etiqueta tono="danger">Anulado</Etiqueta>}
              </SheetTitle>
              <SheetDescription>
                <Link href={`/${tenant.tenant_slug}/activos/${m.activo.id}`} className="font-medium text-primary hover:underline">
                  {m.activo_codigo} {m.activo.nombre}
                </Link>{" "}
                · {fechaCorta(m.fecha_ejecucion)}
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-4 px-4 pb-6">
              {m.anulado && (
                <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
                  <p className="font-medium text-destructive">Anulado por {m.anulado_por?.nombre} · {m.anulado_at && fechaHora(m.anulado_at)}</p>
                  <p className="mt-1">{m.motivo_anulacion}</p>
                </div>
              )}
              <dl className="divide-y">
                <Fila k="Técnico" v={m.nombre_tecnico} />
                {m.contratista && <Fila k="Contratista" v={m.contratista.nombre} />}
                {m.plan && <Fila k="Plan" v={m.plan.nombre} />}
                {m.novedad && <Fila k="Resuelve" v={m.novedad.nombre} />}
                <Fila k="Estado en que quedó" v={<EstadoActivoBadge estado={m.estado_post_intervencion} />} />
                {m.tiempo_ejecucion_horas && <Fila k="Tiempo" v={`${Number(m.tiempo_ejecucion_horas)} h`} />}
                {m.costo_total !== null && (
                  <>
                    <Fila k="Mano de obra" v={pesos(m.costo_mano_obra)} />
                    <Fila k="Repuestos" v={pesos(m.costo_repuestos)} />
                    <Fila k="Costo total" v={<span className="font-semibold">{pesos(m.costo_total)}</span>} />
                  </>
                )}
                {m.fecha_proximo_recomendado && <Fila k="Próxima recomendada" v={fechaCorta(m.fecha_proximo_recomendado)} />}
                <Fila k="Registrado por" v={`${m.registrado_por.nombre.replace(/\s*\(.*\)/, "")} · ${fechaHora(m.created_at)}`} />
              </dl>
              <Bloque titulo="Diagnóstico inicial" texto={m.diagnostico_inicial} />
              <Bloque titulo="Trabajo realizado" texto={m.actividades_realizadas} />
              <Bloque titulo="Repuestos utilizados" texto={m.repuestos_utilizados} />
              <Bloque titulo="Hallazgos" texto={m.novedades_encontradas} />
              {m.checklist.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Lista de chequeo</p>
                  <ul className="space-y-1">
                    {m.checklist.map((c) => (
                      <li key={c.actividad} className="flex items-center gap-2 text-sm">
                        {RESULTADO_ICONO[c.resultado]} {c.actividad}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {m.recomendaciones.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Recomendaciones del técnico</p>
                  <ul className="space-y-1.5">
                    {m.recomendaciones.map((r) => (
                      <li key={r.id} className="rounded-md border p-2 text-sm">
                        <p>{r.descripcion}</p>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          <Etiqueta tono={PRIORIDAD_RECOMENDACION[r.prioridad].tono}>Prioridad {PRIORIDAD_RECOMENDACION[r.prioridad].label.toLowerCase()}</Etiqueta>
                          <Etiqueta tono={ESTADO_RECOMENDACION[r.estado].tono}>{ESTADO_RECOMENDACION[r.estado].label}</Etiqueta>
                          {r.costo_estimado && <Etiqueta tono="neutral">{pesos(r.costo_estimado)}</Etiqueta>}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Separator />
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">Fotos y archivos</p>
                <Evidencias
                  tenantId={tenant.tenant_id}
                  entidad="MANTENIMIENTO"
                  entidadId={m.id}
                  momentos={["ANTES", "DESPUES", "INFORME", "FACTURA"]}
                  puedeSubir={puedeActivos(tenant.role, "subirFotos") && !m.anulado}
                />
              </div>
              {!m.anulado && puedeActivos(tenant.role, "anularMantenimiento") && (
                <Button variant="destructive" size="sm" onClick={() => setAnular(true)}>
                  <Ban className="size-4" /> Anular registro
                </Button>
              )}
            </div>
            <MotivoDialog
              abierto={anular}
              onCambio={setAnular}
              titulo={`Anular ${m.codigo}`}
              descripcion="El registro queda visible como anulado. Si cumplía una actividad del plan, esta vuelve a quedar pendiente."
              boton="Anular"
              onConfirmar={async (motivo) => {
                await api(`${b}/mantenimientos/${m.id}/anular`, { method: "POST", json: { motivo } });
                toast.success(`${m.codigo} anulado`);
                await mutate();
                await refrescar(tenant.tenant_id);
              }}
            />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export function NovedadDetalleSheet({ id, onCerrar }: { id: string | null; onCerrar: () => void }) {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const refrescar = useRefrescarActivos();
  const { data: n, mutate } = useSWR<Novedad>(id ? `${b}/novedades/${id}` : null, fetcher);
  const [avance, setAvance] = useState(false);
  const [correctivo, setCorrectivo] = useState(false);
  const [mtoAbierto, setMtoAbierto] = useState<string | null>(null);

  const abierta = n ? NOVEDAD_ABIERTA.includes(n.estado) : false;
  const actualizar = async () => {
    await mutate();
    await refrescar(tenant.tenant_id);
  };

  return (
    <Sheet open={!!id} onOpenChange={(v) => !v && onCerrar()}>
      <SheetContent className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-lg">
        {!n ? (
          <div className="space-y-3 p-4">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-32" />
          </div>
        ) : (
          <>
            <SheetHeader>
              <SheetTitle className="flex flex-wrap items-center gap-2">
                {n.codigo}
                <Etiqueta tono={PRIORIDAD_NOVEDAD[n.prioridad].tono}>{PRIORIDAD_NOVEDAD[n.prioridad].label}</Etiqueta>
                <Etiqueta tono={ESTADO_NOVEDAD[n.estado].tono} title={ESTADO_NOVEDAD[n.estado].ayuda}>
                  {ESTADO_NOVEDAD[n.estado].label}
                </Etiqueta>
              </SheetTitle>
              <SheetDescription>
                <Link href={`/${tenant.tenant_slug}/activos/${n.activo.id}`} className="font-medium text-primary hover:underline">
                  {n.activo_codigo} {n.activo.nombre}
                </Link>{" "}
                · {n.ubicacion}
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-4 px-4 pb-6">
              <p className="text-sm whitespace-pre-line">{n.descripcion}</p>
              {n.horas_sin_atender !== null && n.horas_sin_atender >= 24 && (
                <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  Lleva {horasTexto(n.horas_sin_atender)} sin atender.
                </p>
              )}
              <dl className="divide-y">
                <Fila k="Reportada por" v={`${n.reportado_por.nombre.replace(/\s*\(.*\)/, "")} · ${fechaHora(n.fecha_reporte)}`} />
                {n.riesgo_identificado && <Fila k="Riesgo" v={n.riesgo_identificado} />}
                {n.fecha_atencion && <Fila k="Atendida" v={fechaHora(n.fecha_atencion)} />}
                {n.asignado_a && <Fila k="Responsable" v={n.asignado_a.nombre.replace(/\s*\(.*\)/, "")} />}
                {n.contratista_asignado && <Fila k="Contratista" v={n.contratista_asignado.nombre} />}
                {n.cotizacion_id && (
                  <Fila
                    k="Cotizaciones"
                    v={
                      <Link href={`/${tenant.tenant_slug}/quotes/${n.cotizacion_id}`} className="text-primary hover:underline">
                        Ver comparación
                      </Link>
                    }
                  />
                )}
                {n.costo_reparacion && <Fila k="Costo de la reparación" v={pesos(n.costo_reparacion)} />}
                {n.cerrada_at && <Fila k="Cerrada" v={`${fechaHora(n.cerrada_at)}${n.cerrada_por ? ` · ${n.cerrada_por.nombre.replace(/\s*\(.*\)/, "")}` : ""}`} />}
              </dl>
              <Bloque titulo="Diagnóstico" texto={n.diagnostico} />
              <Bloque titulo="Solución" texto={n.solucion_implementada} />
              <Bloque titulo="Motivo del descarte" texto={n.motivo_descarte} />
              {n.mantenimientos.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Mantenimientos que la resolvieron</p>
                  <div className="flex flex-wrap gap-1.5">
                    {n.mantenimientos.map((m) => (
                      <Button key={m.id} variant="outline" size="sm" onClick={() => setMtoAbierto(m.id)}>
                        <Wrench className="size-3.5" /> {m.nombre}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
              {abierta && (
                <div className="flex flex-wrap gap-2">
                  {puedeActivos(tenant.role, "gestionarNovedad") && (
                    <Button onClick={() => setAvance(true)}>Siguiente paso</Button>
                  )}
                  {puedeActivos(tenant.role, "registrarMantenimiento") && (
                    <Button variant="outline" onClick={() => setCorrectivo(true)}>
                      <Wrench className="size-4" /> Registrar reparación
                    </Button>
                  )}
                </div>
              )}
              <Separator />
              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">Fotos</p>
                <Evidencias
                  tenantId={tenant.tenant_id}
                  entidad="NOVEDAD"
                  entidadId={n.id}
                  momentos={["EVIDENCIA", "ANTES", "DESPUES"]}
                  puedeSubir={puedeActivos(tenant.role, "subirFotos") && abierta}
                />
              </div>
            </div>
            <NovedadAvanceDialog abierto={avance} onCambio={setAvance} novedad={n} onGuardado={actualizar} />
            <MantenimientoSheet abierto={correctivo} onCambio={setCorrectivo} novedad={n} onGuardado={actualizar} />
            <MantenimientoDetalleSheet id={mtoAbierto} onCerrar={() => setMtoAbierto(null)} />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
