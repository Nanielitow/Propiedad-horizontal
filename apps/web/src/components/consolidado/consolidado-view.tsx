"use client";

import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarClock,
  FlaskConical,
  Gavel,
  HandCoins,
  MessageSquareWarning,
  RefreshCw,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { AceptarPolitica } from "@/components/auth/aceptar-politica";
import { BotonSalir } from "@/components/auth/boton-salir";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { pesos } from "@/lib/recaudos";
import type { Me } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Copropiedad {
  tenant_id: string;
  nombre: string;
  slug: string;
  is_demo: boolean;
  cartera_configurada: boolean;
  cartera_vencida: string;
  unidades_en_mora: number;
  recaudo_pct: string | null;
  pqrs_abiertas: number;
  pqrs_vencidas: number;
  reservas_por_decidir: number;
  mantenimientos_vencidos: number;
  novedades_criticas: number;
  novedades_sin_atender: number;
  recaudado_mes: string;
  transferencias_por_verificar: number;
  alertas_recaudo: number;
  vencimientos_por_revisar: number;
  vencimientos_proximos: number;
  vencimientos_vencidos: number;
  proxima_asamblea: { id: string; titulo: string; fecha_hora: string; en_curso: boolean } | null;
  errores: string[];
}
interface Resumen {
  generado: string;
  copropiedades: Copropiedad[];
}

/** Puntos de atención: lo vencido o crítico pesa más que lo pendiente. */
function urgencia(c: Copropiedad): number {
  return (
    (c.pqrs_vencidas + c.mantenimientos_vencidos + c.novedades_criticas + c.vencimientos_vencidos) * 3 +
    c.alertas_recaudo +
    c.reservas_por_decidir +
    c.transferencias_por_verificar +
    c.vencimientos_por_revisar
  );
}

type Tono = "peligro" | "atencion" | "ok";

/** Una cifra que lleva a la pantalla donde se atiende. */
function Cifra({
  href,
  valor,
  etiqueta,
  tono,
}: {
  href: string;
  valor: React.ReactNode;
  etiqueta: string;
  tono: Tono;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "block rounded-md px-2 py-1 transition-colors hover:bg-accent",
        tono === "peligro" && "text-destructive",
        tono === "atencion" && "text-warning",
        tono === "ok" && "text-muted-foreground",
      )}
    >
      <span className="block text-sm font-semibold tabular-nums">{valor}</span>
      <span className="block text-[11px] leading-tight">{etiqueta}</span>
    </Link>
  );
}

const tono = (n: number, peligro = false): Tono => (n > 0 ? (peligro ? "peligro" : "atencion") : "ok");

function fechaCorta(iso: string): string {
  return new Date(iso).toLocaleDateString("es-CO", { day: "numeric", month: "short" });
}

function celdas(c: Copropiedad) {
  const b = `/${c.slug}`;
  const vencida = Number(c.cartera_vencida);
  return {
    cartera: (
      <Cifra
        href={`${b}/cartera/morosos`}
        valor={c.cartera_configurada ? pesos(vencida) : "Sin configurar"}
        etiqueta={c.cartera_configurada ? `${c.unidades_en_mora} en mora${c.recaudo_pct ? ` · recaudo ${Number(c.recaudo_pct).toLocaleString("es-CO")} %` : ""}` : "Cartera"}
        tono={!c.cartera_configurada ? "ok" : tono(c.unidades_en_mora)}
      />
    ),
    pqrs: (
      <Cifra
        href={`${b}/portal/pqrs`}
        valor={c.pqrs_vencidas > 0 ? `${c.pqrs_vencidas} vencidas` : c.pqrs_abiertas}
        etiqueta={c.pqrs_vencidas > 0 ? `${c.pqrs_abiertas} abiertas` : "abiertas"}
        tono={c.pqrs_vencidas > 0 ? "peligro" : tono(c.pqrs_abiertas)}
      />
    ),
    reservas: <Cifra href={`${b}/portal/reservas`} valor={c.reservas_por_decidir} etiqueta="por aprobar" tono={tono(c.reservas_por_decidir)} />,
    mantenimiento: (
      <Cifra
        href={c.novedades_criticas > 0 ? `${b}/activos/novedades` : `${b}/activos/calendario`}
        valor={c.novedades_criticas > 0 ? `${c.novedades_criticas} crítica${c.novedades_criticas > 1 ? "s" : ""}` : c.mantenimientos_vencidos}
        etiqueta={c.novedades_criticas > 0 ? `${c.mantenimientos_vencidos} vencidos` : "vencidos"}
        tono={c.novedades_criticas > 0 || c.mantenimientos_vencidos > 0 ? "peligro" : "ok"}
      />
    ),
    recaudos: (
      <Cifra
        href={c.alertas_recaudo > 0 ? `${b}/recaudos/alertas` : `${b}/recaudos/conciliacion`}
        valor={c.alertas_recaudo > 0 ? `${c.alertas_recaudo} alertas` : c.transferencias_por_verificar}
        etiqueta={c.alertas_recaudo > 0 ? `${c.transferencias_por_verificar} por verificar` : "por verificar"}
        tono={tono(c.alertas_recaudo + c.transferencias_por_verificar)}
      />
    ),
    vencimientos: (
      <Cifra
        href={`${b}/deadlines`}
        valor={c.vencimientos_vencidos > 0 ? `${c.vencimientos_vencidos} vencidos` : c.vencimientos_proximos}
        etiqueta={c.vencimientos_por_revisar > 0 ? `${c.vencimientos_por_revisar} por revisar` : "en 30 días"}
        tono={c.vencimientos_vencidos > 0 ? "peligro" : tono(c.vencimientos_proximos + c.vencimientos_por_revisar)}
      />
    ),
    asamblea: c.proxima_asamblea ? (
      <Cifra
        href={`${b}/asambleas/${c.proxima_asamblea.id}`}
        valor={c.proxima_asamblea.en_curso ? "En curso" : fechaCorta(c.proxima_asamblea.fecha_hora)}
        etiqueta={c.proxima_asamblea.titulo}
        tono={c.proxima_asamblea.en_curso ? "atencion" : "ok"}
      />
    ) : (
      <span className="block px-2 py-1 text-[11px] text-muted-foreground">Sin programar</span>
    ),
  };
}

function Total({ icono: Icono, titulo, valor, detalle, alerta }: { icono: React.ComponentType<{ className?: string }>; titulo: string; valor: string; detalle: string; alerta: boolean }) {
  return (
    <div className={cn("rounded-lg border bg-card p-4", alerta && "border-destructive/25 bg-destructive/5")}>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Icono className={cn("size-4", alerta && "text-destructive")} />
        {titulo}
      </div>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums", alerta && "text-destructive")}>{valor}</p>
      <p className="text-xs text-muted-foreground">{detalle}</p>
    </div>
  );
}

export function ConsolidadoView({ me }: { me: Me }) {
  const { data, isLoading, mutate, isValidating } = useSWR<Resumen>("/mis-copropiedades/resumen", fetcher, {
    refreshInterval: 300_000,
  });
  const [orden, setOrden] = useState<"urgencia" | "nombre">("urgencia");
  const filas = useMemo(() => {
    const l = [...(data?.copropiedades ?? [])];
    return orden === "urgencia" ? l.sort((a, b) => urgencia(b) - urgencia(a) || a.nombre.localeCompare(b.nombre)) : l;
  }, [data, orden]);

  const t = useMemo(() => {
    const c = data?.copropiedades ?? [];
    const s = (f: (x: Copropiedad) => number) => c.reduce((a, x) => a + f(x), 0);
    return {
      vencida: s((x) => Number(x.cartera_vencida)),
      mora: s((x) => x.unidades_en_mora),
      pqrsVencidas: s((x) => x.pqrs_vencidas),
      pqrsAbiertas: s((x) => x.pqrs_abiertas),
      mto: s((x) => x.mantenimientos_vencidos),
      criticas: s((x) => x.novedades_criticas),
      alertas: s((x) => x.alertas_recaudo),
      porVerificar: s((x) => x.transferencias_por_verificar),
      atender: c.filter((x) => urgencia(x) > 0).length,
    };
  }, [data]);

  return (
    <div className="min-h-dvh bg-background">
      <AceptarPolitica requiere={me.user.requiere_politica} />
      <header className="flex items-center gap-3 bg-sidebar px-4 py-3 text-sidebar-foreground sm:px-6">
        <div className="flex size-8 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
          <Building2 className="size-4.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold tracking-tight text-white">Mis copropiedades</p>
          <p className="truncate text-xs text-sidebar-muted">{me.user.full_name}</p>
        </div>
        {me.user.is_platform_admin && (
          <Button asChild variant="ghost" className="hidden text-sidebar-foreground hover:bg-sidebar-accent hover:text-white sm:inline-flex">
            <Link href="/plataforma">Plataforma</Link>
          </Button>
        )}
        <BotonSalir variant="ghost" className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-white" />
      </header>

      <main className="mx-auto max-w-7xl p-4 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Resumen de todas sus copropiedades</h1>
            <p className="text-sm text-muted-foreground">
              {data
                ? `${data.copropiedades.length} copropiedades · ${t.atender} con pendientes · actualizado a las ${new Date(data.generado).toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" })}`
                : "Cargando…"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-md border bg-card p-0.5 text-sm" role="group" aria-label="Orden">
              {(["urgencia", "nombre"] as const).map((o) => (
                <button
                  key={o}
                  type="button"
                  onClick={() => setOrden(o)}
                  className={cn("rounded px-2.5 py-1", orden === o ? "bg-accent font-medium text-foreground" : "text-muted-foreground")}
                >
                  {o === "urgencia" ? "Lo urgente primero" : "Por nombre"}
                </button>
              ))}
            </div>
            <Button variant="outline" size="icon" onClick={() => void mutate()} aria-label="Actualizar" disabled={isValidating}>
              <RefreshCw className={cn("size-4", isValidating && "animate-spin")} />
            </Button>
          </div>
        </div>

        {/* Totales */}
        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Total icono={HandCoins} titulo="Cartera vencida" valor={pesos(t.vencida)} detalle={`${t.mora} unidades en mora`} alerta={false} />
          <Total icono={MessageSquareWarning} titulo="PQRS vencidas" valor={String(t.pqrsVencidas)} detalle={`${t.pqrsAbiertas} abiertas en total`} alerta={t.pqrsVencidas > 0} />
          <Total icono={Wrench} titulo="Mantenimiento" valor={`${t.mto} vencidos`} detalle={t.criticas === 1 ? "1 falla crítica abierta" : `${t.criticas} fallas críticas abiertas`} alerta={t.mto + t.criticas > 0} />
          <Total icono={AlertTriangle} titulo="Alertas de caja" valor={String(t.alertas)} detalle={t.porVerificar === 1 ? "1 transferencia por verificar" : `${t.porVerificar} transferencias por verificar`} alerta={t.alertas > 0} />
        </div>

        {/* Escritorio: tabla */}
        <div className="mt-5 hidden overflow-x-auto rounded-lg border bg-card lg:block">
          <table className="w-full text-left">
            <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">Copropiedad</th>
                <th className="px-2 py-2.5 font-medium">Cartera vencida</th>
                <th className="px-2 py-2.5 font-medium">PQRS</th>
                <th className="px-2 py-2.5 font-medium">Reservas</th>
                <th className="px-2 py-2.5 font-medium">Mantenimiento</th>
                <th className="px-2 py-2.5 font-medium">Recaudos</th>
                <th className="px-2 py-2.5 font-medium">Vencimientos</th>
                <th className="px-2 py-2.5 font-medium">Asamblea</th>
              </tr>
            </thead>
            <tbody>
              {isLoading &&
                Array.from({ length: 3 }, (_, i) => (
                  <tr key={i}>
                    <td colSpan={8} className="px-4 py-3">
                      <Skeleton className="h-10 w-full" />
                    </td>
                  </tr>
                ))}
              {filas.map((c) => {
                const x = celdas(c);
                return (
                  <tr key={c.tenant_id} className="border-b align-top last:border-b-0">
                    <td className="px-4 py-3">
                      <Link href={`/${c.slug}`} className="group flex items-center gap-1.5 font-medium hover:text-primary">
                        {c.nombre}
                        <ArrowRight className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                      </Link>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                        {urgencia(c) === 0 ? (
                          <span className="inline-flex items-center gap-1 text-success">
                            <ShieldCheck className="size-3" /> Sin pendientes
                          </span>
                        ) : (
                          <span>Recaudo extra del mes: {pesos(c.recaudado_mes)}</span>
                        )}
                        {c.is_demo && (
                          <span className="inline-flex items-center gap-1 text-warning">
                            <FlaskConical className="size-3" /> Demo
                          </span>
                        )}
                        {c.errores.length > 0 && <span className="text-destructive">No se pudo leer: {c.errores.join(", ")}</span>}
                      </div>
                    </td>
                    <td className="px-1 py-2">{x.cartera}</td>
                    <td className="px-1 py-2">{x.pqrs}</td>
                    <td className="px-1 py-2">{x.reservas}</td>
                    <td className="px-1 py-2">{x.mantenimiento}</td>
                    <td className="px-1 py-2">{x.recaudos}</td>
                    <td className="px-1 py-2">{x.vencimientos}</td>
                    <td className="max-w-40 px-1 py-2">{x.asamblea}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Celular y tableta: tarjetas */}
        <div className="mt-5 space-y-3 lg:hidden">
          {isLoading && <Skeleton className="h-40 w-full" />}
          {filas.map((c) => {
            const x = celdas(c);
            return (
              <div key={c.tenant_id} className="rounded-lg border bg-card p-3">
                <div className="flex items-center justify-between gap-2">
                  <Link href={`/${c.slug}`} className="font-medium">
                    {c.nombre}
                  </Link>
                  <Button asChild size="sm" variant="ghost">
                    <Link href={`/${c.slug}`}>
                      Entrar <ArrowRight className="size-4" />
                    </Link>
                  </Button>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-1 sm:grid-cols-3">
                  {[
                    ["Cartera", x.cartera, HandCoins],
                    ["PQRS", x.pqrs, MessageSquareWarning],
                    ["Reservas", x.reservas, CalendarClock],
                    ["Mantenimiento", x.mantenimiento, Wrench],
                    ["Recaudos", x.recaudos, AlertTriangle],
                    ["Vencimientos", x.vencimientos, CalendarClock],
                    ["Asamblea", x.asamblea, Gavel],
                  ].map(([titulo, nodo]) => (
                    <div key={titulo as string} className="rounded-md bg-muted/40 p-1">
                      <p className="px-2 pt-1 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">{titulo as string}</p>
                      {nodo as React.ReactNode}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {data && data.copropiedades.length === 0 && (
          <p className="mt-8 text-center text-sm text-muted-foreground">
            Este resumen es para quien administra copropiedades. Usted no es administrador(a) en ninguna.
          </p>
        )}
        <p className="mt-4 text-xs text-muted-foreground">
          Toque cualquier cifra para ir a esa pantalla de la copropiedad. Rojo: vencido o crítico · amarillo: pendiente. Se actualiza
          cada 5 minutos.
        </p>
      </main>
    </div>
  );
}
