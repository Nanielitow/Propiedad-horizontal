"use client";

import { Car, CheckCircle2, Loader2, PartyPopper, Receipt, Sparkles, Wallet } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, fetcher } from "@/lib/api";
import {
  aDatetimeLocal,
  base,
  type Concepto,
  desdeDatetimeLocal,
  duracion,
  hoyBogota,
  MEDIO,
  type MedioPago,
  pesos,
  puede,
  type RecaudoDetalle,
  type Reserva,
  type ResumenCaja,
  type Unidad,
  type Zona,
} from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { campoClase, mensajeError, SinAcceso, SoporteInput } from "./comunes";

const ICONO: Record<string, React.ComponentType<{ className?: string }>> = {
  PARQUEADERO: Car,
  ALQUILER_ZONA: PartyPopper,
  ASEO: Sparkles,
};

function tarifaTexto(c: Concepto) {
  if (c.tipo_cobro === "POR_HORA") return `${pesos(c.tarifa_base)} cada ${c.fraccion_minutos === 60 ? "hora" : `${c.fraccion_minutos} min`}`;
  if (c.tipo_cobro === "FIJO") return pesos(c.tarifa_base);
  return "Valor libre";
}

interface Cotizacion {
  minutos: number;
  fracciones: number;
  tarifa_sugerida: string;
}

export function RegistrarView() {
  const { tenant } = useTenant();
  const b = base(tenant.tenant_id);
  const permitido = puede(tenant.role, "registrar");
  const { data: conceptos } = useSWR<Concepto[]>(permitido ? `${b}/conceptos` : null, fetcher);
  const { data: unidades } = useSWR<Unidad[]>(permitido ? `${b}/unidades` : null, fetcher);
  const { data: zonas } = useSWR<Zona[]>(permitido ? `${b}/zonas` : null, fetcher);
  const { data: caja, mutate: refrescarCaja } = useSWR<ResumenCaja>(permitido ? `${b}/caja/estado` : null, fetcher);

  const [conceptoId, setConceptoId] = useState<string | null>(null);
  const concepto = conceptos?.find((c) => c.id === conceptoId) ?? null;
  const aseo = conceptos?.find((c) => c.codigo === "ASEO");

  // Campos comunes
  const [pagador, setPagador] = useState("");
  const [identificacion, setIdentificacion] = useState("");
  const [unidadId, setUnidadId] = useState("");
  const [medio, setMedio] = useState<MedioPago>("EFECTIVO");
  const [comprobante, setComprobante] = useState("");
  const [soporte, setSoporte] = useState<string | null>(null);
  const [observaciones, setObservaciones] = useState("");
  const [valor, setValor] = useState("");
  // Parqueadero
  const [placa, setPlaca] = useState("");
  const [ingreso, setIngreso] = useState("");
  const [salida, setSalida] = useState("");
  const [cotizacion, setCotizacion] = useState<Cotizacion | null>(null);
  // Alquiler
  const [zonaId, setZonaId] = useState("");
  const [fechaEvento, setFechaEvento] = useState("");
  const [horaInicio, setHoraInicio] = useState("");
  const [horaFin, setHoraFin] = useState("");
  const [valorAlquiler, setValorAlquiler] = useState("");
  const [valorAseo, setValorAseo] = useState("");

  const [enviando, setEnviando] = useState(false);
  const [ultimo, setUltimo] = useState<RecaudoDetalle | null>(null);

  function elegir(c: Concepto) {
    setConceptoId(c.id);
    setCotizacion(null);
    setValor(c.tipo_cobro === "FIJO" && c.tarifa_base ? String(Number(c.tarifa_base)) : "");
    if (c.requiere_vehiculo) {
      const ahora = new Date();
      setIngreso(aDatetimeLocal(new Date(ahora.getTime() - 60 * 60 * 1000)));
      setSalida(aDatetimeLocal(ahora));
      setPagador((p) => p || "Visitante");
    }
    if (c.requiere_reserva) setFechaEvento(hoyBogota());
  }

  // Cotización del parqueadero en vivo
  useEffect(() => {
    if (!concepto?.requiere_vehiculo || !ingreso || !salida || salida <= ingreso) {
      setCotizacion(null);
      return;
    }
    const ctrl = new AbortController();
    const q = new URLSearchParams({
      concepto_id: concepto.id,
      hora_ingreso: desdeDatetimeLocal(ingreso),
      hora_salida: desdeDatetimeLocal(salida),
    });
    const t = setTimeout(() => {
      api<Cotizacion>(`${b}/parqueadero/cotizar?${q}`, { signal: ctrl.signal })
        .then((c) => {
          setCotizacion(c);
          setValor(String(Number(c.tarifa_sugerida)));
        })
        .catch(() => setCotizacion(null));
    }, 250);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [b, concepto?.id, concepto?.requiere_vehiculo, ingreso, salida]);

  // Tarifas de la zona elegida
  useEffect(() => {
    const zona = zonas?.find((z) => z.id === zonaId);
    if (!zona) return;
    setValorAlquiler(zona.tarifa_alquiler ? String(Number(zona.tarifa_alquiler)) : concepto?.tarifa_base ? String(Number(concepto.tarifa_base)) : "");
    setValorAseo(zona.tarifa_aseo ? String(Number(zona.tarifa_aseo)) : "");
  }, [zonaId, zonas, concepto?.tarifa_base]);

  const totalAlquiler = Number(valorAlquiler || 0) + Number(valorAseo || 0);
  const totalMostrado = concepto?.requiere_reserva ? totalAlquiler : Number(valor || 0);
  const necesitaComprobante = medio !== "EFECTIVO" && !comprobante.trim() && !soporte;

  const errores = useMemo(() => {
    if (!concepto) return ["Elija un concepto"];
    const e: string[] = [];
    if (pagador.trim().length < 2) e.push("Escriba el nombre de quien paga");
    if (concepto.requiere_vehiculo && !/^[A-Z0-9]{5,7}$/.test(placa.replace(/[\s.-]/g, "").toUpperCase())) e.push("Placa inválida");
    if (concepto.requiere_vehiculo && (!ingreso || !salida || salida <= ingreso)) e.push("Revise las horas");
    if (concepto.requiere_reserva && (!zonaId || !fechaEvento)) e.push("Elija zona y fecha del evento");
    if (concepto.requiere_reserva && Number(valorAlquiler) <= 0) e.push("Valor del alquiler");
    if (!concepto.requiere_reserva && Number(valor) <= 0) e.push("Indique el valor recibido");
    if (necesitaComprobante) e.push("Número de comprobante o soporte");
    return e;
  }, [concepto, pagador, placa, ingreso, salida, zonaId, fechaEvento, valorAlquiler, valor, necesitaComprobante]);

  function limpiar() {
    setPagador(concepto?.requiere_vehiculo ? "Visitante" : "");
    setIdentificacion("");
    setUnidadId("");
    setComprobante("");
    setSoporte(null);
    setObservaciones("");
    setPlaca("");
    setZonaId("");
    setHoraInicio("");
    setHoraFin("");
    if (concepto) elegir(concepto);
  }

  async function registrar() {
    if (!concepto || errores.length) return;
    setEnviando(true);
    let reservaCreada: Reserva | null = null;
    try {
      const cuerpo: Record<string, unknown> = {
        concepto_id: concepto.id,
        medio_pago: medio,
        nombre_pagador: pagador.trim(),
        identificacion_pagador: identificacion.trim() || null,
        unidad_id: unidadId || null,
        numero_comprobante: comprobante.trim() || null,
        soporte_key: soporte,
        observaciones: observaciones.trim() || null,
      };
      if (concepto.requiere_vehiculo) {
        cuerpo.parqueadero = {
          placa_vehiculo: placa,
          hora_ingreso: desdeDatetimeLocal(ingreso),
          hora_salida: desdeDatetimeLocal(salida),
        };
        cuerpo.valor_recibido = valor;
      } else if (concepto.requiere_reserva) {
        reservaCreada = await api<Reserva>(`${b}/reservas`, {
          method: "POST",
          json: {
            zona_id: zonaId,
            solicitante: pagador.trim(),
            fecha_evento: fechaEvento,
            unidad_id: unidadId || null,
            hora_inicio: horaInicio || null,
            hora_fin: horaFin || null,
          },
        });
        cuerpo.reserva_id = reservaCreada.id;
        const desglose = [{ concepto_id: concepto.id, valor: valorAlquiler, descripcion: "Valor alquiler" }];
        if (Number(valorAseo) > 0 && aseo) desglose.push({ concepto_id: aseo.id, valor: valorAseo, descripcion: "Valor aseo" });
        cuerpo.desglose = desglose;
      } else {
        cuerpo.valor_recibido = valor;
      }
      const r = await api<RecaudoDetalle>(b, { method: "POST", json: cuerpo });
      setUltimo(r);
      toast.success(`Recaudo #${r.consecutivo} registrado por ${pesos(r.valor_recibido)}`);
      void refrescarCaja();
      limpiar();
    } catch (e) {
      // Si el cobro falló, la reserva recién creada no debe quedar ocupando la zona
      if (reservaCreada) {
        await api(`${b}/reservas/${reservaCreada.id}`, { method: "PATCH", json: { estado: "CANCELADA" } }).catch(() => undefined);
      }
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Registrar recaudo"
        description="Parqueadero de visitantes, alquiler de zonas, aseo y otros ingresos."
        actions={
          caja && (
            <Link
              href={`/${tenant.tenant_slug}/recaudos/caja`}
              className="hidden items-center gap-2 rounded-md border bg-card px-3 py-1.5 text-sm transition-colors hover:bg-accent sm:flex"
            >
              <Wallet className="size-4 text-muted-foreground" />
              En su caja: <span className="font-semibold tabular-nums">{pesos(caja.total_efectivo)}</span>
              <span className="text-muted-foreground">({caja.cantidad})</span>
            </Link>
          )
        }
      />

      <div className="grid gap-6 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          {/* 1. Concepto */}
          <section>
            <h2 className="mb-2 text-sm font-semibold">1. ¿Qué se está cobrando?</h2>
            {!conceptos ? (
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} className="h-20" />
                ))}
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4" role="radiogroup" aria-label="Concepto">
                {conceptos.map((c) => {
                  const Icono = ICONO[c.codigo] ?? Receipt;
                  const activo = c.id === conceptoId;
                  return (
                    <button
                      key={c.id}
                      type="button"
                      role="radio"
                      aria-checked={activo}
                      onClick={() => elegir(c)}
                      className={cn(
                        "flex items-start gap-3 rounded-lg border bg-card p-3 text-left transition-colors",
                        activo ? "border-primary ring-2 ring-primary/20" : "hover:border-primary/40 hover:bg-accent/40",
                      )}
                    >
                      <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-md", activo ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground")}>
                        <Icono className="size-4.5" />
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm leading-tight font-medium">{c.nombre}</span>
                        <span className="mt-0.5 block text-xs text-muted-foreground">{tarifaTexto(c)}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {concepto && (
            <>
              {/* 2. Datos del cobro */}
              <section className="rounded-lg border bg-card p-4">
                <h2 className="mb-3 text-sm font-semibold">2. Datos del cobro</h2>
                {concepto.requiere_vehiculo && (
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="placa">Placa</Label>
                      <Input
                        id="placa"
                        value={placa}
                        onChange={(e) => setPlaca(e.target.value.toUpperCase())}
                        placeholder="ABC123"
                        className="font-mono tracking-wider uppercase"
                        autoFocus
                        maxLength={8}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="ingreso">Ingreso</Label>
                      <input id="ingreso" type="datetime-local" value={ingreso} onChange={(e) => setIngreso(e.target.value)} className={campoClase()} />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="salida">Salida</Label>
                      <input id="salida" type="datetime-local" value={salida} onChange={(e) => setSalida(e.target.value)} className={campoClase()} />
                    </div>
                    <p className="text-sm text-muted-foreground sm:col-span-3">
                      {cotizacion ? (
                        <>
                          Tiempo: <span className="font-medium text-foreground">{duracion(cotizacion.minutos)}</span> ·{" "}
                          {cotizacion.fracciones} {cotizacion.fracciones === 1 ? "fracción" : "fracciones"} · tarifa sugerida{" "}
                          <span className="font-medium text-foreground">{pesos(cotizacion.tarifa_sugerida)}</span>
                        </>
                      ) : (
                        "Indique las horas para calcular la tarifa."
                      )}
                    </p>
                  </div>
                )}

                {concepto.requiere_reserva && (
                  <div className="grid gap-3 sm:grid-cols-4">
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label htmlFor="zona">Zona social</Label>
                      <select id="zona" value={zonaId} onChange={(e) => setZonaId(e.target.value)} className={campoClase()}>
                        <option value="">Elija una zona…</option>
                        {zonas?.map((z) => (
                          <option key={z.id} value={z.id}>
                            {z.nombre}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label htmlFor="fecha-evento">Fecha del evento</Label>
                      <input id="fecha-evento" type="date" value={fechaEvento} onChange={(e) => setFechaEvento(e.target.value)} className={campoClase()} />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="h-ini">Desde (opcional)</Label>
                      <input id="h-ini" type="time" value={horaInicio} onChange={(e) => setHoraInicio(e.target.value)} className={campoClase()} />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="h-fin">Hasta (opcional)</Label>
                      <input id="h-fin" type="time" value={horaFin} onChange={(e) => setHoraFin(e.target.value)} className={campoClase()} />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="v-alquiler">Valor alquiler</Label>
                      <Input id="v-alquiler" inputMode="numeric" value={valorAlquiler} onChange={(e) => setValorAlquiler(e.target.value.replace(/\D/g, ""))} />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="v-aseo">Valor aseo</Label>
                      <Input id="v-aseo" inputMode="numeric" value={valorAseo} onChange={(e) => setValorAseo(e.target.value.replace(/\D/g, ""))} />
                    </div>
                    <p className="text-xs text-muted-foreground sm:col-span-4">
                      Se registra como una sola transacción con dos rubros, y la reserva queda creada para esa fecha.
                    </p>
                  </div>
                )}

                {!concepto.requiere_reserva && (
                  <div className={cn("mt-3 max-w-xs space-y-1.5", !concepto.requiere_vehiculo && "mt-0")}>
                    <Label htmlFor="valor">Valor recibido</Label>
                    <Input
                      id="valor"
                      inputMode="numeric"
                      value={valor}
                      onChange={(e) => setValor(e.target.value.replace(/\D/g, ""))}
                      autoFocus={!concepto.requiere_vehiculo}
                    />
                    {cotizacion && Number(valor) !== Number(cotizacion.tarifa_sugerida) && Number(valor) > 0 && (
                      <p className="text-xs text-warning">Difiere de la tarifa sugerida: explique el motivo en observaciones.</p>
                    )}
                  </div>
                )}
              </section>

              {/* 3. Quién paga y cómo */}
              <section className="rounded-lg border bg-card p-4">
                <h2 className="mb-3 text-sm font-semibold">3. Quién paga y cómo</h2>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="pagador">Nombre de quien paga</Label>
                    <Input id="pagador" value={pagador} onChange={(e) => setPagador(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="ident">Identificación (opcional)</Label>
                    <Input id="ident" value={identificacion} onChange={(e) => setIdentificacion(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="unidad">Unidad</Label>
                    <select id="unidad" value={unidadId} onChange={(e) => setUnidadId(e.target.value)} className={campoClase()}>
                      <option value="">Visitante externo (sin unidad)</option>
                      {unidades?.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.etiqueta}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="mt-4">
                  <Label>Medio de pago</Label>
                  <div className="mt-1.5 inline-flex rounded-md border bg-secondary/50 p-0.5" role="radiogroup" aria-label="Medio de pago">
                    {(Object.keys(MEDIO) as MedioPago[]).map((m) => (
                      <button
                        key={m}
                        type="button"
                        role="radio"
                        aria-checked={medio === m}
                        onClick={() => setMedio(m)}
                        className={cn(
                          "rounded px-3 py-1.5 text-sm transition-colors",
                          medio === m ? "bg-card font-medium shadow-sm" : "text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {MEDIO[m]}
                      </button>
                    ))}
                  </div>
                  {medio !== "EFECTIVO" && (
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      Quedará <strong>por verificar</strong> hasta que contabilidad lo encuentre en el extracto bancario.
                    </p>
                  )}
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="comprobante">
                      N.° de comprobante {medio === "EFECTIVO" ? "(opcional)" : ""}
                    </Label>
                    <Input id="comprobante" value={comprobante} onChange={(e) => setComprobante(e.target.value)} placeholder={medio === "EFECTIVO" ? "Recibo de caja" : "Referencia de la transacción"} />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Soporte</Label>
                    <SoporteInput tenantId={tenant.tenant_id} valor={soporte} onCambio={setSoporte} />
                  </div>
                  <div className="space-y-1.5 sm:col-span-2">
                    <Label htmlFor="obs">Observaciones (opcional)</Label>
                    <Textarea id="obs" rows={2} value={observaciones} onChange={(e) => setObservaciones(e.target.value)} />
                  </div>
                </div>
              </section>
            </>
          )}
        </div>

        {/* Resumen y confirmación */}
        <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">Total a recibir</p>
            <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">{pesos(totalMostrado || 0)}</p>
            {concepto?.requiere_reserva && totalAlquiler > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                Alquiler {pesos(valorAlquiler || 0)} + aseo {pesos(valorAseo || 0)}
              </p>
            )}
            <p className="mt-2 text-sm">
              {concepto ? concepto.nombre : "Elija un concepto"} · {MEDIO[medio]}
            </p>
            {concepto && errores.length > 0 && (
              <ul className="mt-3 space-y-0.5 text-xs text-muted-foreground">
                {errores.map((e) => (
                  <li key={e}>· Falta: {e.toLowerCase()}</li>
                ))}
              </ul>
            )}
            <Button className="mt-4 w-full" disabled={!concepto || errores.length > 0 || enviando} onClick={registrar}>
              {enviando && <Loader2 className="size-4 animate-spin" />}
              Registrar recaudo
            </Button>
          </div>

          {ultimo && (
            <div className="rounded-lg border border-success/30 bg-success-soft/50 p-4 text-sm">
              <p className="flex items-center gap-2 font-medium text-success">
                <CheckCircle2 className="size-4" /> Último registro: #{ultimo.consecutivo}
              </p>
              <p className="mt-1">
                {ultimo.concepto} · {pesos(ultimo.valor_recibido)}
                {ultimo.placa && ` · ${ultimo.placa}`}
              </p>
              <p className="text-xs text-muted-foreground">
                {ultimo.nombre_pagador} · {MEDIO[ultimo.medio_pago]}
              </p>
              <Link href={`/${tenant.tenant_slug}/recaudos/movimientos?id=${ultimo.id}`} className="mt-2 inline-block text-xs font-medium text-primary hover:underline">
                Ver detalle
              </Link>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
