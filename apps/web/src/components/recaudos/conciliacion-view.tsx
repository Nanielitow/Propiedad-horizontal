"use client";

import { Banknote, CheckCircle2, ChevronDown, ExternalLink, Landmark, Loader2, ShieldCheck, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import {
  base,
  type Consignacion,
  type ConsignacionDetalle,
  ESTADO_CONSIGNACION,
  fechaCorta,
  fechaHora,
  hoyBogota,
  type Pendiente,
  pesos,
  puede,
} from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { campoClase, EstadoBadge, Etiqueta, mensajeError, MotivoDialog, Seccion, SinAcceso, SoporteInput, Vacio } from "./comunes";

const BANCOS = ["Bancolombia", "Banco de Bogotá", "Davivienda", "BBVA", "Banco de Occidente", "Banco Caja Social", "Banco Agrario", "Otro"];

function RegistrarDialog({
  seleccion,
  abierto,
  onCambio,
  onRegistrada,
}: {
  seleccion: Pendiente[];
  abierto: boolean;
  onCambio: (v: boolean) => void;
  onRegistrada: () => void;
}) {
  const { tenant } = useTenant();
  const [fecha, setFecha] = useState(hoyBogota());
  const [banco, setBanco] = useState("Bancolombia");
  const [referencia, setReferencia] = useState("");
  const [valor, setValor] = useState("");
  const [soporte, setSoporte] = useState<string | null>(null);
  // Valor aplicado por recaudo (vacío = todo su saldo)
  const [parciales, setParciales] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);

  const aplicado = seleccion.reduce((s, p) => s + Number(parciales[p.recaudo.id] || p.saldo), 0);
  const consignado = valor === "" ? aplicado : Number(valor);
  const descuadre = consignado - aplicado;

  async function registrar() {
    setEnviando(true);
    try {
      const c = await api<ConsignacionDetalle>(`${base(tenant.tenant_id)}/consignaciones`, {
        method: "POST",
        json: {
          fecha_consignacion: fecha,
          banco_destino: banco,
          referencia_bancaria: referencia.trim(),
          valor_consignado: String(consignado),
          soporte_bancario_key: soporte,
          aplicaciones: seleccion.map((p) => ({ recaudo_id: p.recaudo.id, valor_aplicado: parciales[p.recaudo.id] || null })),
        },
      });
      toast.success(
        descuadre === 0
          ? `Consignación #${c.consecutivo} registrada: queda por aprobar`
          : `Consignación #${c.consecutivo} registrada con descuadre; se generó una alerta`,
      );
      onRegistrada();
      onCambio(false);
      setReferencia("");
      setValor("");
      setSoporte(null);
      setParciales({});
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Registrar consignación</DialogTitle>
          <DialogDescription>
            {seleccion.length} recaudos seleccionados. Para consignar solo una parte de alguno, escriba el valor en su fila.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="c-fecha">Fecha</Label>
            <input id="c-fecha" type="date" value={fecha} max={hoyBogota()} onChange={(e) => setFecha(e.target.value)} className={campoClase()} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="c-banco">Banco</Label>
            <select id="c-banco" value={banco} onChange={(e) => setBanco(e.target.value)} className={campoClase()}>
              {BANCOS.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="c-ref">Referencia</Label>
            <Input id="c-ref" value={referencia} onChange={(e) => setReferencia(e.target.value)} placeholder="N.° del comprobante" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="c-valor">Valor consignado</Label>
            <Input id="c-valor" inputMode="numeric" value={valor} placeholder={String(aplicado)} onChange={(e) => setValor(e.target.value.replace(/\D/g, ""))} />
          </div>
        </div>
        <div className="max-h-56 overflow-y-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-secondary text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-1.5 text-left font-medium">Recaudo</th>
                <th className="px-3 py-1.5 text-right font-medium">Saldo</th>
                <th className="w-36 px-3 py-1.5 text-right font-medium">A consignar</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {seleccion.map((p) => (
                <tr key={p.recaudo.id}>
                  <td className="px-3 py-1.5">
                    #{p.recaudo.consecutivo} · {p.recaudo.concepto}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{pesos(p.saldo)}</td>
                  <td className="px-3 py-1">
                    <Input
                      inputMode="numeric"
                      className="h-7 text-right"
                      placeholder={String(Number(p.saldo))}
                      value={parciales[p.recaudo.id] ?? ""}
                      onChange={(e) => setParciales((x) => ({ ...x, [p.recaudo.id]: e.target.value.replace(/\D/g, "") }))}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <SoporteInput tenantId={tenant.tenant_id} valor={soporte} onCambio={setSoporte} />
          <p className={cn("self-center text-sm", descuadre === 0 ? "text-muted-foreground" : "text-destructive")}>
            Recaudos: <span className="font-medium tabular-nums">{pesos(aplicado)}</span>
            {descuadre !== 0 && ` · descuadre de ${pesos(Math.abs(descuadre))}: se generará una alerta`}
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={referencia.trim().length < 3 || consignado <= 0 || enviando} onClick={registrar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Registrar consignación
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DetalleConsignacion({ id }: { id: string }) {
  const { tenant } = useTenant();
  const { data } = useSWR<ConsignacionDetalle>(`${base(tenant.tenant_id)}/consignaciones/${id}`, fetcher);
  if (!data) return <Skeleton className="m-3 h-16" />;
  return (
    <div className="space-y-2 bg-secondary/30 px-4 py-3 text-sm">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        <span>Registró: {data.usuario_consigna.replace(/\s*\(.*\)/, "")}</span>
        {data.aprobada_por && <span>Aprobó: {data.aprobada_por.replace(/\s*\(.*\)/, "")} · {data.aprobada_at && fechaHora(data.aprobada_at)}</span>}
        {data.verificada_por && <span>Verificó: {data.verificada_por.replace(/\s*\(.*\)/, "")} · {data.verificada_at && fechaHora(data.verificada_at)}</span>}
        {data.soporte_url && (
          <a href={data.soporte_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
            <ExternalLink className="size-3" /> Comprobante del banco
          </a>
        )}
      </div>
      <ul className="divide-y rounded-md border bg-card">
        {data.aplicaciones.map((a) => (
          <li key={a.recaudo.id} className="flex items-center justify-between gap-2 px-3 py-1.5">
            <span className="truncate">
              #{a.recaudo.consecutivo} · {a.recaudo.concepto} · {a.recaudo.nombre_pagador}
            </span>
            <span className="flex items-center gap-2">
              <span className="tabular-nums">{pesos(a.valor_aplicado)}</span>
              <EstadoBadge estado={a.recaudo.estado} />
            </span>
          </li>
        ))}
      </ul>
      {data.observaciones && <p className="text-xs whitespace-pre-line text-muted-foreground">{data.observaciones}</p>}
    </div>
  );
}

export function ConciliacionView() {
  const { tenant } = useTenant();
  const b = base(tenant.tenant_id);
  const permitido = puede(tenant.role, "conciliacion");
  const aprueba = puede(tenant.role, "aprobar");
  const registra = tenant.role === "ADMIN" || tenant.role === "AUXILIAR";
  const { data: pendientes, mutate: refrescarPendientes } = useSWR<Pendiente[]>(registra ? `${b}/consignaciones/pendientes` : null, fetcher);
  const { data: consignaciones, mutate: refrescarConsignaciones } = useSWR<Consignacion[]>(permitido ? `${b}/consignaciones` : null, fetcher);
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set());
  const [registrando, setRegistrando] = useState(false);
  const [expandida, setExpandida] = useState<string | null>(null);
  const [rechazando, setRechazando] = useState<Consignacion | null>(null);
  const [trabajando, setTrabajando] = useState<string | null>(null);

  const elegidos = useMemo(() => pendientes?.filter((p) => seleccion.has(p.recaudo.id)) ?? [], [pendientes, seleccion]);
  const totalPendiente = pendientes?.reduce((s, p) => s + Number(p.saldo), 0) ?? 0;

  function refrescar() {
    setSeleccion(new Set());
    void refrescarPendientes();
    void refrescarConsignaciones();
  }

  async function accion(c: Consignacion, que: "aprobar" | "verificar") {
    setTrabajando(c.id);
    try {
      const r = await api<{ recaudos_actualizados: string[] }>(`${b}/consignaciones/${c.id}/${que}`, { method: "POST" });
      const n = r.recaudos_actualizados.length;
      toast.success(
        que === "aprobar"
          ? `Consignación #${c.consecutivo} aprobada: ${n} recaudos pasan a consignados`
          : `Consignación #${c.consecutivo} verificada: ${n} recaudos conciliados`,
      );
      refrescar();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setTrabajando(null);
    }
  }

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Conciliación bancaria" description="Del efectivo en caja al banco: consignaciones, aprobación y verificación contra el extracto." />

      <div className="space-y-6 p-4 sm:p-6">
        {registra && (
          <Seccion
            titulo="Efectivo por consignar"
            descripcion={pendientes ? `${pendientes.length} recaudos · ${pesos(totalPendiente)}` : undefined}
            acciones={
              <Button size="sm" disabled={!elegidos.length} onClick={() => setRegistrando(true)}>
                <Landmark className="size-4" /> Consignar {elegidos.length ? `(${elegidos.length})` : ""}
              </Button>
            }
          >
            {!pendientes ? (
              <Skeleton className="m-4 h-24" />
            ) : !pendientes.length ? (
              <Vacio icono={Banknote} titulo="No hay efectivo pendiente de consignar" texto="El efectivo aparece aquí después de su cierre de caja." />
            ) : (
              <div className="max-h-80 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-card text-xs text-muted-foreground">
                    <tr className="border-b">
                      <th className="w-10 py-2 pl-4 text-left">
                        <input
                          type="checkbox"
                          aria-label="Seleccionar todos"
                          checked={seleccion.size === pendientes.length}
                          onChange={(e) => setSeleccion(e.target.checked ? new Set(pendientes.map((p) => p.recaudo.id)) : new Set())}
                        />
                      </th>
                      <th className="py-2 text-left font-medium">Recaudo</th>
                      <th className="hidden py-2 text-left font-medium md:table-cell">Recibió</th>
                      <th className="py-2 text-left font-medium">Estado</th>
                      <th className="py-2 pr-4 text-right font-medium">Saldo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {pendientes.map((p) => (
                      <tr key={p.recaudo.id} className="hover:bg-accent/30">
                        <td className="py-2 pl-4">
                          <input
                            type="checkbox"
                            aria-label={`Seleccionar recaudo ${p.recaudo.consecutivo}`}
                            checked={seleccion.has(p.recaudo.id)}
                            onChange={(e) =>
                              setSeleccion((s) => {
                                const n = new Set(s);
                                if (e.target.checked) n.add(p.recaudo.id);
                                else n.delete(p.recaudo.id);
                                return n;
                              })
                            }
                          />
                        </td>
                        <td className="py-2">
                          #{p.recaudo.consecutivo} · {p.recaudo.concepto}
                          <span className="block text-xs text-muted-foreground">{fechaHora(p.recaudo.fecha_recaudo)}</span>
                        </td>
                        <td className="hidden py-2 md:table-cell">{p.recaudo.receptor.replace(/\s*\(.*\)/, "")}</td>
                        <td className="py-2">
                          <EstadoBadge estado={p.recaudo.estado} />
                        </td>
                        <td className="py-2 pr-4 text-right tabular-nums">{pesos(p.saldo)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Seccion>
        )}

        <Seccion titulo="Consignaciones" descripcion={aprueba ? "Apruebe lo consignado y verifíquelo contra el extracto bancario." : undefined}>
          {!consignaciones ? (
            <Skeleton className="m-4 h-24" />
          ) : !consignaciones.length ? (
            <Vacio icono={Landmark} titulo="Aún no hay consignaciones" />
          ) : (
            <ul className="divide-y">
              {consignaciones.map((c) => (
                <li key={c.id}>
                  <div className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-3 text-left"
                      onClick={() => setExpandida(expandida === c.id ? null : c.id)}
                      aria-expanded={expandida === c.id}
                    >
                      <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", expandida === c.id && "rotate-180")} />
                      <span className="min-w-0 text-sm">
                        <span className="font-medium">
                          #{c.consecutivo} · {c.banco_destino}
                        </span>{" "}
                        <span className="text-muted-foreground">ref. {c.referencia_bancaria}</span>
                        <span className="block text-xs text-muted-foreground">
                          {fechaCorta(c.fecha_consignacion)} · {c.cantidad_recaudos} recaudos
                        </span>
                      </span>
                    </button>
                    <span className="text-right text-sm">
                      <span className="block font-semibold tabular-nums">{pesos(c.valor_consignado)}</span>
                      {Number(c.valor_consignado) !== Number(c.valor_aplicado) && (
                        <span className="text-xs text-destructive">Recaudos: {pesos(c.valor_aplicado)}</span>
                      )}
                    </span>
                    <Etiqueta tono={ESTADO_CONSIGNACION[c.estado].tono}>{ESTADO_CONSIGNACION[c.estado].label}</Etiqueta>
                    {aprueba && c.estado === "REGISTRADA" && (
                      <>
                        <Button size="sm" disabled={trabajando === c.id} onClick={() => void accion(c, "aprobar")}>
                          {trabajando === c.id ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                          Aprobar
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setRechazando(c)} aria-label="Rechazar">
                          <X className="size-4" />
                        </Button>
                      </>
                    )}
                    {aprueba && c.estado === "APROBADA" && (
                      <Button size="sm" variant="outline" disabled={trabajando === c.id} onClick={() => void accion(c, "verificar")}>
                        {trabajando === c.id ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
                        Verificar en extracto
                      </Button>
                    )}
                  </div>
                  {expandida === c.id && <DetalleConsignacion id={c.id} />}
                </li>
              ))}
            </ul>
          )}
        </Seccion>
      </div>

      <RegistrarDialog seleccion={elegidos} abierto={registrando} onCambio={setRegistrando} onRegistrada={refrescar} />
      <MotivoDialog
        abierto={rechazando !== null}
        onCambio={(v) => !v && setRechazando(null)}
        titulo={`Rechazar consignación #${rechazando?.consecutivo ?? ""}`}
        descripcion="Los recaudos vuelven a quedar pendientes por consignar. El rechazo queda en la auditoría."
        boton="Rechazar consignación"
        onConfirmar={async (motivo) => {
          if (!rechazando) return;
          await api(`${b}/consignaciones/${rechazando.id}/rechazar`, { method: "POST", json: { motivo } });
          toast.success(`Consignación #${rechazando.consecutivo} rechazada`);
          refrescar();
        }}
      />
    </div>
  );
}
