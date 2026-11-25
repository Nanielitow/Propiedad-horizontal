"use client";

import { AlertTriangle, CheckCircle2, FileCheck2, Loader2, Printer } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { Campo } from "@/components/activos/comunes";
import { campoClase, Etiqueta, mensajeError, SoporteInput } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, fetcher } from "@/lib/api";
import {
  baseCartera,
  compactoPesos,
  type PazYSalvo,
  type Periodo,
  type Prefactura,
  RANGO,
  type Rango,
  type ResultadoPago,
  type ResumenCartera,
  tonoMora,
} from "@/lib/cartera";
import { fechaCorta, hoyBogota, MEDIO, type MedioPago, pesos } from "@/lib/recaudos";
import { baseUnidades, type UnidadesPagina } from "@/lib/unidades";
import { cn } from "@/lib/utils";

export function MoraBadge({ dias }: { dias: number }) {
  return <Etiqueta tono={tonoMora(dias)}>{dias <= 0 ? "Al día" : `${dias} días de mora`}</Etiqueta>;
}

/** Revalida todas las consultas de la cartera (y la ficha de unidades, que muestra el saldo). */
export function useRefrescarCartera() {
  const { mutate } = useSWRConfig();
  return (tenantId: string) =>
    mutate((clave) => typeof clave === "string" && clave.startsWith(baseCartera(tenantId)), undefined, { revalidate: true });
}

// --- Registrar pago -------------------------------------------------------------------------

export function RegistrarPagoDialog({
  tenantId,
  abierto,
  onCambio,
  unidadId,
  saldoSugerido,
  onRegistrado,
}: {
  tenantId: string;
  abierto: boolean;
  onCambio: (v: boolean) => void;
  unidadId?: string;
  saldoSugerido?: string;
  onRegistrado?: (r: ResultadoPago) => void;
}) {
  const b = baseCartera(tenantId);
  const { data: unidades } = useSWR<UnidadesPagina>(abierto && !unidadId ? `${baseUnidades(tenantId)}?solo_principales=true&page_size=200` : null, fetcher);
  const [unidad, setUnidad] = useState("");
  const [valor, setValor] = useState("");
  const [fecha, setFecha] = useState(hoyBogota());
  const [medio, setMedio] = useState<MedioPago>("TRANSFERENCIA");
  const [referencia, setReferencia] = useState("");
  const [pagador, setPagador] = useState("");
  const [soporte, setSoporte] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoPago | null>(null);

  // Se reinicia SOLO al abrir. Tras registrar, el padre refresca el saldo (cambia saldoSugerido):
  // si eso reiniciara el formulario, se perdería el recibo y se invitaría a pagar dos veces.
  const estabaAbierto = useRef(false);
  useEffect(() => {
    const recienAbierto = abierto && !estabaAbierto.current;
    estabaAbierto.current = abierto;
    if (!recienAbierto) return;
    setUnidad(unidadId ?? "");
    setValor(saldoSugerido && Number(saldoSugerido) > 0 ? String(Number(saldoSugerido)) : "");
    setFecha(hoyBogota());
    setMedio("TRANSFERENCIA");
    setReferencia("");
    setPagador("");
    setSoporte(null);
    setResultado(null);
  }, [abierto, unidadId, saldoSugerido]);

  const valido = unidad && Number(valor) > 0 && (medio === "EFECTIVO" || referencia.trim() || soporte);

  async function registrar() {
    setEnviando(true);
    try {
      const r = await api<ResultadoPago>(`${b}/pagos`, {
        method: "POST",
        json: {
          unidad_id: unidad,
          fecha_pago: fecha,
          valor: valor.replace(/[^\d.]/g, ""),
          medio_pago: medio,
          referencia: referencia.trim() || null,
          pagador_nombre: pagador.trim() || null,
          soporte_key: soporte,
        },
      });
      setResultado(r);
      onRegistrado?.(r);
      toast.success(`Pago registrado · recibo ${r.pago.consecutivo}`);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="sm:max-w-lg">
        {resultado ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckCircle2 className="size-5 text-success" /> Recibo {resultado.pago.consecutivo} · {resultado.pago.unidad}
              </DialogTitle>
              <DialogDescription>
                {pesos(resultado.pago.valor)} el {fechaCorta(resultado.pago.fecha_pago)}. Se aplicó primero a intereses y luego a lo más antiguo, como exige la ley.
              </DialogDescription>
            </DialogHeader>
            <ul className="max-h-72 min-w-0 divide-y overflow-y-auto rounded-md border text-sm">
              {resultado.aplicaciones.map((a) => (
                <li key={a.cargo_id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className="min-w-0">
                    <span className="block truncate">{a.descripcion}</span>
                    {Number(a.descuento) > 0 && <span className="text-xs text-success">Descuento por pronto pago {pesos(a.descuento)}</span>}
                  </span>
                  <span className="shrink-0 font-medium tabular-nums">{pesos(a.valor)}</span>
                </li>
              ))}
              {Number(resultado.a_favor) > 0 && (
                <li className="flex justify-between px-3 py-2 text-primary">
                  <span>Queda como saldo a favor</span>
                  <span className="font-medium tabular-nums">{pesos(resultado.a_favor)}</span>
                </li>
              )}
            </ul>
            <p className="text-sm">
              Saldo pendiente de la unidad: <strong className="tabular-nums">{pesos(resultado.saldo_pendiente)}</strong>
            </p>
            <DialogFooter>
              <Button variant="outline" asChild>
                <a href={`/api/proxy${b}/pagos/${resultado.pago.id}/recibo.pdf`} target="_blank" rel="noreferrer">
                  <Printer className="size-4" /> Recibo en PDF
                </a>
              </Button>
              <Button onClick={() => onCambio(false)}>Listo</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Registrar pago de cuota</DialogTitle>
              <DialogDescription>Se aplica automáticamente: intereses primero, luego la deuda más antigua. Lo que sobre queda a favor.</DialogDescription>
            </DialogHeader>
            <div className="grid gap-3 sm:grid-cols-2">
              {!unidadId && (
                <Campo label="Unidad" className="sm:col-span-2">
                  <select value={unidad} onChange={(e) => setUnidad(e.target.value)} className={campoClase()}>
                    <option value="">Elija la unidad</option>
                    {unidades?.items.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.etiqueta}
                        {u.responsable_pago ? ` · ${u.responsable_pago.nombre}` : ""}
                      </option>
                    ))}
                  </select>
                </Campo>
              )}
              <Campo label="Valor recibido">
                <Input value={valor} onChange={(e) => setValor(e.target.value)} inputMode="numeric" placeholder="350000" autoFocus />
              </Campo>
              <Campo label="Fecha del pago">
                <input type="date" value={fecha} max={hoyBogota()} onChange={(e) => setFecha(e.target.value)} className={campoClase()} />
              </Campo>
              {/* No va dentro de <label>: el primer botón heredaría el texto de la etiqueta como nombre */}
              <div className="flex flex-col gap-1.5 text-sm sm:col-span-2" role="group" aria-labelledby="medio-pago-titulo">
                <span id="medio-pago-titulo" className="font-medium">
                  Medio de pago
                </span>
                <div className="flex gap-1 rounded-lg bg-muted p-1 text-sm">
                  {(Object.keys(MEDIO) as MedioPago[]).map((m) => (
                    <button key={m} type="button" aria-pressed={medio === m} onClick={() => setMedio(m)} className={cn("flex-1 rounded-md px-2 py-1.5 font-medium", medio === m ? "bg-card shadow-sm" : "text-muted-foreground")}>
                      {MEDIO[m]}
                    </button>
                  ))}
                </div>
              </div>
              {medio !== "EFECTIVO" && (
                <Campo label="Referencia bancaria" ayuda="Número de transacción o de consignación">
                  <Input value={referencia} onChange={(e) => setReferencia(e.target.value)} />
                </Campo>
              )}
              <Campo label="Quién pagó (opcional)" className={medio === "EFECTIVO" ? "sm:col-span-2" : undefined}>
                <Input value={pagador} onChange={(e) => setPagador(e.target.value)} />
              </Campo>
              <div className="sm:col-span-2">
                <SoporteInput tenantId={tenantId} valor={soporte} onCambio={setSoporte} />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => onCambio(false)}>
                Cancelar
              </Button>
              <Button disabled={!valido || enviando} onClick={registrar}>
                {enviando && <Loader2 className="size-4 animate-spin" />}
                Registrar {Number(valor) > 0 ? pesos(valor) : "pago"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// --- Facturar el mes ---------------------------------------------------------------------------

export function FacturarDialog({ tenantId, abierto, onCambio, onEmitido }: { tenantId: string; abierto: boolean; onCambio: (v: boolean) => void; onEmitido: () => void }) {
  const b = baseCartera(tenantId);
  const hoy = hoyBogota();
  const [mes, setMes] = useState("");
  const [previa, setPrevia] = useState<Prefactura | null>(null);
  // Propone el primer mes sin facturar: el actual o, si ya se emitió, el siguiente
  const { data: periodos } = useSWR<Periodo[]>(abierto ? `${b}/periodos` : null, fetcher);
  useEffect(() => {
    if (!abierto) {
      setMes("");
      return;
    }
    if (mes || !periodos) return;
    const actual = hoy.slice(0, 7);
    const emitido = periodos.some((p) => p.estado === "EMITIDO" && `${p.anio}-${String(p.mes).padStart(2, "0")}` === actual);
    const [a, mm] = actual.split("-").map(Number) as [number, number];
    setMes(emitido ? (mm === 12 ? `${a + 1}-01` : `${a}-${String(mm + 1).padStart(2, "0")}`) : actual);
  }, [abierto, periodos, mes, hoy]);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [emitiendo, setEmitiendo] = useState(false);
  const [anio, m] = mes.split("-").map(Number) as [number, number];

  useEffect(() => {
    if (!abierto || !mes) return;
    let vivo = true;
    setCargando(true);
    setError(null);
    api<Prefactura>(`${b}/periodos/previa`, { method: "POST", json: { anio, mes: m } })
      .then((p) => vivo && setPrevia(p))
      .catch((e) => {
        if (!vivo) return;
        setPrevia(null);
        setError(mensajeError(e));
      })
      .finally(() => vivo && setCargando(false));
    return () => {
      vivo = false;
    };
  }, [abierto, b, anio, m]);

  async function emitir() {
    setEmitiendo(true);
    try {
      await api(`${b}/periodos`, { method: "POST", json: { anio, mes: m } });
      toast.success(`Periodo de ${previa?.nombre.toLowerCase()} emitido`);
      onEmitido();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEmitiendo(false);
    }
  }

  const conInteres = previa?.lineas.filter((l) => Number(l.interes) > 0) ?? [];

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Facturar cuotas de administración</DialogTitle>
          <DialogDescription>Revise la vista previa: nada se guarda hasta que pulse «Emitir».</DialogDescription>
        </DialogHeader>
        <Campo label="Mes a facturar">
          <input type="month" value={mes} onChange={(e) => setMes(e.target.value)} className={cn(campoClase(), "w-48")} />
        </Campo>
        {cargando ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Calculando…
          </div>
        ) : error ? (
          <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</p>
        ) : previa ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Dato titulo="Unidades" valor={String(previa.unidades)} />
              <Dato titulo="Cuotas" valor={pesos(previa.total_cuotas)} />
              <Dato titulo="Intereses de mora" valor={pesos(previa.total_intereses)} detalle={conInteres.length ? `${conInteres.length} unidades` : undefined} />
              <Dato titulo="Vence" valor={fechaCorta(previa.fecha_vencimiento)} detalle={previa.fecha_limite_descuento ? `Descuento hasta ${fechaCorta(previa.fecha_limite_descuento)}` : undefined} />
            </div>
            {previa.advertencias.map((a) => (
              <p key={a} className="flex gap-2 rounded-md border border-warning/30 bg-warning-soft/40 px-3 py-2 text-sm">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" /> {a}
              </p>
            ))}
            <div className="max-h-64 overflow-y-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-muted text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-1.5 text-left font-medium">Unidad</th>
                    <th className="px-3 py-1.5 text-left font-medium">Responsable</th>
                    <th className="px-3 py-1.5 text-right font-medium">Cuota</th>
                    <th className="px-3 py-1.5 text-right font-medium">Intereses</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {previa.lineas.map((l) => (
                    <tr key={l.unidad_id}>
                      <td className="px-3 py-1.5 font-medium">{l.etiqueta}</td>
                      <td className="max-w-48 truncate px-3 py-1.5 text-muted-foreground">{l.responsable ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{l.cuota ? pesos(l.cuota) : "—"}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums" title={Number(l.interes) ? `Sobre ${pesos(l.capital_vencido)} vencidos` : undefined}>
                        {Number(l.interes) ? pesos(l.interes) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!previa || emitiendo || cargando} onClick={emitir}>
            {emitiendo && <Loader2 className="size-4 animate-spin" />}
            Emitir {previa ? previa.nombre.toLowerCase() : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Dato({ titulo, valor, detalle }: { titulo: string; valor: string; detalle?: string }) {
  return (
    <div className="rounded-md border px-3 py-2">
      <p className="text-xs text-muted-foreground">{titulo}</p>
      <p className="font-semibold tabular-nums">{valor}</p>
      {detalle && <p className="text-xs text-muted-foreground">{detalle}</p>}
    </div>
  );
}

// --- Paz y salvo -------------------------------------------------------------------------------

export function PazYSalvoBoton({ tenantId, unidadId, alDia, variante = "outline" }: { tenantId: string; unidadId: string; alDia: boolean; variante?: "outline" | "default" }) {
  const [enviando, setEnviando] = useState(false);
  async function expedir() {
    setEnviando(true);
    // La pestaña se abre ANTES del await: los navegadores bloquean ventanas abiertas después
    const ventana = window.open("about:blank", "_blank");
    try {
      const p = await api<PazYSalvo>(`${baseCartera(tenantId)}/unidades/${unidadId}/paz-y-salvo`, { method: "POST" });
      const url = `/api/proxy${baseCartera(tenantId)}/paz-y-salvo/${p.id}.pdf`;
      if (ventana) ventana.location.href = url;
      else window.location.href = url;
      toast.success(`Paz y salvo N.º ${p.consecutivo} expedido · código ${p.codigo_verificacion}`);
    } catch (e) {
      ventana?.close();
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Button variant={variante} onClick={expedir} disabled={!alDia || enviando} title={alDia ? undefined : "Requiere no tener saldo vencido"}>
      {enviando ? <Loader2 className="size-4 animate-spin" /> : <FileCheck2 className="size-4" />}
      Paz y salvo
    </Button>
  );
}

// --- Gráficos --------------------------------------------------------------------------------

/** Facturado (gris, referencia) vs. recaudado (color principal) por mes, con tooltip y tabla. */
export function GraficoRecaudo({ serie }: { serie: ResumenCartera["recaudo_mensual"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const datos = useMemo(() => serie.map((s) => ({ ...s, f: Number(s.facturado), r: Number(s.recaudado) })), [serie]);
  const max = Math.max(...datos.flatMap((x) => [x.f, x.r]), 1);
  const paso = Math.pow(10, Math.floor(Math.log10(max)));
  const tope = Math.ceil(max / paso) * paso;
  const guias = [tope, tope / 2];
  const H = 170;

  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs text-muted-foreground" aria-hidden>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-muted-foreground/45" /> Facturado
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-primary" /> Recaudado
        </span>
      </div>
      <div className="flex gap-2">
        <div className="relative w-14 shrink-0 text-right text-[11px] text-muted-foreground" style={{ height: H }}>
          {guias.map((g) => (
            <span key={g} className="absolute right-0 -translate-y-1/2 tabular-nums" style={{ top: H - (g / tope) * H }}>
              {compactoPesos(g)}
            </span>
          ))}
        </div>
        <div className="relative flex-1" style={{ height: H }} onMouseLeave={() => setHover(null)}>
          {guias.map((g) => (
            <div key={g} className="absolute inset-x-0 border-t border-border/70" style={{ top: H - (g / tope) * H }} />
          ))}
          <div className="absolute inset-0 flex items-end gap-1.5">
            {datos.map((x, i) => (
              <div key={x.mes} className="flex h-full flex-1 items-end justify-center gap-[2px]" onMouseEnter={() => setHover(i)}>
                <div className={cn("w-[40%] max-w-4 rounded-t-[4px] bg-muted-foreground/45", hover === i && "bg-muted-foreground/60")} style={{ height: x.f ? Math.max(2, (x.f / tope) * H) : 0 }} />
                <div className={cn("w-[40%] max-w-4 rounded-t-[4px] bg-primary/85", hover === i && "bg-primary")} style={{ height: x.r ? Math.max(2, (x.r / tope) * H) : 0 }} />
              </div>
            ))}
          </div>
          {hover !== null && datos[hover] && (
            <div
              className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full rounded-md border bg-popover px-2.5 py-1.5 text-xs whitespace-nowrap shadow-md"
              style={{ left: `${((hover + 0.5) / datos.length) * 100}%` }}
            >
              <p className="text-muted-foreground">{datos[hover].mes}</p>
              <p>
                Facturado <span className="font-semibold tabular-nums">{pesos(datos[hover].f)}</span>
              </p>
              <p>
                Recaudado <span className="font-semibold tabular-nums">{pesos(datos[hover].r)}</span>
                {datos[hover].f > 0 && <span className="text-muted-foreground"> · {Math.round((datos[hover].r / datos[hover].f) * 100)} %</span>}
              </p>
            </div>
          )}
        </div>
      </div>
      <div className="mt-1.5 ml-16 flex text-[11px] text-muted-foreground">
        {datos.map((x) => (
          <span key={x.mes} className="flex-1 text-center">
            {x.etiqueta}
          </span>
        ))}
      </div>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">Ver como tabla</summary>
        <table className="mt-2 w-full max-w-md text-xs">
          <thead className="text-muted-foreground">
            <tr>
              <th className="py-1 text-left font-medium">Mes</th>
              <th className="py-1 text-right font-medium">Facturado</th>
              <th className="py-1 text-right font-medium">Recaudado</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {datos.map((x) => (
              <tr key={x.mes}>
                <td className="py-1">{x.mes}</td>
                <td className="py-1 text-right tabular-nums">{pesos(x.f)}</td>
                <td className="py-1 text-right tabular-nums">{pesos(x.r)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

/** Cartera por antigüedad: una serie, etiqueta y valor siempre visibles. */
export function BarrasEdades({ edades, total }: { edades: Record<Rango, string>; total: number }) {
  const filas = (Object.keys(RANGO) as Rango[]).map((k) => ({ k, v: Number(edades[k] ?? 0) }));
  const max = Math.max(...filas.map((f) => f.v), 1);
  return (
    <ul className="space-y-3">
      {filas.map(({ k, v }) => (
        <li key={k}>
          <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
            <span>{RANGO[k].label}</span>
            <span className="tabular-nums">
              <span className="font-medium">{pesos(v)}</span>
              <span className="ml-1.5 text-xs text-muted-foreground">{total ? Math.round((v / total) * 100) : 0} %</span>
            </span>
          </div>
          <div className="h-2 rounded-full bg-secondary">
            <div className="h-2 rounded-full bg-primary/80" style={{ width: `${(v / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
