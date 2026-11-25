"use client";

import { ArrowLeft, Building, Download, FileSpreadsheet, HandCoins, MoreHorizontal, Printer, Undo2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Etiqueta, MotivoDialog, Seccion, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, fetcher } from "@/lib/api";
import { baseCartera, type EstadoCuenta, puedeCartera, RANGO, RANGOS_VENCIDOS } from "@/lib/cartera";
import { fechaCorta, pesos } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { MoraBadge, PazYSalvoBoton, RegistrarPagoDialog, useRefrescarCartera } from "./comunes";

/** Contenido del estado de cuenta (lo usan la vista del personal y «Mi cuenta» del residente). */
export function EstadoCuentaContenido({ e, onCambio }: { e: EstadoCuenta; onCambio?: () => void }) {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const [anular, setAnular] = useState<{ id: string; consecutivo: number } | null>(null);
  const puedeAnular = puedeCartera(tenant.role, "anular");
  const vencidas = RANGOS_VENCIDOS.filter((k) => Number(e.edades[k]) > 0);

  return (
    <div className="space-y-4">
      <div className={cn("rounded-lg border p-4", e.al_dia ? "border-success/30 bg-success-soft/30" : "border-destructive/25 bg-destructive/5")}>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm text-muted-foreground">{e.al_dia ? "Saldo total" : "Saldo vencido"}</p>
            <p className="text-3xl font-semibold tracking-tight tabular-nums">{pesos(e.al_dia ? e.saldo_total : e.saldo_vencido)}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {e.al_dia ? (Number(e.saldo_total) > 0 ? "Al día: lo pendiente aún no vence" : "Al día, sin saldo pendiente") : `Total por pagar ${pesos(e.saldo_total)}`}
              {Number(e.saldo_a_favor) > 0 && ` · saldo a favor ${pesos(e.saldo_a_favor)}`}
            </p>
          </div>
          <div className="text-sm sm:text-right">
            <MoraBadge dias={e.dias_mora} />
            <p className="mt-1 text-muted-foreground">Último pago: {e.ultimo_pago ? fechaCorta(e.ultimo_pago) : "—"}</p>
          </div>
        </div>
        {vencidas.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {vencidas.map((k) => (
              <Etiqueta key={k} tono={RANGO[k].tono}>
                {RANGO[k].label}: {pesos(e.edades[k])}
              </Etiqueta>
            ))}
          </div>
        )}
      </div>

      <Seccion titulo="Pendiente por pagar" descripcion="Los pagos se aplican primero a intereses y luego a lo más antiguo (art. 1653 del Código Civil).">
        {!e.pendientes.length ? (
          <p className="px-4 py-3 text-sm text-muted-foreground">No hay saldos pendientes.</p>
        ) : (
          <ul className="divide-y">
            {e.pendientes.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
                <span className="min-w-0 flex-1">
                  <span className="block">{c.descripcion}</span>
                  <span className="text-xs text-muted-foreground">
                    Vence {fechaCorta(c.fecha_vencimiento)}
                    {c.saldo !== c.valor && ` · valor ${pesos(c.valor)}, abonado ${pesos(Number(c.valor) - Number(c.saldo))}`}
                  </span>
                </span>
                {c.dias_mora > 0 && <span className="text-xs text-destructive">{c.dias_mora} días</span>}
                <span className="w-28 text-right font-medium tabular-nums">{pesos(c.saldo)}</span>
              </li>
            ))}
          </ul>
        )}
      </Seccion>

      <Seccion titulo="Movimientos" descripcion="Cargos, pagos y ajustes con el saldo acumulado. Los anulados se muestran tachados y no suman.">
        {!e.movimientos.length ? (
          <Vacio icono={Building} titulo="Sin movimientos" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="bg-muted/60 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Fecha</th>
                  <th className="px-2 py-2 text-left font-medium">Detalle</th>
                  <th className="px-2 py-2 text-right font-medium">Cargo</th>
                  <th className="px-2 py-2 text-right font-medium">Abono</th>
                  <th className="px-4 py-2 text-right font-medium">Saldo</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {[...e.movimientos].reverse().map((m) => (
                  <tr key={`${m.tipo}-${m.referencia_id}`} className={cn(m.anulado && "text-muted-foreground line-through")}>
                    <td className="px-4 py-2 whitespace-nowrap">{fechaCorta(m.fecha)}</td>
                    <td className="px-2 py-2">
                      <span className="inline-flex items-center gap-1">
                        {m.descripcion}
                        {m.tipo === "PAGO" && !m.anulado && (
                          <span className="inline-flex no-underline">
                            <a href={`/api/proxy${b}/pagos/${m.referencia_id}/recibo.pdf`} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" title="Recibo en PDF">
                              <Printer className="size-3.5" />
                            </a>
                            {puedeAnular && m.consecutivo && (
                              <button type="button" onClick={() => setAnular({ id: m.referencia_id, consecutivo: m.consecutivo! })} className="ml-1 text-muted-foreground hover:text-destructive" title="Anular pago">
                                <Undo2 className="size-3.5" />
                              </button>
                            )}
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums">{Number(m.cargo) ? pesos(m.cargo) : ""}</td>
                    <td className="px-2 py-2 text-right text-success tabular-nums">{Number(m.abono) ? pesos(m.abono) : ""}</td>
                    <td className="px-4 py-2 text-right font-medium tabular-nums">{pesos(m.saldo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Seccion>

      <MotivoDialog
        abierto={!!anular}
        onCambio={(v) => !v && setAnular(null)}
        titulo={`Anular el recibo ${anular?.consecutivo ?? ""}`}
        descripcion="El pago deja de contar y los cargos recuperan su saldo (también se pierde el descuento por pronto pago, si lo hubo). Queda en la auditoría."
        boton="Anular pago"
        onConfirmar={async (motivo) => {
          if (!anular) return;
          await api(`${b}/pagos/${anular.id}/anular`, { method: "POST", json: { motivo } });
          toast.success(`Recibo ${anular.consecutivo} anulado`);
          onCambio?.();
        }}
      />
    </div>
  );
}

export function EstadoCuentaView({ unidadId }: { unidadId: string }) {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const url = `${b}/unidades/${unidadId}/estado-cuenta`;
  const { data: e, error, mutate } = useSWR<EstadoCuenta>(puedeCartera(tenant.role, "ver") ? url : null, fetcher);
  const refrescar = useRefrescarCartera();
  const [pago, setPago] = useState(false);

  if (!puedeCartera(tenant.role, "ver")) return <SinAcceso />;
  if (error instanceof ApiError && error.status === 404) return <SinAcceso texto="La unidad no existe" />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title={e ? `Estado de cuenta ${e.unidad}` : "Estado de cuenta"}
        description={e?.responsable ? `Responsable de pago: ${e.responsable}` : undefined}
        actions={
          <>
            <Button variant="ghost" size="icon" asChild aria-label="Volver">
              <Link href={`/${tenant.tenant_slug}/cartera/morosos`}>
                <ArrowLeft className="size-4" />
              </Link>
            </Button>
            {e && puedeCartera(tenant.role, "pazYSalvo") && <PazYSalvoBoton tenantId={tenant.tenant_id} unidadId={unidadId} alDia={e.al_dia} />}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" aria-label="Descargar">
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem asChild>
                  <a href={`/api/proxy${url}?formato=pdf`} download>
                    <Download className="size-4" /> Estado de cuenta en PDF
                  </a>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <a href={`/api/proxy${url}?formato=xlsx`} download>
                    <FileSpreadsheet className="size-4" /> En Excel
                  </a>
                </DropdownMenuItem>
                <DropdownMenuItem asChild>
                  <Link href={`/${tenant.tenant_slug}/unidades/${unidadId}`}>
                    <Building className="size-4" /> Ficha de la unidad
                  </Link>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {puedeCartera(tenant.role, "registrarPago") && (
              <Button onClick={() => setPago(true)}>
                <HandCoins className="size-4" /> <span className="hidden sm:inline">Registrar pago</span>
              </Button>
            )}
          </>
        }
      />
      <div className="mx-auto w-full max-w-5xl p-4 sm:p-6">
        {!e ? (
          <Skeleton className="h-96" />
        ) : (
          <EstadoCuentaContenido
            e={e}
            onCambio={() => {
              void mutate();
              void refrescar(tenant.tenant_id);
            }}
          />
        )}
      </div>
      <RegistrarPagoDialog
        tenantId={tenant.tenant_id}
        abierto={pago}
        onCambio={setPago}
        unidadId={unidadId}
        saldoSugerido={e?.saldo_vencido !== "0.00" ? e?.saldo_vencido : e?.saldo_total}
        onRegistrado={() => {
          void mutate();
          void refrescar(tenant.tenant_id);
        }}
      />
    </div>
  );
}
