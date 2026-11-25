"use client";

import { AlertTriangle, CalendarPlus, HandCoins, Settings2, Users, Wallet } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Etiqueta, Kpi, Seccion, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { baseCartera, puedeCartera, type ResumenCartera } from "@/lib/cartera";
import { fechaCorta, pesos } from "@/lib/recaudos";

import { BarrasEdades, FacturarDialog, GraficoRecaudo, RegistrarPagoDialog, useRefrescarCartera } from "./comunes";

export function PanelCarteraView() {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const permitido = puedeCartera(tenant.role, "ver");
  const { data: r } = useSWR<ResumenCartera>(permitido ? `${b}/resumen` : null, fetcher);
  const refrescar = useRefrescarCartera();
  const [facturar, setFacturar] = useState(false);
  const [pago, setPago] = useState(false);

  if (!permitido) return <SinAcceso />;
  const slug = tenant.tenant_slug;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Cartera"
        description="Cuotas de administración: lo facturado, lo recaudado y quién está en mora."
        actions={
          <>
            {puedeCartera(tenant.role, "facturar") && r?.configurada && (
              <Button variant="outline" onClick={() => setFacturar(true)} className="hidden sm:inline-flex">
                <CalendarPlus className="size-4" /> Facturar mes
              </Button>
            )}
            {puedeCartera(tenant.role, "registrarPago") && r?.configurada && (
              <Button onClick={() => setPago(true)}>
                <HandCoins className="size-4" /> Registrar pago
              </Button>
            )}
          </>
        }
      />

      <div className="space-y-4 p-4 sm:p-6">
        {!r ? (
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : !r.configurada ? (
          <div className="rounded-lg border bg-card">
            <Vacio icono={Settings2} titulo="La cartera aún no está configurada" texto="Defina cómo se calcula la cuota (por coeficiente o por tarifa), el día de vencimiento, el descuento y los intereses de mora." />
            {puedeCartera(tenant.role, "configurar") && (
              <div className="pb-8 text-center">
                <Button asChild>
                  <Link href={`/${slug}/cartera/configuracion`}>Configurar ahora</Link>
                </Button>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
              <Kpi titulo="Cartera vencida" icono={AlertTriangle} valor={pesos(r.cartera_vencida)} destacado={Number(r.cartera_vencida) > 0} detalle={`De ${pesos(r.cartera_total)} por cobrar`} />
              <Kpi
                titulo="Recaudo del mes"
                icono={Wallet}
                valor={r.recaudo_pct !== null ? `${Number(r.recaudo_pct).toLocaleString("es-CO")} %` : "—"}
                detalle={r.facturado_mes !== "0" ? `${pesos(r.recaudado_mes)} recibidos · ${pesos(r.facturado_mes)} facturados` : "Aún no se factura este mes"}
              />
              <Kpi
                titulo="Unidades en mora"
                icono={Users}
                valor={String(r.unidades_en_mora)}
                destacado={r.unidades_en_mora > 0}
                detalle={
                  <Link href={`/${slug}/cartera/morosos`} className="font-medium text-primary hover:underline">
                    {r.unidades_al_dia} al día · ver morosos
                  </Link>
                }
              />
              <Kpi titulo="Saldos a favor" valor={pesos(r.saldo_a_favor)} detalle="Anticipos que cubrirán las próximas cuotas" />
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
              <Seccion titulo="Facturado vs. recaudado" descripcion="Últimos 12 meses. El recaudo incluye pagos de deudas atrasadas.">
                <div className="p-4">
                  <GraficoRecaudo serie={r.recaudo_mensual} />
                </div>
              </Seccion>
              <Seccion titulo="Cartera por antigüedad" descripcion="Saldo pendiente según los días de mora.">
                <div className="p-4">
                  <BarrasEdades edades={r.edades} total={Number(r.cartera_total)} />
                </div>
              </Seccion>
            </div>

            <Seccion
              titulo="Periodos facturados"
              acciones={
                <Button variant="ghost" size="sm" asChild>
                  <Link href={`/${slug}/cartera/periodos`}>Ver todos</Link>
                </Button>
              }
            >
              {!r.ultimos_periodos.length ? (
                <Vacio icono={CalendarPlus} titulo="Aún no se ha facturado ningún mes" />
              ) : (
                <ul className="divide-y">
                  {r.ultimos_periodos.map((p) => {
                    const total = Number(p.total_cuotas) + Number(p.total_intereses);
                    const pct = total ? Math.round((Number(p.recaudado) / total) * 100) : 0;
                    return (
                      <li key={p.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
                        <span className="w-36 font-medium">{p.nombre}</span>
                        {p.estado === "ANULADO" ? (
                          <Etiqueta tono="danger">Anulado</Etiqueta>
                        ) : (
                          <>
                            <span className="text-muted-foreground">Vence {fechaCorta(p.fecha_vencimiento)}</span>
                            <span className="tabular-nums">{pesos(total)}</span>
                            <span className="flex min-w-40 flex-1 items-center gap-2">
                              <span className="h-1.5 flex-1 rounded-full bg-secondary">
                                <span className="block h-1.5 rounded-full bg-primary/80" style={{ width: `${Math.min(100, pct)}%` }} />
                              </span>
                              <span className="w-10 text-right text-xs text-muted-foreground tabular-nums">{pct} %</span>
                            </span>
                          </>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </Seccion>
          </>
        )}
      </div>

      <FacturarDialog tenantId={tenant.tenant_id} abierto={facturar} onCambio={setFacturar} onEmitido={() => refrescar(tenant.tenant_id)} />
      <RegistrarPagoDialog tenantId={tenant.tenant_id} abierto={pago} onCambio={setPago} onRegistrado={() => refrescar(tenant.tenant_id)} />
    </div>
  );
}
