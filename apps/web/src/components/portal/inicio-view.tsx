"use client";

import { BellRing, CalendarPlus, ChevronRight, FileCheck2, Home, Inbox, Megaphone, MessageSquarePlus, PiggyBank, Search } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Seccion, SinAcceso } from "@/components/recaudos/comunes";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { basePortal, hora, type InicioResidente } from "@/lib/portal";
import { fechaCorta, pesos } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { EstadoPqrsBadge, EstadoReservaBadge } from "./comunes";

export function InicioView() {
  const { tenant } = useTenant();
  const residente = tenant.role === "RESIDENTE";
  const { data: i } = useSWR<InicioResidente>(residente ? `${basePortal(tenant.tenant_id)}/inicio` : null, fetcher);
  const s = tenant.tenant_slug;

  if (!residente) return <SinAcceso />;
  if (!i) return <div className="space-y-3 p-6"><Skeleton className="h-24" /><Skeleton className="h-64" /></div>;

  const accesos = [
    { href: "mi-portal/pqrs", icono: MessageSquarePlus, titulo: "Radicar una PQRS", texto: "Petición, queja o sugerencia" },
    { href: "mi-portal/reservas", icono: CalendarPlus, titulo: "Reservar", texto: i.zonas_reservables ? `${i.zonas_reservables} zonas disponibles` : "Zonas sociales" },
    { href: "mi-cuenta", icono: PiggyBank, titulo: "Mi cuenta", texto: "Cuotas, pagos y paz y salvo" },
    { href: "search", icono: Search, titulo: "Preguntar", texto: "Reglamento y manual de convivencia" },
  ];

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title={`Hola, ${i.nombre.split(" ")[0]}`} description={i.unidades.length ? `Unidad ${i.unidades.join(", ")} · ${tenant.tenant_name}` : tenant.tenant_name} />
      <div className="mx-auto w-full max-w-5xl space-y-5 p-4 sm:p-6">
        {/* Estado de cuenta */}
        {i.saldo_total !== null && (
          <Link
            href={`/${s}/mi-cuenta`}
            className={cn("flex flex-wrap items-center gap-4 rounded-lg border p-4 transition-colors hover:bg-accent/30", i.al_dia ? "border-success/30 bg-success-soft/30" : "border-destructive/25 bg-destructive/5")}
          >
            <PiggyBank className={cn("size-8 shrink-0", i.al_dia ? "text-success" : "text-destructive")} />
            <div className="min-w-0 flex-1 basis-40">
              <p className="text-sm text-muted-foreground">{i.al_dia ? "Está al día con la administración" : "Tiene un saldo vencido"}</p>
              <p className="text-2xl font-semibold tabular-nums">{pesos(i.al_dia ? i.saldo_total : i.saldo_vencido)}</p>
            </div>
            {/* En celular el enlace baja a su propia línea para no apretar el saldo */}
            <span className="inline-flex w-full items-center gap-1 text-sm font-medium text-primary sm:w-auto">
              {i.al_dia ? (
                <>
                  <FileCheck2 className="size-4" /> Descargar paz y salvo
                </>
              ) : (
                "Ver estado de cuenta"
              )}
              <ChevronRight className="size-4" />
            </span>
          </Link>
        )}

        {/* Circulares sin leer */}
        {i.circulares_sin_leer.length > 0 && (
          <Seccion
            titulo={`Circulares sin leer (${i.circulares_sin_leer.length})`}
            acciones={
              <Link href={`/${s}/mi-portal/circulares`} className="text-sm font-medium text-primary hover:underline">
                Ver todas
              </Link>
            }
          >
            <ul className="divide-y">
              {i.circulares_sin_leer.map((c) => (
                <li key={c.id}>
                  <Link href={`/${s}/mi-portal/circulares`} className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-accent/40">
                    {c.importante ? <BellRing className="size-4 shrink-0 text-warning" /> : <Megaphone className="size-4 shrink-0 text-muted-foreground" />}
                    <span className="min-w-0 flex-1 truncate font-medium">{c.titulo}</span>
                    {c.publicada_at && <span className="text-xs text-muted-foreground">{fechaCorta(c.publicada_at)}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          </Seccion>
        )}

        {/* Accesos rápidos */}
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {accesos.map((a) => (
            <Link key={a.href} href={`/${s}/${a.href}`} className="rounded-lg border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-accent/30">
              <a.icono className="size-5 text-primary" />
              <p className="mt-2 font-medium">{a.titulo}</p>
              <p className="text-xs text-muted-foreground">{a.texto}</p>
            </Link>
          ))}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Seccion
            titulo="Mis PQRS"
            descripcion={i.pqrs_por_calificar ? `${i.pqrs_por_calificar} con respuesta esperando su calificación` : undefined}
            acciones={
              <Link href={`/${s}/mi-portal/pqrs`} className="text-sm font-medium text-primary hover:underline">
                Ver todas
              </Link>
            }
          >
            {!i.pqrs_abiertas.length ? (
              <p className="flex items-center gap-2 px-4 py-4 text-sm text-muted-foreground">
                <Inbox className="size-4" /> No tiene solicitudes en curso.
              </p>
            ) : (
              <ul className="divide-y">
                {i.pqrs_abiertas.map((p) => (
                  <li key={p.id}>
                    <Link href={`/${s}/mi-portal/pqrs/${p.id}`} className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-accent/40">
                      <span className="min-w-0 flex-1 truncate">{p.asunto}</span>
                      <EstadoPqrsBadge estado={p.estado} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Seccion>
          <Seccion
            titulo="Mis próximas reservas"
            acciones={
              <Link href={`/${s}/mi-portal/reservas`} className="text-sm font-medium text-primary hover:underline">
                Reservar
              </Link>
            }
          >
            {!i.proximas_reservas.length ? (
              <p className="flex items-center gap-2 px-4 py-4 text-sm text-muted-foreground">
                <Home className="size-4" /> No tiene reservas próximas.
              </p>
            ) : (
              <ul className="divide-y">
                {i.proximas_reservas.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
                    <span className="font-medium">{r.zona}</span>
                    <span className="text-muted-foreground">
                      {fechaCorta(r.fecha_evento)} · {hora(r.hora_inicio)}–{hora(r.hora_fin)}
                    </span>
                    <span className="ml-auto">
                      <EstadoReservaBadge estado={r.estado} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Seccion>
        </div>
      </div>
    </div>
  );
}
