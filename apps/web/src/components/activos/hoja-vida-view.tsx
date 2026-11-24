"use client";

import {
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  Check,
  ClipboardList,
  FileText,
  Gauge,
  History,
  Link2,
  MoreHorizontal,
  Pause,
  Pencil,
  Play,
  Plus,
  Printer,
  QrCode,
  RefreshCw,
  Trash2,
  UserRound,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { usePdfViewer } from "@/components/pdf-viewer/viewer-context";
import { useTenant } from "@/components/layout/tenant-context";
import { Etiqueta, mensajeError, MotivoDialog, Seccion, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError, fetcher } from "@/lib/api";
import {
  type Actividad,
  type ActivoDetalle,
  type AuditoriaActivo,
  baseActivos,
  ESTADO_NOVEDAD,
  ESTADO_RECOMENDACION,
  NOVEDAD_ABIERTA,
  PERIODICIDAD,
  type Plan,
  PRIORIDAD_NOVEDAD,
  PRIORIDAD_RECOMENDACION,
  puedeActivos,
  type Recomendacion,
  textoDias,
  TIPO_DOCUMENTO,
  TIPO_MANTENIMIENTO,
} from "@/lib/activos";
import { fechaCorta, fechaHora, pesos } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { CriticidadBadge, EstadoActivoBadge, Evidencias, Fila, SemaforoBadge, SemaforoPunto, useRefrescarActivos } from "./comunes";
import { MantenimientoDetalleSheet, NovedadDetalleSheet } from "./detalles";
import { MantenimientoSheet } from "./formulario-mantenimiento";
import { ActivoFormDialog, LecturaDialog, VincularDocumentoDialog } from "./formularios-activo";
import { NovedadFormDialog, RecomendacionDialog } from "./formularios-novedad";
import { AsignarDialog, PlanFormDialog, ReprogramarDialog } from "./formularios-plan";

const CAMPO_AUDITORIA: Record<string, string> = {
  nombre: "Nombre",
  ubicacion: "Ubicación",
  estado: "Estado",
  criticidad: "Criticidad",
  marca: "Marca",
  modelo: "Modelo",
  fabricante: "Fabricante",
  numero_serie: "Serie",
  subtipo: "Tipo",
  especificaciones: "Especificaciones",
  vida_util_anios: "Vida útil",
  fecha_instalacion: "Instalación",
  fecha_vencimiento_garantia: "Garantía",
  qr_token: "Código QR",
  fecha_programada: "Fecha",
  asignado_a_id: "Responsable",
  activo: "Plan activo",
  aprobado_at: "Aprobación",
  diagnostico: "Diagnóstico",
  solucion_implementada: "Solución",
  prioridad: "Prioridad",
  responsable_id: "Responsable",
  motivo_baja: "Motivo de baja",
  anulado_at: "Anulación",
};
const ENTIDAD: Record<string, string> = {
  activo: "Activo",
  plan: "Plan",
  actividad: "Actividad",
  mantenimiento: "Mantenimiento",
  novedad: "Novedad",
  recomendacion: "Recomendación",
};

function valorAuditoria(k: string, v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (k.endsWith("_id") || k === "qr_token") return "cambiado";
  if (typeof v === "object") return "actualizadas";
  if (k === "activo") return v ? "sí" : "no";
  const s = String(v);
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? fechaCorta(s) : s.replaceAll("_", " ").toLowerCase();
}

export function HojaDeVidaView({ activoId }: { activoId: string }) {
  const { tenant } = useTenant();
  const rol = tenant.role;
  const b = baseActivos(tenant.tenant_id);
  const refrescar = useRefrescarActivos();
  const permitido = puedeActivos(rol, "ver");
  const visor = usePdfViewer();
  const { data: a, error, mutate } = useSWR<ActivoDetalle>(permitido ? `${b}/${activoId}` : null, fetcher);
  const { data: auditoria } = useSWR<AuditoriaActivo[]>(
    permitido && puedeActivos(rol, "auditoria") ? `${b}/auditoria/activo/${activoId}` : null,
    fetcher,
  );

  const [dialogo, setDialogo] = useState<null | "editar" | "plan" | "lectura" | "documento" | "baja" | "novedad" | "mantenimiento" | "recomendacion">(null);
  const [actividad, setActividad] = useState<Actividad | null>(null);
  const [accionActividad, setAccionActividad] = useState<null | "ejecutar" | "reprogramar" | "asignar">(null);
  const [pausar, setPausar] = useState<Plan | null>(null);
  const [mto, setMto] = useState<string | null>(null);
  const [nov, setNov] = useState<string | null>(null);
  const [rec, setRec] = useState<Recomendacion | null>(null);

  const actualizar = async () => {
    await mutate();
    await refrescar(tenant.tenant_id);
  };

  async function accion(fn: () => Promise<unknown>, ok: string) {
    try {
      await fn();
      toast.success(ok);
      await actualizar();
    } catch (e) {
      toast.error(mensajeError(e));
    }
  }

  if (!permitido) return <SinAcceso />;
  if (error) {
    return <SinAcceso texto={error instanceof ApiError && error.status === 404 ? "Activo no encontrado" : mensajeError(error)} />;
  }
  if (!a) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const vigente = a.estado !== "DADO_DE_BAJA";
  const abiertas = a.novedades.filter((n) => NOVEDAD_ABIERTA.includes(n.estado));
  const primeraAbierta = abiertas[0];
  const recsPendientes = a.recomendaciones.filter((r) => r.estado === "PENDIENTE" || r.estado === "EN_PROCESO");
  const vida = a.vida_util_consumida ? Number(a.vida_util_consumida) : null;
  const usaHorometro = a.planes.some((p) => p.periodicidad === "POR_HORAS_USO" && p.activo_plan);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title={a.nombre}
        description={`${a.codigo_interno} · ${a.categoria.nombre}${a.subtipo ? ` · ${a.subtipo}` : ""} · ${a.ubicacion}`}
        actions={
          vigente && (
            <>
              {puedeActivos(rol, "reportarNovedad") && (
                <Button variant="outline" onClick={() => setDialogo("novedad")} className="hidden sm:inline-flex">
                  <AlertTriangle className="size-4" /> Reportar falla
                </Button>
              )}
              {puedeActivos(rol, "registrarMantenimiento") && (
                <Button onClick={() => setDialogo("mantenimiento")}>
                  <Wrench className="size-4" /> <span className="hidden sm:inline">Registrar mantenimiento</span>
                  <span className="sm:hidden">Registrar</span>
                </Button>
              )}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon-lg" aria-label="Más acciones">
                    <MoreHorizontal className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  {puedeActivos(rol, "reportarNovedad") && (
                    <DropdownMenuItem onSelect={() => setDialogo("novedad")} className="sm:hidden">
                      <AlertTriangle className="size-4" /> Reportar falla
                    </DropdownMenuItem>
                  )}
                  {puedeActivos(rol, "editarActivo") && (
                    <DropdownMenuItem onSelect={() => setDialogo("editar")}>
                      <Pencil className="size-4" /> Editar hoja de vida
                    </DropdownMenuItem>
                  )}
                  {puedeActivos(rol, "crearPlan") && (
                    <DropdownMenuItem onSelect={() => setDialogo("plan")}>
                      <CalendarClock className="size-4" /> Nuevo plan de mantenimiento
                    </DropdownMenuItem>
                  )}
                  {puedeActivos(rol, "registrarMantenimiento") && usaHorometro && (
                    <DropdownMenuItem onSelect={() => setDialogo("lectura")}>
                      <Gauge className="size-4" /> Lectura del horómetro
                    </DropdownMenuItem>
                  )}
                  {puedeActivos(rol, "gestionarRecomendacion") && rol !== "MANTENIMIENTO" && (
                    <DropdownMenuItem onSelect={() => setDialogo("recomendacion")}>
                      <ClipboardList className="size-4" /> Nueva recomendación
                    </DropdownMenuItem>
                  )}
                  {puedeActivos(rol, "documentar") && (
                    <DropdownMenuItem onSelect={() => setDialogo("documento")}>
                      <Link2 className="size-4" /> Vincular documento
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem asChild>
                    <a href={`/api/proxy${b}/${a.id}/dossier.pdf`} download>
                      <FileText className="size-4" /> Descargar hoja de vida (PDF)
                    </a>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <a href={`/api/proxy${b}/etiquetas.pdf?ids=${a.id}`} download>
                      <Printer className="size-4" /> Imprimir etiqueta QR
                    </a>
                  </DropdownMenuItem>
                  {puedeActivos(rol, "editarActivo") && (
                    <DropdownMenuItem
                      onSelect={() =>
                        void accion(() => api(`${b}/${a.id}/qr/regenerar`, { method: "POST" }), "QR regenerado: imprima la nueva etiqueta")
                      }
                    >
                      <RefreshCw className="size-4" /> Regenerar QR
                    </DropdownMenuItem>
                  )}
                  {puedeActivos(rol, "darDeBaja") && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem variant="destructive" onSelect={() => setDialogo("baja")}>
                        <Trash2 className="size-4" /> Dar de baja
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          )
        }
      />

      <div className="space-y-4 p-4 sm:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <Link href={`/${tenant.tenant_slug}/activos`} className="mr-1 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" /> Activos
          </Link>
          <EstadoActivoBadge estado={a.estado} />
          {vigente && <SemaforoBadge color={a.semaforo} />}
          <CriticidadBadge criticidad={a.criticidad} />
        </div>

        {!vigente && (
          <div className="rounded-lg border bg-secondary/60 p-3 text-sm">
            <p className="font-medium">Dado de baja{a.fecha_baja ? ` el ${fechaCorta(a.fecha_baja)}` : ""}</p>
            <p className="text-muted-foreground">{a.motivo_baja}</p>
          </div>
        )}
        {primeraAbierta && (
          <button
            type="button"
            onClick={() => setNov(primeraAbierta.id)}
            className="flex w-full items-start gap-2 rounded-lg border border-warning/30 bg-warning-soft/60 p-3 text-left text-sm"
          >
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
            <span>
              <span className="font-medium">
                {abiertas.length === 1 ? "1 novedad abierta" : `${abiertas.length} novedades abiertas`}:
              </span>{" "}
              {primeraAbierta.codigo} {primeraAbierta.descripcion}
              {abiertas.length > 1 && " y otras"}
            </span>
          </button>
        )}

        <Tabs defaultValue="resumen">
          <TabsList>
            <TabsTrigger value="resumen">Resumen</TabsTrigger>
            <TabsTrigger value="plan">Plan y agenda</TabsTrigger>
            <TabsTrigger value="historial">Historial ({a.mantenimientos.filter((m) => !m.anulado).length})</TabsTrigger>
            <TabsTrigger value="novedades">Novedades{abiertas.length ? ` (${abiertas.length})` : ""}</TabsTrigger>
            <TabsTrigger value="recomendaciones">Recomendaciones{recsPendientes.length ? ` (${recsPendientes.length})` : ""}</TabsTrigger>
            <TabsTrigger value="documentos">Documentos</TabsTrigger>
            <TabsTrigger value="fotos">Fotos</TabsTrigger>
            {auditoria && <TabsTrigger value="auditoria">Auditoría</TabsTrigger>}
          </TabsList>

          {/* --- Resumen --- */}
          <TabsContent value="resumen" className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <Seccion titulo="Ficha técnica">
                <dl className="grid gap-x-8 px-4 py-2 sm:grid-cols-2">
                  <Fila k="Marca" v={a.marca} />
                  <Fila k="Modelo" v={a.modelo} />
                  <Fila k="Fabricante" v={a.fabricante} />
                  <Fila k="Serie" v={a.numero_serie} />
                  <Fila k="Instalación" v={a.fecha_instalacion ? fechaCorta(a.fecha_instalacion) : null} />
                  <Fila k="Instalado por" v={a.instalador?.nombre} />
                  <Fila k="Mantenimiento a cargo de" v={a.mantenedor?.nombre ?? "Personal interno"} />
                  <Fila
                    k="Garantía"
                    v={
                      a.fecha_vencimiento_garantia ? (
                        <span className={cn(a.garantia_vigente ? "text-success" : "text-muted-foreground")}>
                          {a.garantia_vigente ? "Vigente hasta" : "Venció el"} {fechaCorta(a.fecha_vencimiento_garantia)}
                        </span>
                      ) : null
                    }
                  />
                </dl>
                {Object.keys(a.especificaciones).length > 0 && (
                  <div className="border-t px-4 py-3">
                    <p className="mb-2 text-xs font-medium text-muted-foreground">Especificaciones</p>
                    <dl className="grid gap-x-8 sm:grid-cols-2">
                      {Object.entries(a.especificaciones).map(([k, v]) => (
                        <Fila key={k} k={k} v={String(v)} />
                      ))}
                    </dl>
                  </div>
                )}
              </Seccion>

              <Seccion titulo="Próximos mantenimientos" acciones={<span className="text-xs text-muted-foreground">{a.planes.filter((p) => p.activo_plan && p.aprobado).length} planes activos</span>}>
                {a.proximas_actividades.length === 0 ? (
                  <p className="px-4 py-6 text-sm text-muted-foreground">Sin actividades programadas.</p>
                ) : (
                  <ul className="divide-y">
                    {a.proximas_actividades.slice(0, 4).map((x) => (
                      <ActividadFila
                        key={x.id}
                        x={x}
                        rol={rol}
                        onAccion={(acc) => {
                          setActividad(x);
                          setAccionActividad(acc);
                        }}
                      />
                    ))}
                  </ul>
                )}
              </Seccion>
            </div>

            <div className="space-y-4">
              <Seccion titulo="Código QR" acciones={<QrCode className="size-4 text-muted-foreground" />}>
                <div className="flex flex-col items-center gap-2 p-4">
                  {/* <img>: SVG generado por la API detrás del proxy autenticado */}
                  <img src={`/api/proxy${b}/${a.id}/qr.svg`} alt={`QR de ${a.codigo_interno}`} className="size-40 rounded-md border bg-white p-1" />
                  <p className="text-center text-xs text-muted-foreground">Péguelo en el equipo: al escanearlo, el técnico ve su estado y registra trabajos.</p>
                </div>
              </Seccion>

              {vida !== null && (
                <Seccion titulo="Vida útil">
                  <div className="space-y-2 p-4">
                    <div className="h-2 overflow-hidden rounded-full bg-secondary">
                      <div
                        className={cn("h-full rounded-full", vida >= 90 ? "bg-destructive" : vida >= 70 ? "bg-warning" : "bg-success")}
                        style={{ width: `${Math.min(100, vida)}%` }}
                      />
                    </div>
                    <p className="text-sm">
                      <span className="font-semibold tabular-nums">{vida.toLocaleString("es-CO")} %</span> consumida de {a.vida_util_anios} años
                      {vida >= 90 && <span className="block text-xs text-destructive">Conviene presupuestar su reemplazo.</span>}
                    </p>
                  </div>
                </Seccion>
              )}

              {a.horas.map((h) => (
                <Seccion key={h.plan_id} titulo="Horómetro" acciones={<Gauge className="size-4 text-muted-foreground" />}>
                  <dl className="px-4 py-2">
                    <Fila k="Horas desde el último" v={`${Number(h.horas_desde_ultimo).toLocaleString("es-CO")} de ${h.intervalo_horas} h`} />
                    <Fila k="Restantes" v={<span className={cn(Number(h.horas_restantes) <= h.intervalo_horas / 10 && "text-destructive")}>{Number(h.horas_restantes).toLocaleString("es-CO")} h</span>} />
                    {h.uso_diario && <Fila k="Uso diario" v={`${Number(h.uso_diario).toLocaleString("es-CO")} h`} />}
                    {h.fecha_estimada && <Fila k="Fecha estimada" v={fechaCorta(h.fecha_estimada)} />}
                    {a.lecturas[0] && <Fila k="Última lectura" v={`${Number(a.lecturas[0].horas_acumuladas).toLocaleString("es-CO")} h · ${fechaCorta(a.lecturas[0].fecha)}`} />}
                  </dl>
                </Seccion>
              ))}

              {a.puede_ver_costos && (
                <Seccion titulo="Costos de mantenimiento">
                  <dl className="px-4 py-2">
                    <Fila k={`En ${new Date().getFullYear()}`} v={pesos(a.costo_anio)} />
                    <Fila k="Acumulado" v={pesos(a.costo_acumulado)} />
                  </dl>
                </Seccion>
              )}
            </div>
          </TabsContent>

          {/* --- Plan y agenda --- */}
          <TabsContent value="plan" className="space-y-4">
            <Seccion
              titulo="Planes preventivos"
              descripcion="Cada plan es una regla; las fechas concretas están en la agenda."
              acciones={
                puedeActivos(rol, "crearPlan") &&
                vigente && (
                  <Button size="sm" variant="outline" onClick={() => setDialogo("plan")}>
                    <Plus className="size-4" /> Nuevo plan
                  </Button>
                )
              }
            >
              {a.planes.length === 0 ? (
                <Vacio icono={CalendarClock} titulo="Sin plan de mantenimiento" texto="Cree un plan para que el sistema programe las fechas y avise antes de cada una." />
              ) : (
                <ul className="divide-y">
                  {a.planes.map((p) => (
                    <li key={p.id} className="flex flex-wrap items-start gap-3 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">{p.nombre}</p>
                        <p className="text-xs text-muted-foreground">
                          {p.periodicidad === "POR_HORAS_USO" ? `Cada ${p.intervalo_horas} h de uso` : PERIODICIDAD[p.periodicidad]}
                          {p.base_calculo === "DESDE_ULTIMA_EJECUCION" && " · cuenta desde la última ejecución"} · {p.contratista?.nombre ?? "Personal interno"}
                          {p.costo_estimado && ` · ${pesos(p.costo_estimado)} por vez`}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {p.ejecuciones} ejecutados{p.proxima_fecha && ` · próxima: ${fechaCorta(p.proxima_fecha)}`}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {!p.aprobado ? (
                          <Etiqueta tono="warning">Pendiente de aprobación</Etiqueta>
                        ) : !p.activo_plan ? (
                          <Etiqueta tono="neutral">Pausado</Etiqueta>
                        ) : (
                          <Etiqueta tono="success">Activo</Etiqueta>
                        )}
                        {puedeActivos(rol, "aprobarPlan") && vigente && (
                          <>
                            {!p.aprobado && p.activo_plan && (
                              <Button size="sm" onClick={() => void accion(() => api(`${b}/planes/${p.id}/aprobar`, { method: "POST" }), "Plan aprobado y programado")}>
                                <Check className="size-4" /> Aprobar
                              </Button>
                            )}
                            {p.aprobado && p.activo_plan && (
                              <Button size="sm" variant="ghost" onClick={() => setPausar(p)} aria-label={`Pausar ${p.nombre}`}>
                                <Pause className="size-4" />
                              </Button>
                            )}
                            {p.aprobado && !p.activo_plan && (
                              <Button size="sm" variant="outline" onClick={() => void accion(() => api(`${b}/planes/${p.id}/reanudar`, { method: "POST" }), "Plan reanudado")}>
                                <Play className="size-4" /> Reanudar
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Seccion>
            <Seccion titulo="Agenda" descripcion="Las próximas 12 fechas programadas, con su semáforo.">
              {a.proximas_actividades.length === 0 ? (
                <p className="px-4 py-6 text-sm text-muted-foreground">Sin actividades programadas.</p>
              ) : (
                <ul className="divide-y">
                  {a.proximas_actividades.map((x) => (
                    <ActividadFila
                      key={x.id}
                      x={x}
                      rol={rol}
                      onAccion={(acc) => {
                        setActividad(x);
                        setAccionActividad(acc);
                      }}
                    />
                  ))}
                </ul>
              )}
            </Seccion>
          </TabsContent>

          {/* --- Historial --- */}
          <TabsContent value="historial">
            <Seccion titulo="Historial de intervenciones" descripcion="Registro inmutable: los errores se anulan y quedan visibles.">
              {a.mantenimientos.length === 0 ? (
                <Vacio icono={History} titulo="Sin intervenciones registradas" />
              ) : (
                <ul className="divide-y">
                  {a.mantenimientos.map((m) => (
                    <li key={m.id}>
                      <button type="button" onClick={() => setMto(m.id)} className={cn("flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-accent/40", m.anulado && "opacity-60")}>
                        <span className="w-24 shrink-0 text-sm tabular-nums text-muted-foreground">{fechaCorta(m.fecha_ejecucion)}</span>
                        <span className="min-w-0 flex-1">
                          <span className={cn("block text-sm font-medium", m.anulado && "line-through")}>
                            {m.codigo} · {m.nombre_tecnico}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">{m.contratista?.nombre ?? "Personal interno"}</span>
                        </span>
                        <Etiqueta tono={m.anulado ? "danger" : TIPO_MANTENIMIENTO[m.tipo].tono}>{m.anulado ? "Anulado" : TIPO_MANTENIMIENTO[m.tipo].label}</Etiqueta>
                        {m.costo_total !== null && <span className="hidden w-28 text-right text-sm tabular-nums sm:block">{pesos(m.costo_total)}</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Seccion>
          </TabsContent>

          {/* --- Novedades --- */}
          <TabsContent value="novedades">
            <Seccion
              titulo="Novedades y fallas"
              acciones={
                puedeActivos(rol, "reportarNovedad") &&
                vigente && (
                  <Button size="sm" variant="outline" onClick={() => setDialogo("novedad")}>
                    <Plus className="size-4" /> Reportar falla
                  </Button>
                )
              }
            >
              {a.novedades.length === 0 ? (
                <Vacio icono={AlertTriangle} titulo="Sin novedades reportadas" />
              ) : (
                <ul className="divide-y">
                  {a.novedades.map((n) => (
                    <li key={n.id}>
                      <button type="button" onClick={() => setNov(n.id)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-accent/40">
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium">
                            {n.codigo} · {n.descripcion}
                          </span>
                          <span className="block text-xs text-muted-foreground">
                            {fechaHora(n.fecha_reporte)} · {n.reportado_por.nombre.replace(/\s*\(.*\)/, "")}
                          </span>
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
          </TabsContent>

          {/* --- Recomendaciones --- */}
          <TabsContent value="recomendaciones">
            <ListaRecomendaciones recs={a.recomendaciones} onAbrir={setRec} />
          </TabsContent>

          {/* --- Documentos --- */}
          <TabsContent value="documentos" className="grid gap-4 lg:grid-cols-2">
            <Seccion
              titulo="Documentos vinculados"
              descripcion="Manuales, garantías, contratos, certificados."
              acciones={
                puedeActivos(rol, "documentar") &&
                vigente && (
                  <Button size="sm" variant="outline" onClick={() => setDialogo("documento")}>
                    <Link2 className="size-4" /> Vincular
                  </Button>
                )
              }
            >
              {a.documentos.length === 0 ? (
                <Vacio icono={FileText} titulo="Sin documentos vinculados" />
              ) : (
                <ul className="divide-y">
                  {a.documentos.map((d) => (
                    <li key={d.document_id} className="flex items-center gap-3 px-4 py-2.5">
                      <FileText className="size-4 shrink-0 text-muted-foreground" />
                      <button
                        type="button"
                        onClick={() => visor.open({ documentId: d.document_id, title: d.titulo, page: 1 })}
                        className="min-w-0 flex-1 truncate text-left text-sm font-medium hover:underline"
                      >
                        {d.titulo}
                      </button>
                      <Etiqueta tono="neutral">{TIPO_DOCUMENTO[d.tipo]}</Etiqueta>
                      {puedeActivos(rol, "documentar") && vigente && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Desvincular ${d.titulo}`}
                          title="Desvincular (el documento sigue en el archivo)"
                          onClick={() => void accion(() => api(`${b}/${a.id}/documentos/${d.document_id}`, { method: "DELETE" }), "Documento desvinculado")}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Seccion>
            <Seccion titulo="Vencimientos de esos documentos" descripcion="Detectados por la IA (pólizas, contratos, certificados).">
              {a.vencimientos.length === 0 ? (
                <p className="px-4 py-6 text-sm text-muted-foreground">{rol === "ADMIN" || rol === "AUXILIAR" ? "Ningún vencimiento detectado." : "Los vencimientos los gestiona la administración."}</p>
              ) : (
                <ul className="divide-y">
                  {a.vencimientos.map((v) => (
                    <li key={v.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                      <span>{v.title}</span>
                      <span className="text-muted-foreground tabular-nums">{v.due_date ? fechaCorta(v.due_date) : "—"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Seccion>
          </TabsContent>

          {/* --- Fotos --- */}
          <TabsContent value="fotos">
            <Seccion titulo="Fotos del activo" descripcion="Las de cada mantenimiento y novedad están en su detalle.">
              <div className="p-4">
                <Evidencias tenantId={tenant.tenant_id} entidad="ACTIVO" entidadId={a.id} momentos={["FOTO_ACTIVO", "EVIDENCIA"]} puedeSubir={puedeActivos(rol, "subirFotos") && vigente} />
              </div>
            </Seccion>
          </TabsContent>

          {/* --- Auditoría --- */}
          {auditoria && (
            <TabsContent value="auditoria">
              <Seccion titulo="Trazabilidad" descripcion="Quién hizo qué y cuándo, con el motivo. La escribe la base de datos y nadie puede editarla.">
                <ol className="divide-y">
                  {auditoria.map((ev) => {
                    const cambios =
                      ev.accion !== "CREACION" && ev.valores_nuevos
                        ? Object.entries(ev.valores_nuevos).filter(([k]) => k in CAMPO_AUDITORIA)
                        : [];
                    return (
                      <li key={ev.id} className="px-4 py-2.5 text-sm">
                        <div className="flex flex-wrap items-center gap-x-2">
                          <span className="font-medium">
                            {ENTIDAD[ev.entidad] ?? ev.entidad} · {ev.accion === "CREACION" ? "creación" : ev.accion === "ANULACION" ? "anulación" : "cambio"}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {fechaHora(ev.fecha_hora)} · {ev.usuario?.nombre.replace(/\s*\(.*\)/, "") ?? "Sistema"}
                          </span>
                        </div>
                        {cambios.length > 0 && (
                          <ul className="mt-0.5 text-xs text-muted-foreground">
                            {cambios.map(([k, v]) => (
                              <li key={k}>
                                {CAMPO_AUDITORIA[k]}: {valorAuditoria(k, ev.valores_anteriores?.[k])} → {valorAuditoria(k, v)}
                              </li>
                            ))}
                          </ul>
                        )}
                        {ev.motivo && <p className="mt-0.5 text-xs">Motivo: {ev.motivo}</p>}
                      </li>
                    );
                  })}
                </ol>
              </Seccion>
            </TabsContent>
          )}
        </Tabs>
      </div>

      {/* Diálogos */}
      <ActivoFormDialog tenantId={tenant.tenant_id} abierto={dialogo === "editar"} onCambio={(v) => setDialogo(v ? "editar" : null)} activo={a} onGuardado={() => void actualizar()} />
      <PlanFormDialog tenantId={tenant.tenant_id} rol={rol} abierto={dialogo === "plan"} onCambio={(v) => setDialogo(v ? "plan" : null)} activoId={a.id} onGuardado={() => void actualizar()} />
      <LecturaDialog tenantId={tenant.tenant_id} abierto={dialogo === "lectura"} onCambio={(v) => setDialogo(v ? "lectura" : null)} activoId={a.id} ultima={a.lecturas[0]?.horas_acumuladas} onGuardado={() => void actualizar()} />
      <VincularDocumentoDialog
        tenantId={tenant.tenant_id}
        abierto={dialogo === "documento"}
        onCambio={(v) => setDialogo(v ? "documento" : null)}
        activoId={a.id}
        yaVinculados={a.documentos.map((d) => d.document_id)}
        onGuardado={() => void actualizar()}
      />
      <NovedadFormDialog abierto={dialogo === "novedad"} onCambio={(v) => setDialogo(v ? "novedad" : null)} activoId={a.id} onGuardado={() => void actualizar()} />
      <RecomendacionDialog abierto={dialogo === "recomendacion"} onCambio={(v) => setDialogo(v ? "recomendacion" : null)} activoId={a.id} onGuardado={() => void actualizar()} />
      <RecomendacionDialog abierto={!!rec} onCambio={(v) => !v && setRec(null)} recomendacion={rec} onGuardado={() => void actualizar()} />
      <MantenimientoSheet
        abierto={dialogo === "mantenimiento" || accionActividad === "ejecutar"}
        onCambio={(v) => {
          if (!v) {
            setDialogo(null);
            setAccionActividad(null);
          }
        }}
        activoId={a.id}
        actividad={accionActividad === "ejecutar" ? actividad : null}
        onGuardado={() => void actualizar()}
      />
      <ReprogramarDialog tenantId={tenant.tenant_id} abierto={accionActividad === "reprogramar"} onCambio={(v) => !v && setAccionActividad(null)} actividad={actividad} onGuardado={() => void actualizar()} />
      <AsignarDialog tenantId={tenant.tenant_id} abierto={accionActividad === "asignar"} onCambio={(v) => !v && setAccionActividad(null)} actividad={actividad} onGuardado={() => void actualizar()} />
      <MotivoDialog
        abierto={dialogo === "baja"}
        onCambio={(v) => setDialogo(v ? "baja" : null)}
        titulo={`Dar de baja ${a.codigo_interno}`}
        descripcion="El activo y todo su historial se conservan, pero ya no se programa ni se edita. Es definitivo."
        boton="Dar de baja"
        onConfirmar={async (motivo) => {
          await api(`${b}/${a.id}/baja`, { method: "POST", json: { motivo } });
          toast.success(`${a.codigo_interno} dado de baja`);
          await actualizar();
        }}
      />
      <MotivoDialog
        abierto={!!pausar}
        onCambio={(v) => !v && setPausar(null)}
        titulo={`Pausar «${pausar?.nombre}»`}
        descripcion="Se cancelan sus fechas pendientes (quedan en el historial). Puede reanudarlo después."
        boton="Pausar plan"
        peligro={false}
        onConfirmar={async (motivo) => {
          if (!pausar) return;
          await api(`${b}/planes/${pausar.id}/pausar`, { method: "POST", json: { motivo } });
          toast.success("Plan pausado");
          await actualizar();
        }}
      />
      <MantenimientoDetalleSheet id={mto} onCerrar={() => setMto(null)} />
      <NovedadDetalleSheet id={nov} onCerrar={() => setNov(null)} />
    </div>
  );
}

export function ActividadFila({
  x,
  rol,
  onAccion,
  mostrarActivo = false,
}: {
  x: Actividad;
  rol: import("@/lib/types").Role;
  onAccion: (a: "ejecutar" | "reprogramar" | "asignar") => void;
  mostrarActivo?: boolean;
}) {
  const pendiente = x.estado === "PROGRAMADA";
  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-2.5">
      <SemaforoPunto color={x.semaforo} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          {mostrarActivo ? `${x.activo_codigo} ${x.activo.nombre} · ` : ""}
          {x.plan.nombre}
        </p>
        <p className="text-xs text-muted-foreground">
          {fechaCorta(x.fecha_programada)}
          {pendiente && x.dias_restantes !== null && ` · ${textoDias(x.dias_restantes)}`}
          {x.reprogramada && ` · reprogramada (era el ${fechaCorta(x.fecha_original)})`}
          {x.contratista && ` · ${x.contratista.nombre}`}
          {x.asignado_a && (
            <span className="inline-flex items-center gap-0.5">
              {" · "}
              <UserRound className="size-3" /> {x.asignado_a.nombre.replace(/\s*\(.*\)/, "")}
            </span>
          )}
        </p>
      </div>
      {pendiente ? (
        <div className="flex gap-1">
          {puedeActivos(rol, "registrarMantenimiento") && (
            <Button size="sm" variant="outline" onClick={() => onAccion("ejecutar")}>
              <Wrench className="size-3.5" /> Ejecutar
            </Button>
          )}
          {puedeActivos(rol, "reprogramar") && (
            <Button size="sm" variant="ghost" onClick={() => onAccion("reprogramar")} aria-label="Reprogramar" title="Reprogramar">
              <CalendarClock className="size-4" />
            </Button>
          )}
          {puedeActivos(rol, "asignar") && (
            <Button size="sm" variant="ghost" onClick={() => onAccion("asignar")} aria-label="Asignar responsable" title="Asignar responsable">
              <UserRound className="size-4" />
            </Button>
          )}
        </div>
      ) : (
        <Etiqueta tono={x.estado === "EJECUTADA" ? "success" : "neutral"}>{x.estado === "EJECUTADA" ? "Ejecutada" : "Cancelada"}</Etiqueta>
      )}
    </li>
  );
}

export function ListaRecomendaciones({ recs, onAbrir, mostrarActivo = false }: { recs: Recomendacion[]; onAbrir: (r: Recomendacion) => void; mostrarActivo?: boolean }) {
  if (recs.length === 0) return <Vacio icono={ClipboardList} titulo="Sin recomendaciones" />;
  return (
    <ul className="divide-y rounded-lg border bg-card">
      {recs.map((r) => (
        <li key={r.id}>
          <button type="button" onClick={() => onAbrir(r)} className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-accent/40">
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">
                {mostrarActivo && <span className="text-muted-foreground">{r.activo_codigo} {r.activo.nombre} · </span>}
                {r.descripcion}
              </span>
              <span className="block text-xs text-muted-foreground">
                {r.mantenimiento_origen ? `De ${r.mantenimiento_origen.nombre}` : "Registrada por la administración"}
                {r.responsable && ` · a cargo de ${r.responsable.nombre.replace(/\s*\(.*\)/, "")}`}
                {r.fecha_limite && ` · límite ${fechaCorta(r.fecha_limite)}`}
                {r.costo_estimado && ` · ${pesos(r.costo_estimado)}`}
              </span>
            </span>
            <span className="flex shrink-0 flex-col items-end gap-1">
              <Etiqueta tono={ESTADO_RECOMENDACION[r.estado].tono}>{ESTADO_RECOMENDACION[r.estado].label}</Etiqueta>
              {r.vencida ? (
                <Etiqueta tono="danger">Vencida</Etiqueta>
              ) : (
                <Etiqueta tono={PRIORIDAD_RECOMENDACION[r.prioridad].tono}>{PRIORIDAD_RECOMENDACION[r.prioridad].label}</Etiqueta>
              )}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
