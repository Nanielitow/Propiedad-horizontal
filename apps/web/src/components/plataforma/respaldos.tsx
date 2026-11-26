"use client";

import { AlertTriangle, DatabaseBackup, Download, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Etiqueta } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { api, ApiError, fetcher } from "@/lib/api";

interface Respaldo {
  clave: string;
  tipo: "diario" | "mensual";
  tamano_bytes: number;
  fecha: string;
}
interface Respaldos {
  respaldos: Respaldo[];
  ultimo: string | null;
  al_dia: boolean;
}

const URL = "/plataforma/respaldos";

function tamano(b: number): string {
  if (b >= 1_000_000) return `${(b / 1_000_000).toLocaleString("es-CO", { maximumFractionDigits: 1 })} MB`;
  return `${Math.max(1, Math.round(b / 1000))} KB`;
}
function fecha(iso: string): string {
  return new Date(iso).toLocaleString("es-CO", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
}

/** Respaldos diarios de la base de datos: estado, historial, respaldar ahora y descargar. */
export function RespaldosSeccion() {
  const [esperando, setEsperando] = useState(false);
  const { data, mutate, isLoading } = useSWR<Respaldos>(URL, fetcher, { refreshInterval: esperando ? 10_000 : 0 });
  const [descargando, setDescargando] = useState<string | null>(null);
  const [pidiendo, setPidiendo] = useState(false);

  async function respaldarAhora() {
    setPidiendo(true);
    const antes = data?.respaldos[0]?.clave;
    try {
      const r = await api<{ detail: string }>(URL, { method: "POST" });
      toast.success(r.detail);
      setEsperando(true);
      // Deja de consultar cuando aparece el respaldo nuevo (o a los 4 minutos)
      const fin = Date.now() + 240_000;
      const revisar = async () => {
        const d = await mutate();
        if (d?.respaldos[0]?.clave !== antes || Date.now() > fin) setEsperando(false);
        else setTimeout(revisar, 10_000);
      };
      setTimeout(revisar, 10_000);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo iniciar el respaldo.");
    } finally {
      setPidiendo(false);
    }
  }

  async function descargar(r: Respaldo) {
    setDescargando(r.clave);
    try {
      const { url } = await api<{ url: string }>(`${URL}/descargar`, { method: "POST", json: { clave: r.clave } });
      window.location.assign(url);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo descargar.");
    } finally {
      setDescargando(null);
    }
  }

  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Respaldos de la base de datos</h2>
          <p className="text-sm text-muted-foreground">
            Copia completa cada noche a las 3:00 a. m. Se guardan 30 días de copias diarias y 12 meses de copias mensuales.
          </p>
        </div>
        <Button variant="outline" onClick={() => void respaldarAhora()} disabled={pidiendo || esperando}>
          {pidiendo || esperando ? <Loader2 className="size-4 animate-spin" /> : <DatabaseBackup className="size-4" />}
          {esperando ? "Respaldando…" : "Respaldar ahora"}
        </Button>
      </div>

      {data && (
        <div
          className={`mt-3 flex gap-2 rounded-md border px-3 py-2.5 text-sm ${
            data.al_dia ? "border-success/25 bg-success-soft text-success" : "border-destructive/25 bg-destructive/5 text-destructive"
          }`}
        >
          {data.al_dia ? <ShieldCheck className="mt-0.5 size-4 shrink-0" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0" />}
          {data.al_dia
            ? `Al día: último respaldo el ${fecha(data.ultimo!)}.`
            : data.ultimo
              ? `El último respaldo es del ${fecha(data.ultimo)}: hace más de 36 horas. Revise el correo de alertas o pulse «Respaldar ahora».`
              : "Aún no hay respaldos. El primero se hará esta noche, o pulse «Respaldar ahora»."}
        </div>
      )}

      <div className="mt-3 overflow-hidden rounded-lg border bg-card">
        {isLoading && <p className="px-4 py-6 text-sm text-muted-foreground">Cargando…</p>}
        {data?.respaldos.slice(0, 15).map((r) => (
          <div key={r.clave} className="flex items-center gap-3 border-b px-4 py-2.5 last:border-b-0">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{fecha(r.fecha)}</p>
              <p className="truncate text-xs text-muted-foreground">{r.clave.split("/").pop()}</p>
            </div>
            {r.tipo === "mensual" && <Etiqueta tono="info">Mensual</Etiqueta>}
            <span className="w-16 text-right text-sm tabular-nums text-muted-foreground">{tamano(r.tamano_bytes)}</span>
            <Button variant="ghost" size="sm" onClick={() => void descargar(r)} disabled={descargando === r.clave}>
              {descargando === r.clave ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
              <span className="hidden sm:inline">Descargar</span>
            </Button>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        El archivo descargado contiene todos los datos de todas las copropiedades: guárdelo en un lugar seguro. Cómo restaurarlo:
        docs/RESPALDOS.md.
      </p>
      <AlertasDeErrores />
    </section>
  );
}

/** Comprueba que las alertas de errores (Sentry) llegan: envía un error de prueba. */
function AlertasDeErrores() {
  const [enviando, setEnviando] = useState(false);
  async function probar() {
    setEnviando(true);
    try {
      const r = await api<{ activas: boolean; detail: string }>("/plataforma/probar-alerta", { method: "POST" });
      if (r.activas) toast.success(r.detail);
      else toast.warning(r.detail);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo enviar la alerta de prueba.");
    } finally {
      setEnviando(false);
    }
  }
  return (
    <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card px-4 py-3">
      <div>
        <p className="text-sm font-medium">Alertas de errores</p>
        <p className="text-xs text-muted-foreground">
          Si algo falla en la plataforma, le llega un correo de Sentry. Compruebe que funcionan enviando una alerta de prueba.
        </p>
      </div>
      <Button variant="outline" size="sm" onClick={() => void probar()} disabled={enviando}>
        {enviando ? <Loader2 className="size-4 animate-spin" /> : <AlertTriangle className="size-4" />}
        Enviar alerta de prueba
      </Button>
    </div>
  );
}
