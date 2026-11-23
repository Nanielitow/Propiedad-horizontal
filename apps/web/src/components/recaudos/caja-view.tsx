"use client";

import { ArrowRightLeft, Calculator, Check, HandCoins, Inbox, Loader2, Lock, X } from "lucide-react";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api, fetcher } from "@/lib/api";
import {
  base,
  type Cierre,
  type Entrega,
  ESTADO_ENTREGA,
  fechaHora,
  type Persona,
  pesos,
  puede,
  type RecaudoFila,
  type RecaudosPagina,
  type ResumenCaja,
} from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { campoClase, Etiqueta, mensajeError, MotivoDialog, Seccion, SinAcceso, Vacio } from "./comunes";

const soloDigitos = (v: string) => v.replace(/\D/g, "");

function CerrarCajaDialog({ resumen, abierto, onCambio, onCerrado }: { resumen: ResumenCaja; abierto: boolean; onCambio: (v: boolean) => void; onCerrado: () => void }) {
  const { tenant } = useTenant();
  const [inicial, setInicial] = useState("0");
  const [contado, setContado] = useState("");
  const [justificacion, setJustificacion] = useState("");
  const [enviando, setEnviando] = useState(false);

  const esperado = Number(inicial || 0) + Number(resumen.total_efectivo);
  const diferencia = contado === "" ? null : Number(contado) - esperado;
  const requiereJustificacion = diferencia !== null && diferencia !== 0;
  const valido = contado !== "" && (!requiereJustificacion || justificacion.trim().length >= 10);

  async function cerrar() {
    setEnviando(true);
    try {
      const c = await api<Cierre>(`${base(tenant.tenant_id)}/caja/cierres`, {
        method: "POST",
        json: {
          saldo_inicial: inicial || "0",
          valor_fisico_contado: contado,
          observacion_justificacion: justificacion.trim() || null,
        },
      });
      toast.success(
        c.tipo_diferencia === "CUADRADO"
          ? `Cierre #${c.consecutivo}: caja cuadrada`
          : `Cierre #${c.consecutivo} registrado con ${c.tipo_diferencia.toLowerCase()}; se avisó a la administración`,
      );
      onCerrado();
      onCambio(false);
      setContado("");
      setJustificacion("");
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
          <DialogTitle>Cerrar caja</DialogTitle>
          <DialogDescription>
            Cuente el dinero físico. El sistema compara con lo registrado en su turno ({resumen.cantidad} recaudos en efectivo).
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="inicial">Base de caja al iniciar</Label>
            <Input id="inicial" inputMode="numeric" value={inicial} onChange={(e) => setInicial(soloDigitos(e.target.value))} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="contado">Dinero contado</Label>
            <Input id="contado" inputMode="numeric" value={contado} onChange={(e) => setContado(soloDigitos(e.target.value))} autoFocus />
          </div>
        </div>
        <dl className="divide-y rounded-md border px-3 text-sm">
          <div className="flex justify-between py-1.5">
            <dt className="text-muted-foreground">Recaudado en efectivo</dt>
            <dd className="tabular-nums">{pesos(resumen.total_efectivo)}</dd>
          </div>
          <div className="flex justify-between py-1.5">
            <dt className="text-muted-foreground">Esperado en caja</dt>
            <dd className="font-medium tabular-nums">{pesos(esperado)}</dd>
          </div>
          <div className="flex justify-between py-1.5">
            <dt className="text-muted-foreground">Diferencia</dt>
            <dd
              className={cn(
                "font-semibold tabular-nums",
                diferencia === 0 && "text-success",
                diferencia !== null && diferencia < 0 && "text-destructive",
                diferencia !== null && diferencia > 0 && "text-warning",
              )}
            >
              {diferencia === null ? "—" : diferencia === 0 ? "Cuadrada" : `${diferencia > 0 ? "Sobrante" : "Faltante"} ${pesos(Math.abs(diferencia))}`}
            </dd>
          </div>
        </dl>
        {requiereJustificacion && (
          <div className="space-y-1.5">
            <Label htmlFor="just">Justificación de la diferencia</Label>
            <Textarea id="just" rows={2} value={justificacion} onChange={(e) => setJustificacion(e.target.value)} />
            <p className="text-xs text-muted-foreground">Obligatoria. La administración recibirá una alerta de auditoría.</p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!valido || enviando} onClick={cerrar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Confirmar cierre
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EntregarDialog({ disponibles, abierto, onCambio, onEntregado }: { disponibles: RecaudoFila[]; abierto: boolean; onCambio: (v: boolean) => void; onEntregado: () => void }) {
  const { tenant } = useTenant();
  const b = base(tenant.tenant_id);
  const { data: admins } = useSWR<Persona[]>(abierto ? `${b}/personal?rol=ADMIN` : null, fetcher);
  const [receptor, setReceptor] = useState("");
  const [obs, setObs] = useState("");
  const [enviando, setEnviando] = useState(false);
  const total = disponibles.reduce((s, r) => s + Number(r.valor_recibido), 0);

  async function entregar() {
    setEnviando(true);
    try {
      const e = await api<Entrega>(`${b}/entregas`, {
        method: "POST",
        json: { recibido_por_id: receptor, recaudo_ids: disponibles.map((r) => r.id), observaciones: obs.trim() || null },
      });
      toast.success(`Entrega #${e.consecutivo} por ${pesos(e.valor_total)}: queda pendiente de que ${e.recibido_por.replace(/\s*\(.*\)/, "")} la confirme`);
      onEntregado();
      onCambio(false);
    } catch (err) {
      toast.error(mensajeError(err));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Entregar efectivo a la administración</DialogTitle>
          <DialogDescription>
            Se entrega todo el efectivo ya cerrado que sigue en su caja: {disponibles.length} recaudos por {pesos(total)}.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="receptor">¿Quién recibe?</Label>
            <select id="receptor" value={receptor} onChange={(e) => setReceptor(e.target.value)} className={campoClase()}>
              <option value="">Elija…</option>
              {admins?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nombre}
                  </option>
                ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="obs-e">Observaciones (opcional)</Label>
            <Textarea id="obs-e" rows={2} value={obs} onChange={(e) => setObs(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!receptor || enviando} onClick={entregar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Registrar entrega
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ConfirmarEntregaDialog({ entrega, onCerrar, onHecho }: { entrega: Entrega | null; onCerrar: () => void; onHecho: () => void }) {
  const { tenant } = useTenant();
  const [contado, setContado] = useState("");
  const [nota, setNota] = useState("");
  const [enviando, setEnviando] = useState(false);
  if (!entrega) return null;
  const diferencia = contado === "" ? null : Number(contado) - Number(entrega.valor_total);

  async function confirmar() {
    if (!entrega) return;
    setEnviando(true);
    try {
      await api(`${base(tenant.tenant_id)}/entregas/${entrega.id}/confirmar`, {
        method: "POST",
        json: { valor_contado: contado, observaciones: nota.trim() || null },
      });
      toast.success(`Entrega #${entrega.consecutivo} confirmada`);
      setContado("");
      setNota("");
      onHecho();
      onCerrar();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirmar entrega #{entrega.consecutivo}</DialogTitle>
          <DialogDescription>
            {entrega.entregado_por.replace(/\s*\(.*\)/, "")} entrega {entrega.cantidad_recaudos} recaudos por {pesos(entrega.valor_total)}. Cuente el dinero antes de confirmar.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="contado-e">Dinero recibido</Label>
          <Input id="contado-e" inputMode="numeric" value={contado} onChange={(e) => setContado(soloDigitos(e.target.value))} autoFocus />
          {diferencia !== null && diferencia !== 0 && (
            <p className="text-xs text-destructive">
              {diferencia > 0 ? "Sobran" : "Faltan"} {pesos(Math.abs(diferencia))}: explique la diferencia; se generará una alerta.
            </p>
          )}
        </div>
        {diferencia !== null && diferencia !== 0 && <Textarea rows={2} value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Explicación" />}
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button disabled={contado === "" || (diferencia !== 0 && nota.trim().length < 10) || enviando} onClick={confirmar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Confirmar recepción
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function CajaView() {
  const { tenant, user } = useTenant();
  const b = base(tenant.tenant_id);
  const permitido = puede(tenant.role, "caja");
  const esAdmin = puede(tenant.role, "recibir");
  const { data: resumen, mutate: refrescarResumen } = useSWR<ResumenCaja>(permitido ? `${b}/caja/estado` : null, fetcher);
  const { data: cierres, mutate: refrescarCierres } = useSWR<Cierre[]>(permitido ? `${b}/caja/cierres` : null, fetcher);
  const { data: entregas, mutate: refrescarEntregas } = useSWR<Entrega[]>(permitido ? `${b}/entregas` : null, fetcher);
  // Efectivo propio ya cerrado que sigue en caja: lo que se puede entregar
  const { data: enCaja, mutate: refrescarEnCaja } = useSWR<RecaudosPagina>(
    permitido ? `${b}?estado=RECAUDADO_EN_CAJA&usuario_id=${user.id}&medio_pago=EFECTIVO&page_size=100` : null,
    fetcher,
  );
  const [cerrando, setCerrando] = useState(false);
  const [entregando, setEntregando] = useState(false);
  const [confirmando, setConfirmando] = useState<Entrega | null>(null);
  const [rechazando, setRechazando] = useState<Entrega | null>(null);

  const disponibles = useMemo(() => enCaja?.items.filter((r) => r.cierre_id && !r.entrega_id) ?? [], [enCaja]);
  const porConfirmar = entregas?.filter((e) => e.estado === "PENDIENTE_CONFIRMACION" && e.recibido_por_id === user.id) ?? [];

  function refrescar() {
    void refrescarResumen();
    void refrescarCierres();
    void refrescarEntregas();
    void refrescarEnCaja();
  }

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Caja" description="Cierre de turno, entregas de efectivo a la administración e historial de arqueos." />

      <div className="space-y-6 p-4 sm:p-6">
        {porConfirmar.length > 0 && (
          <Seccion titulo="Entregas por confirmar" descripcion="Efectivo que le entregaron y está pendiente de que usted lo cuente.">
            <ul className="divide-y">
              {porConfirmar.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <Inbox className="size-5 text-warning" />
                  <div className="min-w-0 flex-1 text-sm">
                    <p className="font-medium">
                      Entrega #{e.consecutivo} · {pesos(e.valor_total)}
                    </p>
                    <p className="text-muted-foreground">
                      De {e.entregado_por.replace(/\s*\(.*\)/, "")} · {e.cantidad_recaudos} recaudos · {fechaHora(e.fecha_entrega)}
                    </p>
                  </div>
                  <Button size="sm" onClick={() => setConfirmando(e)}>
                    <Check className="size-4" /> Confirmar
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setRechazando(e)}>
                    <X className="size-4" /> Rechazar
                  </Button>
                </li>
              ))}
            </ul>
          </Seccion>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          <Seccion
            titulo="Mi turno"
            descripcion={resumen ? `Desde ${fechaHora(resumen.inicio_turno)}` : undefined}
            acciones={
              resumen && (
                <Button size="sm" disabled={resumen.cantidad === 0} title={resumen.cantidad === 0 ? "No hay efectivo sin cerrar en su turno" : undefined} onClick={() => setCerrando(true)}>
                  <Calculator className="size-4" /> Cerrar caja
                </Button>
              )
            }
          >
            {!resumen ? (
              <Skeleton className="m-4 h-24" />
            ) : (
              <div className="p-4">
                <p className="text-sm text-muted-foreground">Efectivo recibido en el turno</p>
                <p className="text-3xl font-semibold tracking-tight tabular-nums">{pesos(resumen.total_efectivo)}</p>
                <p className="text-sm text-muted-foreground">{resumen.cantidad} recaudos en efectivo sin cerrar</p>
                {resumen.recaudos.length > 0 && (
                  <ul className="mt-3 max-h-56 divide-y overflow-y-auto rounded-md border text-sm">
                    {resumen.recaudos.map((r) => (
                      <li key={r.id} className="flex justify-between gap-2 px-3 py-1.5">
                        <span className="truncate">
                          #{r.consecutivo} · {r.concepto}
                          {r.placa && <span className="ml-1 font-mono text-xs text-muted-foreground">{r.placa}</span>}
                        </span>
                        <span className="tabular-nums">{pesos(r.valor_recibido)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </Seccion>

          <Seccion
            titulo="Efectivo cerrado en caja"
            descripcion="Ya contado en un cierre, pendiente de entregar o consignar."
            acciones={
              disponibles.length > 0 && (
                <Button size="sm" variant="outline" onClick={() => setEntregando(true)}>
                  <HandCoins className="size-4" /> Entregar a administración
                </Button>
              )
            }
          >
            <div className="p-4">
              <p className="text-3xl font-semibold tracking-tight tabular-nums">
                {pesos(disponibles.reduce((s, r) => s + Number(r.valor_recibido), 0))}
              </p>
              <p className="text-sm text-muted-foreground">
                {disponibles.length} recaudos
                {esAdmin && disponibles.length > 0 && " · también puede consignarlos directamente en Conciliación"}
              </p>
            </div>
          </Seccion>
        </div>

        <Seccion titulo="Historial de cierres" descripcion={tenant.role === "AUXILIAR" ? "Sus arqueos de caja." : "Arqueos de todo el personal."}>
          {!cierres ? (
            <Skeleton className="m-4 h-24" />
          ) : !cierres.length ? (
            <Vacio icono={Lock} titulo="Aún no hay cierres de caja" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">N.°</TableHead>
                  <TableHead>Cierre</TableHead>
                  <TableHead className="hidden md:table-cell">Responsable</TableHead>
                  <TableHead className="text-right">Esperado</TableHead>
                  <TableHead className="text-right">Contado</TableHead>
                  <TableHead className="pr-4 text-right">Resultado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cierres.map((c) => (
                  <TableRow key={c.id} title={c.observacion_justificacion ?? undefined}>
                    <TableCell className="pl-4 tabular-nums">{c.consecutivo}</TableCell>
                    <TableCell className="whitespace-nowrap">{fechaHora(c.fin_turno)}</TableCell>
                    <TableCell className="hidden md:table-cell">{c.usuario.replace(/\s*\(.*\)/, "")}</TableCell>
                    <TableCell className="text-right tabular-nums">{pesos(c.saldo_esperado_sistema)}</TableCell>
                    <TableCell className="text-right tabular-nums">{pesos(c.valor_fisico_contado)}</TableCell>
                    <TableCell className="pr-4 text-right">
                      {c.tipo_diferencia === "CUADRADO" ? (
                        <Etiqueta tono="success">Cuadrada</Etiqueta>
                      ) : (
                        <Etiqueta tono={c.tipo_diferencia === "FALTANTE" ? "danger" : "warning"}>
                          {c.tipo_diferencia === "FALTANTE" ? "Faltante" : "Sobrante"} {pesos(Math.abs(Number(c.diferencia)))}
                        </Etiqueta>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Seccion>

        <Seccion titulo="Entregas internas" descripcion="Traslados de efectivo de recepción a la administración.">
          {!entregas ? (
            <Skeleton className="m-4 h-20" />
          ) : !entregas.length ? (
            <Vacio icono={ArrowRightLeft} titulo="Aún no hay entregas" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">N.°</TableHead>
                  <TableHead>Fecha</TableHead>
                  <TableHead className="hidden md:table-cell">De → Para</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead className="pr-4">Estado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entregas.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="pl-4 tabular-nums">{e.consecutivo}</TableCell>
                    <TableCell className="whitespace-nowrap">{fechaHora(e.fecha_entrega)}</TableCell>
                    <TableCell className="hidden md:table-cell">
                      {e.entregado_por.replace(/\s*\(.*\)/, "")} → {e.recibido_por.replace(/\s*\(.*\)/, "")}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{pesos(e.valor_total)}</TableCell>
                    <TableCell className="pr-4">
                      <Etiqueta tono={ESTADO_ENTREGA[e.estado].tono}>{ESTADO_ENTREGA[e.estado].label}</Etiqueta>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Seccion>
      </div>

      {resumen && <CerrarCajaDialog resumen={resumen} abierto={cerrando} onCambio={setCerrando} onCerrado={refrescar} />}
      <EntregarDialog disponibles={disponibles} abierto={entregando} onCambio={setEntregando} onEntregado={refrescar} />
      <ConfirmarEntregaDialog entrega={confirmando} onCerrar={() => setConfirmando(null)} onHecho={refrescar} />
      <MotivoDialog
        abierto={rechazando !== null}
        onCambio={(v) => !v && setRechazando(null)}
        titulo={`Rechazar entrega #${rechazando?.consecutivo ?? ""}`}
        descripcion="El efectivo vuelve a la caja de quien lo entregó, que podrá entregarlo de nuevo."
        boton="Rechazar entrega"
        onConfirmar={async (motivo) => {
          if (!rechazando) return;
          await api(`${b}/entregas/${rechazando.id}/rechazar`, { method: "POST", json: { motivo } });
          toast.success(`Entrega #${rechazando.consecutivo} rechazada`);
          refrescar();
        }}
      />
    </div>
  );
}
