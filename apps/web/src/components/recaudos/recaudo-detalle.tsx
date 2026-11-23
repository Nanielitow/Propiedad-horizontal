"use client";

import { Ban, CheckCircle2, ExternalLink, History, Loader2, Pencil } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

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
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, fetcher } from "@/lib/api";
import {
  ACCION,
  type Auditoria,
  base,
  duracion,
  ESTADO,
  ESTADO_CONSIGNACION,
  fechaCorta,
  fechaHora,
  MEDIO,
  pesos,
  puede,
  type RecaudoDetalle as Detalle,
} from "@/lib/recaudos";

import { EstadoBadge, Etiqueta, mensajeError, MotivoDialog } from "./comunes";

function Fila({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="text-right font-medium">{v}</dd>
    </div>
  );
}

const CAMPO: Record<string, string> = {
  estado: "Estado",
  nombre_pagador: "Pagador",
  identificacion_pagador: "Identificación",
  numero_comprobante: "Comprobante",
  observaciones: "Observaciones",
  unidad_id: "Unidad",
  soporte_key: "Soporte",
  cierre_id: "Cierre de caja",
  entrega_id: "Entrega interna",
  motivo_anulacion: "Motivo",
};

function cambios(a: Auditoria) {
  if (a.accion === "CREACION" || !a.valores_nuevos) return null;
  return Object.entries(a.valores_nuevos)
    .filter(([k]) => k in CAMPO && !k.endsWith("_at") && !k.endsWith("_por_id"))
    .map(([k, v]) => {
      const antes = a.valores_anteriores?.[k];
      const fmt = (x: unknown) =>
        k === "estado" && typeof x === "string" && x in ESTADO ? ESTADO[x as keyof typeof ESTADO].label : x ? String(x) : "—";
      const esId = k.endsWith("_id") || k === "soporte_key";
      return (
        <li key={k}>
          {CAMPO[k]}: {esId ? (v ? "asignado" : "quitado") : `${fmt(antes)} → ${fmt(v)}`}
        </li>
      );
    });
}

function EditarDialog({ r, abierto, onCambio, onGuardado }: { r: Detalle; abierto: boolean; onCambio: (v: boolean) => void; onGuardado: () => void }) {
  const { tenant } = useTenant();
  const [pagador, setPagador] = useState(r.nombre_pagador);
  const [comprobante, setComprobante] = useState(r.numero_comprobante ?? "");
  const [observaciones, setObservaciones] = useState(r.observaciones ?? "");
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function guardar() {
    setEnviando(true);
    try {
      await api(`${base(tenant.tenant_id)}/${r.id}`, {
        method: "PATCH",
        json: {
          nombre_pagador: pagador.trim(),
          numero_comprobante: comprobante.trim() || null,
          observaciones: observaciones.trim() || null,
          motivo: motivo.trim(),
        },
      });
      toast.success("Recaudo actualizado");
      onGuardado();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Editar recaudo #{r.consecutivo}</DialogTitle>
          <DialogDescription>
            Solo los datos descriptivos. El valor, el concepto y el medio de pago no se editan: si están mal, anule y registre de nuevo.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="e-pagador">Pagador</Label>
            <Input id="e-pagador" value={pagador} onChange={(e) => setPagador(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-comp">Comprobante</Label>
            <Input id="e-comp" value={comprobante} onChange={(e) => setComprobante(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-obs">Observaciones</Label>
            <Textarea id="e-obs" rows={2} value={observaciones} onChange={(e) => setObservaciones(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-motivo">Motivo del cambio</Label>
            <Input id="e-motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Queda en la auditoría" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={motivo.trim().length < 5 || pagador.trim().length < 2 || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RecaudoDetalleSheet({ id, onClose, onCambio }: { id: string | null; onClose: () => void; onCambio: () => void }) {
  const { tenant, user } = useTenant();
  const b = base(tenant.tenant_id);
  const { data: r, mutate } = useSWR<Detalle>(id ? `${b}/${id}` : null, fetcher);
  const verAuditoria = puede(tenant.role, "auditoria");
  const { data: historial, mutate: refrescarHistorial } = useSWR<Auditoria[]>(id && verAuditoria ? `${b}/${id}/auditoria` : null, fetcher);
  const [anulando, setAnulando] = useState(false);
  const [editando, setEditando] = useState(false);
  const [verificando, setVerificando] = useState(false);

  function actualizado() {
    void mutate();
    void refrescarHistorial();
    onCambio();
  }

  async function verificar() {
    if (!r) return;
    setVerificando(true);
    try {
      await api(`${b}/${r.id}/verificar`, { method: "POST" });
      toast.success(`Recaudo #${r.consecutivo} verificado`);
      actualizado();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setVerificando(false);
    }
  }

  const puedeEditar =
    r &&
    r.estado !== "ANULADO" &&
    r.estado !== "VERIFICADO" &&
    (tenant.role === "ADMIN" || (tenant.role === "AUXILIAR" && r.usuario_receptor_id === user.id && !r.cierre_id));

  return (
    <Sheet open={id !== null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        {!r ? (
          <div className="space-y-3 p-6">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-40" />
          </div>
        ) : (
          <>
            <SheetHeader className="border-b">
              <SheetTitle className="flex items-center gap-2">
                Recaudo #{r.consecutivo} <EstadoBadge estado={r.estado} />
              </SheetTitle>
              <SheetDescription>
                {r.concepto} · {fechaHora(r.fecha_recaudo)} · recibió {r.receptor.replace(/\s*\(.*\)/, "")}
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-5 px-4 pb-6">
              <div>
                <p className="text-3xl font-semibold tracking-tight tabular-nums">{pesos(r.valor_recibido)}</p>
                <p className="text-sm text-muted-foreground">{MEDIO[r.medio_pago]}</p>
              </div>

              {r.estado === "ANULADO" && (
                <div className="rounded-md border border-destructive/25 bg-destructive/5 p-3 text-sm">
                  <p className="font-medium text-destructive">Anulado por {r.anulado_por} · {r.anulado_at && fechaHora(r.anulado_at)}</p>
                  <p className="mt-1">{r.motivo_anulacion}</p>
                </div>
              )}

              {/* Acciones */}
              <div className="flex flex-wrap gap-2">
                {r.estado === "PENDIENTE_VERIFICACION" && puede(tenant.role, "verificar") && (
                  <Button size="sm" onClick={verificar} disabled={verificando}>
                    {verificando ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                    Verificar en extracto
                  </Button>
                )}
                {puedeEditar && (
                  <Button size="sm" variant="outline" onClick={() => setEditando(true)}>
                    <Pencil className="size-4" /> Editar
                  </Button>
                )}
                {r.estado !== "ANULADO" && puede(tenant.role, "anular") && (
                  <Button size="sm" variant="outline" className="text-destructive hover:text-destructive" onClick={() => setAnulando(true)}>
                    <Ban className="size-4" /> Anular
                  </Button>
                )}
                {r.soporte_url && (
                  <Button size="sm" variant="outline" asChild>
                    <a href={r.soporte_url} target="_blank" rel="noreferrer">
                      <ExternalLink className="size-4" /> Ver soporte
                    </a>
                  </Button>
                )}
              </div>

              <dl className="divide-y rounded-md border px-3">
                <Fila k="Pagador" v={r.nombre_pagador} />
                {r.identificacion_pagador && <Fila k="Identificación" v={r.identificacion_pagador} />}
                <Fila k="Unidad" v={r.unidad ?? "Visitante externo"} />
                {r.numero_comprobante && <Fila k="Comprobante" v={r.numero_comprobante} />}
                {Number(r.saldo_por_consignar) > 0 && <Fila k="Por consignar" v={pesos(r.saldo_por_consignar)} />}
                {r.verificado_por && <Fila k="Verificado" v={`${r.verificado_por} · ${r.verificado_at && fechaCorta(r.verificado_at)}`} />}
              </dl>

              {r.parqueadero && (
                <div>
                  <h3 className="mb-1.5 text-sm font-semibold">Parqueadero</h3>
                  <dl className="divide-y rounded-md border px-3">
                    <Fila k="Placa" v={<span className="font-mono tracking-wider">{r.parqueadero.placa_vehiculo}</span>} />
                    <Fila k="Ingreso" v={fechaHora(r.parqueadero.hora_ingreso)} />
                    <Fila k="Salida" v={fechaHora(r.parqueadero.hora_salida)} />
                    <Fila k="Tiempo" v={duracion(r.parqueadero.minutos_totales)} />
                    <Fila k="Tarifa sugerida" v={pesos(r.parqueadero.tarifa_sugerida)} />
                  </dl>
                </div>
              )}

              {r.reserva && (
                <div>
                  <h3 className="mb-1.5 text-sm font-semibold">Reserva</h3>
                  <dl className="divide-y rounded-md border px-3">
                    <Fila k="Zona" v={r.zona} />
                    <Fila k="Fecha del evento" v={fechaCorta(r.reserva.fecha_evento)} />
                    {r.reserva.hora_inicio && <Fila k="Horario" v={`${r.reserva.hora_inicio.slice(0, 5)} – ${r.reserva.hora_fin?.slice(0, 5) ?? ""}`} />}
                    <Fila k="Solicitante" v={r.reserva.solicitante} />
                  </dl>
                </div>
              )}

              {r.items.length > 1 && (
                <div>
                  <h3 className="mb-1.5 text-sm font-semibold">Desglose</h3>
                  <dl className="divide-y rounded-md border px-3">
                    {r.items.map((i) => (
                      <Fila key={i.concepto_id + i.valor} k={i.descripcion ?? i.concepto} v={pesos(i.valor)} />
                    ))}
                  </dl>
                </div>
              )}

              {r.consignaciones.length > 0 && (
                <div>
                  <h3 className="mb-1.5 text-sm font-semibold">Consignaciones</h3>
                  <ul className="divide-y rounded-md border">
                    {r.consignaciones.map((c) => (
                      <li key={c.consignacion_id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                        <span>
                          #{c.consecutivo} · {c.banco_destino} <span className="text-muted-foreground">ref. {c.referencia_bancaria}</span>
                        </span>
                        <span className="flex items-center gap-2">
                          <span className="tabular-nums">{pesos(c.valor_aplicado)}</span>
                          <Etiqueta tono={ESTADO_CONSIGNACION[c.estado].tono}>{ESTADO_CONSIGNACION[c.estado].label}</Etiqueta>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {r.observaciones && (
                <div>
                  <h3 className="mb-1.5 text-sm font-semibold">Observaciones</h3>
                  <p className="rounded-md border px-3 py-2 text-sm whitespace-pre-line">{r.observaciones}</p>
                </div>
              )}

              {verAuditoria && historial && (
                <div>
                  <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
                    <History className="size-4" /> Historial de auditoría
                  </h3>
                  <ol className="space-y-3 border-l pl-4">
                    {historial.map((a) => (
                      <li key={a.id} className="relative text-sm">
                        <span className="absolute top-1.5 -left-[21px] size-2.5 rounded-full border-2 border-card bg-primary" />
                        <p className="font-medium">
                          {ACCION[a.accion]} <span className="font-normal text-muted-foreground">· {a.usuario ?? "Sistema"} · {fechaHora(a.fecha_hora)}</span>
                        </p>
                        {a.motivo && <p className="text-muted-foreground">«{a.motivo}»</p>}
                        <ul className="text-xs text-muted-foreground">{cambios(a)}</ul>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>

            <MotivoDialog
              abierto={anulando}
              onCambio={setAnulando}
              titulo={`Anular recaudo #${r.consecutivo}`}
              descripcion="El registro no se borra: queda visible como anulado, deja de sumar en los totales y la anulación queda en la auditoría."
              boton="Anular recaudo"
              onConfirmar={async (motivo) => {
                await api(`${b}/${r.id}/anular`, { method: "POST", json: { motivo } });
                toast.success(`Recaudo #${r.consecutivo} anulado`);
                actualizado();
              }}
            />
            <EditarDialog key={r.id + r.nombre_pagador} r={r} abierto={editando} onCambio={setEditando} onGuardado={actualizado} />
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
