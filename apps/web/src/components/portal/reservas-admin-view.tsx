"use client";

import { CalendarClock, Check, Loader2, Settings2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo, textareaClase } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, MotivoDialog, mensajeError, Seccion, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import { basePortal, hora, puedePortal, type ReservaPortal, type Zona } from "@/lib/portal";
import { fechaCorta, hoyBogota, pesos } from "@/lib/recaudos";

import { EstadoReservaBadge, useRefrescarPortal } from "./comunes";

export function ReservasAdminView() {
  const { tenant } = useTenant();
  const b = basePortal(tenant.tenant_id);
  const permitido = puedePortal(tenant.role, "verReservas");
  const decide = puedePortal(tenant.role, "decidirReserva");
  const hoy = hoyBogota();
  const { data: reservas } = useSWR<ReservaPortal[]>(permitido ? `${b}/reservas?desde=${hoy}` : null, fetcher);
  const { data: zonas } = useSWR<Zona[]>(permitido ? `${b}/zonas` : null, fetcher);
  const refrescar = useRefrescarPortal();
  const [rechazar, setRechazar] = useState<ReservaPortal | null>(null);
  const [zona, setZona] = useState<Zona | null>(null);
  const [aprobando, setAprobando] = useState<string | null>(null);

  if (!permitido) return <SinAcceso />;
  const solicitadas = (reservas ?? []).filter((r) => r.estado === "SOLICITADA");
  const proximas = (reservas ?? []).filter((r) => r.estado === "CONFIRMADA");

  async function aprobar(r: ReservaPortal) {
    setAprobando(r.id);
    try {
      await api(`${b}/reservas/${r.id}/decidir`, { method: "POST", json: { aprobar: true } });
      toast.success(`Reserva de ${r.solicitante} aprobada: se le avisó por correo`);
      void refrescar(tenant.tenant_id);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setAprobando(null);
    }
  }

  const fila = (r: ReservaPortal, acciones: boolean) => (
    <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          {r.zona} · {fechaCorta(r.fecha_evento)} · {hora(r.hora_inicio)} a {hora(r.hora_fin)}
        </p>
        <p className="text-xs text-muted-foreground">
          {r.solicitante}
          {r.unidad && ` (${r.unidad})`}
          {r.numero_asistentes && ` · ${r.numero_asistentes} personas`}
          {r.solicitada_en_portal ? " · desde el portal" : " · registrada por recepción"}
          {r.observaciones && ` · «${r.observaciones}»`}
        </p>
      </div>
      {r.tarifa_total && Number(r.tarifa_total) > 0 && <span className="text-muted-foreground tabular-nums">{pesos(r.tarifa_total)}</span>}
      {acciones && decide ? (
        <div className="flex gap-1">
          <Button size="sm" disabled={aprobando === r.id} onClick={() => void aprobar(r)}>
            {aprobando === r.id ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />} Aprobar
          </Button>
          <Button size="sm" variant="outline" onClick={() => setRechazar(r)}>
            <X className="size-4" /> Rechazar
          </Button>
        </div>
      ) : (
        <EstadoReservaBadge estado={r.estado} />
      )}
    </li>
  );

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Reservas de zonas sociales" description="Solicitudes de los residentes, próximas reservas y reglas de cada zona." />
      <div className="space-y-4 p-4 sm:p-6">
        {!reservas ? (
          <Skeleton className="h-48" />
        ) : (
          <>
            <Seccion titulo={`Por aprobar (${solicitadas.length})`} descripcion="El residente recibe un correo con la decisión. El alquiler se cobra en Recaudos asociándolo a la reserva.">
              {!solicitadas.length ? <Vacio icono={Check} titulo="No hay solicitudes pendientes" /> : <ul className="divide-y">{solicitadas.map((r) => fila(r, true))}</ul>}
            </Seccion>
            <Seccion titulo="Próximas reservas confirmadas">
              {!proximas.length ? <Vacio icono={CalendarClock} titulo="No hay reservas confirmadas" /> : <ul className="divide-y">{proximas.map((r) => fila(r, false))}</ul>}
            </Seccion>
          </>
        )}

        <Seccion titulo="Zonas y sus reglas" descripcion="Qué se puede reservar desde el portal y con qué condiciones.">
          {!zonas ? (
            <Skeleton className="h-24" />
          ) : (
            <ul className="divide-y">
              {zonas.map((z) => (
                <li key={z.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {z.nombre}
                      {!z.reservable_residentes && <span className="ml-2 text-xs font-normal text-muted-foreground">(no se reserva desde el portal)</span>}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {hora(z.hora_apertura)}–{hora(z.hora_cierre)} · con {z.anticipacion_min_dias} a {z.anticipacion_max_dias} días de anticipación · máx. {z.max_reservas_mes_unidad}/mes por unidad
                      {z.capacidad && ` · ${z.capacidad} personas`}
                      {z.requiere_paz_y_salvo && " · exige estar al día"}
                      {z.requiere_aprobacion ? " · con aprobación" : " · confirmación automática"}
                    </p>
                  </div>
                  {puedePortal(tenant.role, "configurarZonas") && (
                    <Button size="sm" variant="outline" onClick={() => setZona(z)}>
                      <Settings2 className="size-4" /> Reglas
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Seccion>
      </div>

      <MotivoDialog
        abierto={!!rechazar}
        onCambio={(v) => !v && setRechazar(null)}
        titulo="Rechazar la solicitud"
        descripcion={rechazar ? `${rechazar.zona} el ${fechaCorta(rechazar.fecha_evento)}, de ${rechazar.solicitante}. El residente verá el motivo.` : ""}
        boton="Rechazar"
        minimo={5}
        onConfirmar={async (motivo) => {
          if (!rechazar) return;
          await api(`${b}/reservas/${rechazar.id}/decidir`, { method: "POST", json: { aprobar: false, motivo } });
          toast.success("Solicitud rechazada");
          void refrescar(tenant.tenant_id);
        }}
      />
      <ReglasDialog zona={zona} onCerrar={() => setZona(null)} onGuardada={() => refrescar(tenant.tenant_id)} />
    </div>
  );
}

function ReglasDialog({ zona, onCerrar, onGuardada }: { zona: Zona | null; onCerrar: () => void; onGuardada: () => void }) {
  const { tenant } = useTenant();
  const [f, setF] = useState<Record<string, string | boolean>>({});
  const [enviando, setEnviando] = useState(false);
  useEffect(() => {
    if (!zona) return;
    setF({
      descripcion: zona.descripcion ?? "",
      capacidad: zona.capacidad ? String(zona.capacidad) : "",
      reglas: zona.reglas ?? "",
      hora_apertura: hora(zona.hora_apertura),
      hora_cierre: hora(zona.hora_cierre),
      anticipacion_min_dias: String(zona.anticipacion_min_dias),
      anticipacion_max_dias: String(zona.anticipacion_max_dias),
      max_reservas_mes_unidad: String(zona.max_reservas_mes_unidad),
      requiere_paz_y_salvo: zona.requiere_paz_y_salvo,
      requiere_aprobacion: zona.requiere_aprobacion,
      reservable_residentes: zona.reservable_residentes,
    });
  }, [zona]);
  const set = (k: string, v: string | boolean) => setF((x) => ({ ...x, [k]: v }));
  const txt = (k: string) => String(f[k] ?? "");

  async function guardar() {
    if (!zona) return;
    setEnviando(true);
    try {
      await api(`${basePortal(tenant.tenant_id)}/zonas/${zona.id}`, {
        method: "PATCH",
        json: {
          descripcion: txt("descripcion").trim() || null,
          capacidad: txt("capacidad") ? Number(txt("capacidad")) : null,
          reglas: txt("reglas").trim() || null,
          hora_apertura: txt("hora_apertura"),
          hora_cierre: txt("hora_cierre"),
          anticipacion_min_dias: Number(txt("anticipacion_min_dias")),
          anticipacion_max_dias: Number(txt("anticipacion_max_dias")),
          max_reservas_mes_unidad: Number(txt("max_reservas_mes_unidad")),
          requiere_paz_y_salvo: !!f.requiere_paz_y_salvo,
          requiere_aprobacion: !!f.requiere_aprobacion,
          reservable_residentes: !!f.reservable_residentes,
        },
      });
      toast.success("Reglas guardadas");
      onGuardada();
      onCerrar();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  const casilla = (k: string, label: string, ayuda: string) => (
    <label className="flex items-start gap-2 text-sm">
      <input type="checkbox" checked={!!f[k]} onChange={(e) => set(k, e.target.checked)} className="mt-0.5 size-4" />
      <span>
        {label}
        <span className="block text-xs text-muted-foreground">{ayuda}</span>
      </span>
    </label>
  );

  return (
    <Dialog open={!!zona} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Reglas de {zona?.nombre}</DialogTitle>
          <DialogDescription>Las tarifas se configuran en Recaudos → Configuración.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo label="Descripción" className="sm:col-span-2">
            <Input value={txt("descripcion")} onChange={(e) => set("descripcion", e.target.value)} />
          </Campo>
          <Campo label="Abre">
            <input type="time" value={txt("hora_apertura")} onChange={(e) => set("hora_apertura", e.target.value)} className={campoClase()} />
          </Campo>
          <Campo label="Cierra">
            <input type="time" value={txt("hora_cierre")} onChange={(e) => set("hora_cierre", e.target.value)} className={campoClase()} />
          </Campo>
          <Campo label="Anticipación mínima (días)">
            <Input type="number" min={0} value={txt("anticipacion_min_dias")} onChange={(e) => set("anticipacion_min_dias", e.target.value)} />
          </Campo>
          <Campo label="Anticipación máxima (días)">
            <Input type="number" min={1} value={txt("anticipacion_max_dias")} onChange={(e) => set("anticipacion_max_dias", e.target.value)} />
          </Campo>
          <Campo label="Reservas por mes por unidad">
            <Input type="number" min={1} value={txt("max_reservas_mes_unidad")} onChange={(e) => set("max_reservas_mes_unidad", e.target.value)} />
          </Campo>
          <Campo label="Capacidad (personas)">
            <Input type="number" min={1} value={txt("capacidad")} onChange={(e) => set("capacidad", e.target.value)} />
          </Campo>
          <Campo label="Reglas de uso" className="sm:col-span-2">
            <textarea value={txt("reglas")} onChange={(e) => set("reglas", e.target.value)} rows={2} className={textareaClase()} />
          </Campo>
          <div className="space-y-2 sm:col-span-2">
            {casilla("reservable_residentes", "Se reserva desde el portal", "Si no, solo la registra recepción.")}
            {casilla("requiere_aprobacion", "Requiere aprobación de la administración", "Si no, la reserva queda confirmada de inmediato.")}
            {casilla("requiere_paz_y_salvo", "Exige estar al día con la cartera", "La unidad no puede tener saldo vencido.")}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button disabled={enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar reglas
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
