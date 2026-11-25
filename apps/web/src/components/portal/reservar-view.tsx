"use client";

import { CalendarCheck, ChevronLeft, ChevronRight, Clock, Loader2, PartyPopper, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, MotivoDialog, mensajeError, Seccion, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import { basePortal, hora, type Ocupado, type ReservaPortal, type Zona } from "@/lib/portal";
import { fechaCorta, hoyBogota, pesos } from "@/lib/recaudos";
import type { UnidadDetalle } from "@/lib/unidades";
import { cn } from "@/lib/utils";

import { EstadoReservaBadge, useRefrescarPortal } from "./comunes";

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const DIAS = ["L", "M", "M", "J", "V", "S", "D"];

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function sumarDias(fecha: string, n: number): string {
  const [a, m, d] = fecha.split("-").map(Number) as [number, number, number];
  return iso(new Date(a, m - 1, d + n));
}

export function ReservarView() {
  const { tenant } = useTenant();
  const b = basePortal(tenant.tenant_id);
  const refrescar = useRefrescarPortal();
  const residente = tenant.role === "RESIDENTE";
  const { data: zonas } = useSWR<Zona[]>(residente ? `${b}/zonas` : null, fetcher);
  const { data: mias, mutate: refrescarMias } = useSWR<ReservaPortal[]>(residente ? `${b}/reservas` : null, fetcher);
  const { data: unidades } = useSWR<UnidadDetalle[]>(residente ? `/tenants/${tenant.tenant_id}/mi-unidad` : null, fetcher);
  const [zonaId, setZonaId] = useState<string | null>(null);
  const [cancelar, setCancelar] = useState<ReservaPortal | null>(null);
  const zona = zonas?.find((z) => z.id === zonaId) ?? null;
  const hoy = hoyBogota();

  useEffect(() => {
    if (!zonaId && zonas?.length) setZonaId(zonas[0]!.id);
  }, [zonas, zonaId]);

  if (!residente) return <SinAcceso texto="Las reservas desde el portal son para residentes. El personal las gestiona en «Reservas»." />;
  const vigentes = (mias ?? []).filter((r) => r.fecha_evento >= hoy && (r.estado === "SOLICITADA" || r.estado === "CONFIRMADA"));
  const anteriores = (mias ?? []).filter((r) => !vigentes.includes(r)).slice(-5).reverse();

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Reservar zonas sociales" description="Consulte la disponibilidad y reserve el salón social, el BBQ u otras zonas." />
      <div className="mx-auto w-full max-w-5xl space-y-5 p-4 sm:p-6">
        {vigentes.length > 0 && (
          <Seccion titulo="Mis próximas reservas">
            <ul className="divide-y">
              {vigentes.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
                  <CalendarCheck className="size-4 text-primary" />
                  <span className="font-medium">{r.zona}</span>
                  <span>
                    {fechaCorta(r.fecha_evento)} · {hora(r.hora_inicio)} a {hora(r.hora_fin)}
                  </span>
                  <EstadoReservaBadge estado={r.estado} />
                  {r.tarifa_total && Number(r.tarifa_total) > 0 && <span className="text-muted-foreground">Valor {pesos(r.tarifa_total)}</span>}
                  <Button variant="ghost" size="sm" className="ml-auto text-destructive" onClick={() => setCancelar(r)}>
                    Cancelar
                  </Button>
                </li>
              ))}
            </ul>
          </Seccion>
        )}

        {!zonas ? (
          <Skeleton className="h-64" />
        ) : !zonas.length ? (
          <div className="rounded-lg border bg-card">
            <Vacio icono={PartyPopper} titulo="No hay zonas reservables desde el portal" texto="Consulte a la administración." />
          </div>
        ) : (
          <>
            <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Zona">
              {zonas.map((z) => (
                <button
                  key={z.id}
                  type="button"
                  role="radio"
                  aria-checked={zonaId === z.id}
                  onClick={() => setZonaId(z.id)}
                  className={cn("rounded-lg border bg-card p-3 text-left transition-colors", zonaId === z.id ? "border-primary ring-2 ring-primary/20" : "hover:bg-accent/40")}
                >
                  <span className="block font-medium">{z.nombre}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {z.capacidad ? `Hasta ${z.capacidad} personas · ` : ""}
                    {Number(z.tarifa_alquiler ?? 0) + Number(z.tarifa_aseo ?? 0) > 0 ? pesos(Number(z.tarifa_alquiler ?? 0) + Number(z.tarifa_aseo ?? 0)) : "Sin costo"}
                  </span>
                </button>
              ))}
            </div>
            {zona && <Reservador zona={zona} unidades={unidades ?? []} onReservada={() => { void refrescarMias(); void refrescar(tenant.tenant_id); }} />}
          </>
        )}

        {anteriores.length > 0 && (
          <Seccion titulo="Historial">
            <ul className="divide-y text-sm">
              {anteriores.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
                  <span>{r.zona}</span>
                  <span className="text-muted-foreground">{fechaCorta(r.fecha_evento)}</span>
                  <EstadoReservaBadge estado={r.estado} />
                  {r.motivo_decision && <span className="w-full text-xs text-muted-foreground">{r.motivo_decision}</span>}
                </li>
              ))}
            </ul>
          </Seccion>
        )}
      </div>
      <MotivoDialog
        abierto={!!cancelar}
        onCambio={(v) => !v && setCancelar(null)}
        titulo="Cancelar la reserva"
        descripcion={cancelar ? `${cancelar.zona} el ${fechaCorta(cancelar.fecha_evento)}. La franja queda libre para otros residentes.` : ""}
        boton="Cancelar reserva"
        minimo={3}
        onConfirmar={async (motivo) => {
          if (!cancelar) return;
          await api(`${b}/reservas/${cancelar.id}/cancelar`, { method: "POST", json: { motivo } });
          toast.success("Reserva cancelada");
          void refrescarMias();
          void refrescar(tenant.tenant_id);
        }}
      />
    </div>
  );
}

function Reservador({ zona, unidades, onReservada }: { zona: Zona; unidades: UnidadDetalle[]; onReservada: () => void }) {
  const { tenant } = useTenant();
  const b = basePortal(tenant.tenant_id);
  const hoy = hoyBogota();
  const minimo = sumarDias(hoy, zona.anticipacion_min_dias);
  const maximo = sumarDias(hoy, zona.anticipacion_max_dias);
  const [mes, setMes] = useState(() => minimo.slice(0, 7));
  const [fecha, setFecha] = useState<string | null>(null);
  const [inicio, setInicio] = useState(hora(zona.hora_apertura));
  const [fin, setFin] = useState("");
  const [asistentes, setAsistentes] = useState("");
  const [obs, setObs] = useState("");
  const [unidad, setUnidad] = useState("");
  const [enviando, setEnviando] = useState(false);

  const [a, m] = mes.split("-").map(Number) as [number, number];
  const primero = `${mes}-01`;
  const ultimo = iso(new Date(a, m, 0));
  const { data: ocupado } = useSWR<Ocupado[]>(`${b}/zonas/${zona.id}/disponibilidad?desde=${primero}&hasta=${ultimo}`, fetcher);
  const porDia = useMemo(() => {
    const mapa = new Map<string, Ocupado[]>();
    for (const o of ocupado ?? []) mapa.set(o.fecha_evento, [...(mapa.get(o.fecha_evento) ?? []), o]);
    return mapa;
  }, [ocupado]);

  useEffect(() => {
    setFecha(null);
    setInicio(hora(zona.hora_apertura));
    setFin("");
    setMes(sumarDias(hoyBogota(), zona.anticipacion_min_dias).slice(0, 7));
  }, [zona.id, zona.hora_apertura, zona.anticipacion_min_dias]);
  useEffect(() => {
    if (!unidad && unidades.length) setUnidad(unidades[0]!.id);
  }, [unidad, unidades]);

  const dias = new Date(a, m, 0).getDate();
  const desfase = (new Date(a, m - 1, 1).getDay() + 6) % 7; // lunes = 0
  const delDia = fecha ? porDia.get(fecha) ?? [] : [];
  const choca = delDia.some((o) => !o.hora_inicio || !o.hora_fin || (inicio && fin && o.hora_inicio.slice(0, 5) < fin && o.hora_fin.slice(0, 5) > inicio));
  const valido = fecha && unidad && inicio && fin && fin > inicio && !choca;

  async function reservar() {
    setEnviando(true);
    try {
      const r = await api<ReservaPortal>(`${b}/reservas`, {
        method: "POST",
        json: { zona_id: zona.id, unidad_id: unidad, fecha_evento: fecha, hora_inicio: inicio, hora_fin: fin, numero_asistentes: asistentes ? Number(asistentes) : null, observaciones: obs.trim() || null },
      });
      toast.success(r.estado === "CONFIRMADA" ? "¡Reserva confirmada!" : "Solicitud enviada: la administración le avisará por correo cuando la apruebe");
      setFecha(null);
      setFin("");
      setObs("");
      onReservada();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  const mover = (n: number) => setMes(iso(new Date(a, m - 1 + n, 1)).slice(0, 7));

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <Seccion
        titulo={`${MESES[m - 1]?.replace(/^./, (c) => c.toUpperCase())} de ${a}`}
        descripcion={`Puede reservar entre el ${fechaCorta(minimo)} y el ${fechaCorta(maximo)}.`}
        acciones={
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" onClick={() => mover(-1)} disabled={primero <= hoy.slice(0, 8) + "01"} aria-label="Mes anterior">
              <ChevronLeft className="size-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => mover(1)} disabled={ultimo >= maximo} aria-label="Mes siguiente">
              <ChevronRight className="size-4" />
            </Button>
          </div>
        }
      >
        <div className="p-3">
          <div className="grid grid-cols-7 gap-1 text-center text-xs text-muted-foreground">
            {DIAS.map((d, i) => (
              <span key={i}>{d}</span>
            ))}
          </div>
          <div className="mt-1 grid grid-cols-7 gap-1">
            {Array.from({ length: desfase }).map((_, i) => (
              <span key={`v${i}`} />
            ))}
            {Array.from({ length: dias }, (_, i) => {
              const f = `${mes}-${String(i + 1).padStart(2, "0")}`;
              const fuera = f < minimo || f > maximo;
              const ocup = porDia.get(f) ?? [];
              const todoElDia = ocup.some((o) => !o.hora_inicio);
              return (
                <button
                  key={f}
                  type="button"
                  disabled={fuera || todoElDia}
                  onClick={() => setFecha(f)}
                  aria-pressed={fecha === f}
                  aria-label={`${i + 1} de ${MESES[m - 1]}${ocup.length ? `, ${ocup.length} reserva(s)` : ", libre"}`}
                  className={cn(
                    "flex aspect-square flex-col items-center justify-center rounded-md border text-sm transition-colors",
                    fuera ? "border-transparent text-muted-foreground/40" : "hover:border-primary/50",
                    fecha === f && "border-primary bg-primary text-primary-foreground",
                  )}
                >
                  {i + 1}
                  {!fuera && ocup.length > 0 && (
                    <span className={cn("mt-0.5 h-1 w-4 rounded-full", fecha === f ? "bg-primary-foreground/70" : ocup.some((o) => o.propia) ? "bg-primary" : "bg-warning")} />
                  )}
                </button>
              );
            })}
          </div>
          <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1 w-4 rounded-full bg-warning" /> Tiene reservas (hay horas ocupadas)
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1 w-4 rounded-full bg-primary" /> Su reserva
            </span>
          </p>
        </div>
      </Seccion>

      <div className="space-y-3">
        <div className="space-y-2 rounded-lg border bg-card p-4 text-sm">
          <p className="font-semibold">{zona.nombre}</p>
          {zona.descripcion && <p className="text-muted-foreground">{zona.descripcion}</p>}
          <p className="flex items-center gap-1.5 text-muted-foreground">
            <Clock className="size-4" /> De {hora(zona.hora_apertura)} a {hora(zona.hora_cierre)}
          </p>
          {zona.capacidad && (
            <p className="flex items-center gap-1.5 text-muted-foreground">
              <Users className="size-4" /> Hasta {zona.capacidad} personas
            </p>
          )}
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
            <li>{zona.requiere_aprobacion ? "La administración aprueba cada solicitud" : "Se confirma de inmediato"}</li>
            {zona.requiere_paz_y_salvo && <li>Requiere estar al día con la administración</li>}
            <li>Máximo {zona.max_reservas_mes_unidad} por mes por unidad</li>
          </ul>
          {zona.reglas && <p className="rounded-md bg-muted px-2 py-1.5 text-xs">{zona.reglas}</p>}
        </div>

        {fecha ? (
          <div className="space-y-3 rounded-lg border bg-card p-4">
            <p className="text-sm font-semibold">Reservar el {fechaCorta(fecha)}</p>
            {delDia.length > 0 && (
              <p className="text-xs text-warning">
                Ocupado: {delDia.map((o) => (o.hora_inicio ? `${hora(o.hora_inicio)}–${hora(o.hora_fin)}` : "todo el día")).join(", ")}
              </p>
            )}
            <div className="grid grid-cols-2 gap-2">
              <Campo label="Desde">
                <input type="time" value={inicio} min={hora(zona.hora_apertura)} max={hora(zona.hora_cierre)} onChange={(e) => setInicio(e.target.value)} className={campoClase()} />
              </Campo>
              <Campo label="Hasta">
                <input type="time" value={fin} min={inicio} max={hora(zona.hora_cierre)} onChange={(e) => setFin(e.target.value)} className={campoClase(choca)} />
              </Campo>
            </div>
            {choca && <p className="text-xs text-destructive">Ese horario se cruza con otra reserva.</p>}
            {unidades.length > 1 && (
              <Campo label="Unidad">
                <select value={unidad} onChange={(e) => setUnidad(e.target.value)} className={campoClase()}>
                  {unidades.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.etiqueta}
                    </option>
                  ))}
                </select>
              </Campo>
            )}
            <Campo label="Número de asistentes">
              <Input type="number" min={1} max={zona.capacidad ?? undefined} value={asistentes} onChange={(e) => setAsistentes(e.target.value)} />
            </Campo>
            <Campo label="Motivo u observaciones (opcional)">
              <Input value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Cumpleaños, reunión familiar…" />
            </Campo>
            <Button className="w-full" disabled={!valido || enviando} onClick={reservar}>
              {enviando && <Loader2 className="size-4 animate-spin" />}
              {zona.requiere_aprobacion ? "Solicitar reserva" : "Reservar"}
            </Button>
          </div>
        ) : (
          <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">Elija un día en el calendario.</p>
        )}
      </div>
    </div>
  );
}
