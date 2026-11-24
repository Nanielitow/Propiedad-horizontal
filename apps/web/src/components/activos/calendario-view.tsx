"use client";

import { AlertTriangle, CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Seccion, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { type Actividad, baseActivos, puedeActivos, SEMAFORO } from "@/lib/activos";
import { hoyBogota } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { useRefrescarActivos } from "./comunes";
import { MantenimientoDetalleSheet } from "./detalles";
import { MantenimientoSheet } from "./formulario-mantenimiento";
import { AsignarDialog, ReprogramarDialog } from "./formularios-plan";
import { ActividadFila } from "./hoja-vida-view";

const DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

/** Fechas como "AAAA-MM-DD" con aritmética en UTC (sin saltos por zona horaria). */
function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}
function sumarDias(s: string, n: number) {
  const d = new Date(`${s}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return iso(d);
}

function cuadricula(mes: string) {
  const [y, m] = mes.split("-").map(Number) as [number, number];
  const primero = new Date(Date.UTC(y, m - 1, 1));
  const desfase = (primero.getUTCDay() + 6) % 7; // semana empieza el lunes
  const inicio = sumarDias(iso(primero), -desfase);
  const ultimo = new Date(Date.UTC(y, m, 0));
  const semanas = Math.ceil((desfase + ultimo.getUTCDate()) / 7);
  return { inicio, fin: sumarDias(inicio, semanas * 7 - 1), dias: Array.from({ length: semanas * 7 }, (_, i) => sumarDias(inicio, i)) };
}

function chipClase(x: Actividad) {
  if (x.estado === "EJECUTADA") return "bg-secondary text-muted-foreground line-through decoration-muted-foreground/50";
  if (x.estado === "CANCELADA") return "hidden";
  if (x.semaforo === "ROJO") return "bg-destructive/10 text-destructive";
  if (x.semaforo === "AMARILLO") return "bg-warning-soft text-warning";
  return "bg-success-soft text-success";
}

export function CalendarioView() {
  const { tenant } = useTenant();
  const rol = tenant.role;
  const b = baseActivos(tenant.tenant_id);
  const permitido = puedeActivos(rol, "ver");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const refrescar = useRefrescarActivos();
  const hoy = hoyBogota();
  const mes = params.get("mes") ?? hoy.slice(0, 7);
  const mias = params.get("mias") === "1";
  const [dia, setDia] = useState<string | null>(null);
  const [actividad, setActividad] = useState<Actividad | null>(null);
  const [accion, setAccion] = useState<null | "ejecutar" | "reprogramar" | "asignar">(null);
  const [mto, setMto] = useState<string | null>(null);

  const g = useMemo(() => cuadricula(mes), [mes]);
  const filtro = mias ? "&mias=true" : "";
  const { data, isLoading, mutate } = useSWR<Actividad[]>(permitido ? `${b}/actividades?desde=${g.inicio}&hasta=${g.fin}${filtro}` : null, fetcher, {
    keepPreviousData: true,
  });
  const { data: vencidas } = useSWR<Actividad[]>(permitido ? `${b}/actividades?semaforo=ROJO${filtro}` : null, fetcher);

  const porDia = useMemo(() => {
    const m: Record<string, Actividad[]> = {};
    for (const x of data ?? []) if (x.estado !== "CANCELADA") (m[x.fecha_programada] ??= []).push(x);
    return m;
  }, [data]);

  function setParam(cambios: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    router.replace(`${pathname}?${p}`, { scroll: false });
  }
  function mover(n: number) {
    const [y, m] = mes.split("-").map(Number) as [number, number];
    const d = new Date(Date.UTC(y, m - 1 + n, 1));
    setParam({ mes: iso(d).slice(0, 7) });
    setDia(null);
  }
  function abrir(x: Actividad, a: "ejecutar" | "reprogramar" | "asignar") {
    setActividad(x);
    setAccion(a);
  }
  const actualizar = async () => {
    await mutate();
    await refrescar(tenant.tenant_id);
  };

  if (!permitido) return <SinAcceso />;

  const tituloBase = new Date(`${mes}-15T12:00:00Z`).toLocaleDateString("es-CO", { month: "long", year: "numeric", timeZone: "UTC" });
  const titulo = tituloBase.charAt(0).toUpperCase() + tituloBase.slice(1); // "Noviembre de 2026" (CSS capitalize daría "De")
  const seleccion = dia ? (porDia[dia] ?? []) : [];
  const diasConActividad = g.dias.filter((d) => d.slice(0, 7) === mes && porDia[d]?.length);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Calendario de mantenimiento" description="Las fechas de todos los planes, con su semáforo. Haga clic en un día para actuar." />
      <div className="space-y-4 p-4 sm:p-6">
        {vencidas && vencidas.length > 0 && (
          <Seccion titulo={`${vencidas.length} ${vencidas.length === 1 ? "mantenimiento vencido" : "mantenimientos vencidos"}`} descripcion="Pasó su fecha sin ejecutarse: ejecútelos o reprográmelos." acciones={<AlertTriangle className="size-4 text-destructive" />}>
            <ul className="divide-y">
              {vencidas.slice(0, 5).map((x) => (
                <ActividadFila key={x.id} x={x} rol={rol} mostrarActivo onAccion={(a) => abrir(x, a)} />
              ))}
            </ul>
          </Seccion>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" onClick={() => mover(-1)} aria-label="Mes anterior">
              <ChevronLeft className="size-4" />
            </Button>
            <h2 className="w-44 text-center text-base font-semibold">{titulo}</h2>
            <Button variant="outline" size="icon" onClick={() => mover(1)} aria-label="Mes siguiente">
              <ChevronRight className="size-4" />
            </Button>
            {mes !== hoy.slice(0, 7) && (
              <Button variant="ghost" size="sm" onClick={() => setParam({ mes: null })}>
                Hoy
              </Button>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {(["ROJO", "AMARILLO", "VERDE"] as const).map((c) => (
              <span key={c} className="hidden items-center gap-1 sm:inline-flex">
                <span className={cn("size-2 rounded-full", SEMAFORO[c].punto)} /> {SEMAFORO[c].label}
              </span>
            ))}
            <label className="inline-flex items-center gap-1.5 text-sm text-foreground">
              <input type="checkbox" checked={mias} onChange={(e) => setParam({ mias: e.target.checked ? "1" : null })} className="size-4" />
              Solo las mías
            </label>
          </div>
        </div>

        {isLoading && !data ? (
          <Skeleton className="h-96" />
        ) : (
          <>
            {/* Escritorio: cuadrícula del mes */}
            <div className="hidden overflow-hidden rounded-lg border bg-card md:block">
              <div className="grid grid-cols-7 border-b bg-secondary/40 text-center text-xs font-medium text-muted-foreground">
                {DIAS.map((d) => (
                  <div key={d} className="py-2">
                    {d}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-7">
                {g.dias.map((d) => {
                  const lista = porDia[d] ?? [];
                  const fuera = d.slice(0, 7) !== mes;
                  return (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setDia(d === dia ? null : d)}
                      className={cn(
                        "flex min-h-24 flex-col items-stretch justify-start border-r border-b p-1.5 text-left transition-colors last:border-r-0 hover:bg-accent/40 [&:nth-child(7n)]:border-r-0",
                        fuera && "bg-secondary/30 text-muted-foreground",
                        d === dia && "bg-accent ring-2 ring-primary/30 ring-inset",
                      )}
                      aria-label={`${d}: ${lista.length} actividades`}
                    >
                      <span className={cn("inline-flex size-6 items-center justify-center rounded-full text-xs", d === hoy && "bg-primary font-semibold text-primary-foreground")}>
                        {Number(d.slice(8))}
                      </span>
                      <div className="mt-1 space-y-0.5">
                        {lista.slice(0, 3).map((x) => (
                          <span key={x.id} className={cn("block truncate rounded px-1 py-0.5 text-[11px] font-medium", chipClase(x))} title={`${x.activo.nombre} · ${x.plan.nombre}`}>
                            {x.activo.nombre}
                          </span>
                        ))}
                        {lista.length > 3 && <span className="block px-1 text-[11px] text-muted-foreground">+{lista.length - 3} más</span>}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {dia && (
              <Seccion titulo={new Date(`${dia}T12:00:00Z`).toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" })} className="hidden md:block">
                {seleccion.length === 0 ? (
                  <p className="px-4 py-6 text-sm text-muted-foreground">Sin actividades este día.</p>
                ) : (
                  <ul className="divide-y">
                    {seleccion.map((x) => (
                      <ActividadDia key={x.id} x={x} rol={rol} onAccion={(a) => abrir(x, a)} onVer={setMto} />
                    ))}
                  </ul>
                )}
              </Seccion>
            )}

            {/* Celular: agenda por días */}
            <div className="space-y-3 md:hidden">
              {diasConActividad.length === 0 ? (
                <Vacio icono={CalendarDays} titulo="Sin actividades este mes" />
              ) : (
                diasConActividad.map((d) => (
                  <Seccion key={d} titulo={new Date(`${d}T12:00:00Z`).toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" }) + (d === hoy ? " · hoy" : "")}>
                    <ul className="divide-y">
                      {(porDia[d] ?? []).map((x) => (
                        <ActividadDia key={x.id} x={x} rol={rol} onAccion={(a) => abrir(x, a)} onVer={setMto} />
                      ))}
                    </ul>
                  </Seccion>
                ))
              )}
            </div>
          </>
        )}
      </div>

      <MantenimientoSheet abierto={accion === "ejecutar"} onCambio={(v) => !v && setAccion(null)} actividad={accion === "ejecutar" ? actividad : null} onGuardado={() => void actualizar()} />
      <ReprogramarDialog tenantId={tenant.tenant_id} abierto={accion === "reprogramar"} onCambio={(v) => !v && setAccion(null)} actividad={actividad} onGuardado={() => void actualizar()} />
      <AsignarDialog tenantId={tenant.tenant_id} abierto={accion === "asignar"} onCambio={(v) => !v && setAccion(null)} actividad={actividad} onGuardado={() => void actualizar()} />
      <MantenimientoDetalleSheet id={mto} onCerrar={() => setMto(null)} />
    </div>
  );
}

function ActividadDia({
  x,
  rol,
  onAccion,
  onVer,
}: {
  x: Actividad;
  rol: import("@/lib/types").Role;
  onAccion: (a: "ejecutar" | "reprogramar" | "asignar") => void;
  onVer: (id: string) => void;
}) {
  if (x.estado === "EJECUTADA" && x.mantenimiento_id) {
    return (
      <li>
        <button type="button" onClick={() => onVer(x.mantenimiento_id!)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-accent/40">
          <span className="size-2.5 rounded-full bg-muted-foreground/40" />
          <span className="min-w-0 flex-1 text-sm">
            <span className="font-medium">
              {x.activo_codigo} {x.activo.nombre}
            </span>{" "}
            · {x.plan.nombre}
          </span>
          <span className="text-xs text-success">Ejecutada · ver registro</span>
        </button>
      </li>
    );
  }
  return <ActividadFila x={x} rol={rol} mostrarActivo onAccion={onAccion} />;
}
