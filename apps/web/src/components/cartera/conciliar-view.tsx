"use client";

import { CheckCircle2, FileSpreadsheet, Info, Landmark, Loader2, RotateCcw, Upload } from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, SinAcceso } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { api, ApiError, errorMessage } from "@/lib/api";
import { baseCartera, puedeCartera } from "@/lib/cartera";
import { fechaCorta, pesos } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

type Confianza = "alta" | "media" | "baja" | "ninguna";
interface Movimiento {
  fila: number;
  fecha: string;
  descripcion: string;
  pagador: string | null;
  valor: string;
  referencia: string;
  medio_pago: "TRANSFERENCIA" | "CONSIGNACION";
  unidad_id: string | null;
  unidad: string | null;
  confianza: Confianza;
  motivos: string[];
  ya_registrado: string | null;
}
interface Analisis {
  archivo: string;
  movimientos: Movimiento[];
  unidades: { id: string; etiqueta: string }[];
}
interface Resultado {
  creados: { fila: number; pago_id: string; recibo: number; valor: string }[];
  errores: { fila: number; motivo: string }[];
}

const TONO: Record<Confianza, "success" | "info" | "warning" | "neutral"> = {
  alta: "success",
  media: "info",
  baja: "warning",
  ninguna: "neutral",
};
const ETIQUETA: Record<Confianza, string> = { alta: "Confianza alta", media: "Confianza media", baja: "Revisar", ninguna: "Sin unidad" };

export function ConciliarView() {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const input = useRef<HTMLInputElement>(null);
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [unidad, setUnidad] = useState<Record<number, string>>({});
  const [incluir, setIncluir] = useState<Record<number, boolean>>({});
  const [filtro, setFiltro] = useState<"todos" | "revisar" | "listos">("todos");
  const [cargando, setCargando] = useState(false);
  const [registrando, setRegistrando] = useState(false);
  const [resultado, setResultado] = useState<Resultado | null>(null);

  if (!puedeCartera(tenant.role, "registrarPago")) return <SinAcceso texto="Solo administración y contabilidad concilian pagos" />;

  async function analizar(archivo: File) {
    setCargando(true);
    setResultado(null);
    try {
      const form = new FormData();
      form.append("archivo", archivo);
      const res = await fetch(`/api/proxy${b}/extracto/analizar`, { method: "POST", body: form });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        toast.error(errorMessage(data, "No se pudo leer el extracto."));
        return;
      }
      const a = data as Analisis;
      setAnalisis(a);
      setUnidad(Object.fromEntries(a.movimientos.filter((m) => m.unidad_id).map((m) => [m.fila, m.unidad_id!])));
      // Se preseleccionan solo los de confianza alta o media que no están registrados
      setIncluir(
        Object.fromEntries(
          a.movimientos.map((m) => [m.fila, !m.ya_registrado && !!m.unidad_id && (m.confianza === "alta" || m.confianza === "media")]),
        ),
      );
    } catch {
      toast.error("No se pudo conectar con el servidor.");
    } finally {
      setCargando(false);
      if (input.current) input.current.value = "";
    }
  }

  const movs = analisis?.movimientos ?? [];
  const seleccion = movs.filter((m) => incluir[m.fila] && unidad[m.fila] && !m.ya_registrado);
  const total = seleccion.reduce((a, m) => a + Number(m.valor), 0);
  const visibles = useMemo(
    () =>
      movs.filter((m) =>
        filtro === "todos" ? true : filtro === "listos" ? incluir[m.fila] && !m.ya_registrado : !m.ya_registrado && (m.confianza === "baja" || m.confianza === "ninguna"),
      ),
    [movs, filtro, incluir],
  );
  const cuenta = (c: Confianza) => movs.filter((m) => m.confianza === c && !m.ya_registrado).length;
  const yaRegistrados = movs.filter((m) => m.ya_registrado).length;

  async function registrar() {
    setRegistrando(true);
    try {
      const r = await api<Resultado>(`${b}/extracto/registrar`, {
        method: "POST",
        json: {
          items: seleccion.map((m) => ({
            fila: m.fila,
            unidad_id: unidad[m.fila],
            fecha_pago: m.fecha,
            valor: m.valor,
            medio_pago: m.medio_pago,
            referencia: m.referencia,
            pagador_nombre: m.pagador ?? undefined,
          })),
        },
      });
      setResultado(r);
      if (r.creados.length) toast.success(`${r.creados.length} pago${r.creados.length === 1 ? "" : "s"} registrado${r.creados.length === 1 ? "" : "s"}`);
      if (r.errores.length) toast.warning(`${r.errores.length} no se pudieron registrar: revise el detalle.`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudieron registrar los pagos.");
    } finally {
      setRegistrando(false);
    }
  }

  // ---------------------------------------------------------------- resultado
  if (resultado) {
    const porFila = Object.fromEntries(movs.map((m) => [m.fila, m]));
    return (
      <div className="flex flex-1 flex-col">
        <PageHeader title="Conciliar extracto" description="Pagos registrados desde el extracto bancario" />
        <div className="space-y-4 p-4 sm:p-6">
          <div className="flex gap-3 rounded-lg border border-success/25 bg-success-soft p-4 text-success">
            <CheckCircle2 className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="font-medium">{resultado.creados.length} pagos registrados por {pesos(resultado.creados.reduce((a, c) => a + Number(c.valor), 0))}</p>
              <p className="text-sm">Cada uno se aplicó a intereses y luego a la deuda más antigua, y generó su recibo de caja.</p>
            </div>
          </div>
          {resultado.errores.length > 0 && (
            <div className="rounded-lg border border-destructive/25 bg-destructive/5 p-4 text-sm">
              <p className="font-medium text-destructive">{resultado.errores.length} no se registraron</p>
              <ul className="mt-2 space-y-1">
                {resultado.errores.map((e) => (
                  <li key={e.fila}>
                    <span className="font-medium">{porFila[e.fila]?.descripcion || `Fila ${e.fila}`}</span> ({pesos(porFila[e.fila]?.valor)}): {e.motivo}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button asChild>
              <Link href={`/${tenant.tenant_slug}/cartera/pagos`}>Ver los pagos</Link>
            </Button>
            <Button variant="outline" onClick={() => { setAnalisis(null); setResultado(null); }}>
              <RotateCcw className="size-4" /> Conciliar otro extracto
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------- subir el archivo
  if (!analisis) {
    return (
      <div className="flex flex-1 flex-col">
        <PageHeader title="Conciliar extracto" description="Registre los pagos de cuotas a partir del extracto del banco" />
        <div className="mx-auto w-full max-w-3xl space-y-5 p-4 sm:p-6">
          <button
            type="button"
            onClick={() => input.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files[0];
              if (f) void analizar(f);
            }}
            disabled={cargando}
            className="flex w-full flex-col items-center gap-2 rounded-lg border-2 border-dashed bg-card px-6 py-12 text-center transition-colors hover:border-primary/50 hover:bg-accent/40"
          >
            {cargando ? <Loader2 className="size-8 animate-spin text-primary" /> : <Upload className="size-8 text-primary" />}
            <span className="font-medium">{cargando ? "Leyendo el extracto…" : "Arrastre el extracto aquí o haga clic para elegirlo"}</span>
            <span className="text-xs text-muted-foreground">Excel (.xlsx) o CSV, máximo 5 MB. Nada se guarda hasta que confirme.</span>
          </button>
          <input ref={input} type="file" accept=".xlsx,.csv,.txt" className="hidden" onChange={(e) => e.target.files?.[0] && void analizar(e.target.files[0])} />
          <div className="rounded-lg border bg-card p-4 text-sm">
            <p className="flex items-center gap-2 font-medium">
              <Landmark className="size-4 text-primary" /> Cómo obtener el extracto
            </p>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
              <li>Entre a la banca en línea de la cuenta de la copropiedad.</li>
              <li>Busque «Movimientos» o «Consultar extracto», elija el periodo y descárguelo en <b>Excel</b> o <b>CSV</b>.</li>
              <li>Súbalo aquí tal cual: la plataforma reconoce las columnas de fecha, descripción, referencia y valor de cualquier banco, y toma solo las entradas de dinero.</li>
            </ol>
            <p className="mt-3 flex gap-2 text-xs text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              Para que la plataforma reconozca más pagos, pida a los residentes que escriban la torre y el apartamento en la
              referencia de la transferencia (por ejemplo «T1 APTO 502»).
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------- revisar sugerencias
  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Conciliar extracto"
        description={`${analisis.archivo} · ${movs.length} entradas de dinero`}
        actions={
          <Button variant="outline" onClick={() => setAnalisis(null)}>
            <FileSpreadsheet className="size-4" /> Otro archivo
          </Button>
        }
      />
      <div className="space-y-4 p-4 pb-28 sm:p-6 sm:pb-28">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {(
            [
              ["Confianza alta", cuenta("alta"), "success"],
              ["Confianza media", cuenta("media"), "info"],
              ["Por revisar", cuenta("baja"), "warning"],
              ["Sin unidad", cuenta("ninguna"), "neutral"],
              ["Ya registrados", yaRegistrados, "neutral"],
            ] as const
          ).map(([t, n, tono]) => (
            <div key={t} className="rounded-lg border bg-card p-3">
              <p className="text-xs text-muted-foreground">{t}</p>
              <p className={cn("text-xl font-semibold tabular-nums", tono === "success" && "text-success", tono === "warning" && n > 0 && "text-warning")}>{n}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex rounded-md border bg-card p-0.5 text-sm" role="group" aria-label="Filtro">
            {(
              [
                ["todos", "Todos"],
                ["revisar", "Por revisar"],
                ["listos", "Seleccionados"],
              ] as const
            ).map(([k, t]) => (
              <button key={k} type="button" onClick={() => setFiltro(k)} className={cn("rounded px-2.5 py-1", filtro === k ? "bg-accent font-medium" : "text-muted-foreground")}>
                {t}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">Revise la unidad de cada movimiento. Los de confianza alta y media ya vienen marcados.</p>
        </div>

        <div className="overflow-x-auto rounded-lg border bg-card">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
              <tr>
                <th className="w-10 px-3 py-2" />
                <th className="px-2 py-2 font-medium">Fecha</th>
                <th className="px-2 py-2 font-medium">Movimiento</th>
                <th className="px-2 py-2 text-right font-medium">Valor</th>
                <th className="px-2 py-2 font-medium">Unidad</th>
                <th className="px-2 py-2 font-medium">Por qué</th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((m) => (
                <tr key={m.fila} className={cn("border-b align-top last:border-b-0", m.ya_registrado && "opacity-60")}>
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      aria-label={`Registrar el movimiento de ${pesos(m.valor)}`}
                      className="size-4 accent-primary"
                      disabled={!!m.ya_registrado || !unidad[m.fila]}
                      checked={!!incluir[m.fila] && !m.ya_registrado}
                      onChange={(e) => setIncluir((x) => ({ ...x, [m.fila]: e.target.checked }))}
                    />
                  </td>
                  <td className="px-2 py-2.5 whitespace-nowrap">{fechaCorta(m.fecha)}</td>
                  <td className="max-w-80 px-2 py-2.5">
                    <p className="truncate font-medium" title={m.descripcion}>{m.descripcion || "—"}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {m.pagador ? `${m.pagador} · ` : ""}ref. {m.referencia}
                    </p>
                  </td>
                  <td className="px-2 py-2.5 text-right font-medium whitespace-nowrap tabular-nums">{pesos(m.valor)}</td>
                  <td className="px-2 py-2.5">
                    {m.ya_registrado ? (
                      <Etiqueta tono="neutral">Ya registrado · {m.ya_registrado}</Etiqueta>
                    ) : (
                      <select
                        aria-label="Unidad"
                        className={`${campoClase(!unidad[m.fila] && !!incluir[m.fila])} h-8 w-32`}
                        value={unidad[m.fila] ?? ""}
                        onChange={(e) => {
                          const v = e.target.value;
                          setUnidad((x) => ({ ...x, [m.fila]: v }));
                          setIncluir((x) => ({ ...x, [m.fila]: !!v }));
                        }}
                      >
                        <option value="">No es cuota…</option>
                        {analisis.unidades.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.etiqueta}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="px-2 py-2.5">
                    {!m.ya_registrado && <Etiqueta tono={TONO[m.confianza]}>{ETIQUETA[m.confianza]}</Etiqueta>}
                    {m.motivos.length > 0 && <p className="mt-1 text-xs text-muted-foreground">{m.motivos.join(" · ")}</p>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {visibles.length === 0 && <p className="px-4 py-6 text-center text-sm text-muted-foreground">Nada en este filtro.</p>}
        </div>
      </div>

      {/* Barra fija para confirmar */}
      <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-3 border-t bg-card px-4 py-3 sm:px-6">
        <p className="text-sm">
          <span className="font-semibold">{seleccion.length}</span> pagos seleccionados por <span className="font-semibold">{pesos(total)}</span>
        </p>
        <Button onClick={() => void registrar()} disabled={!seleccion.length || registrando}>
          {registrando && <Loader2 className="size-4 animate-spin" />}
          Registrar {seleccion.length} pago{seleccion.length === 1 ? "" : "s"}
        </Button>
      </div>
    </div>
  );
}
