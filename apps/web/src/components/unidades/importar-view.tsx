"use client";

import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Download, FileSpreadsheet, Loader2, RotateCcw, Upload, XCircle } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Kpi, mensajeError, Seccion, SinAcceso } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, errorMessage, redirectToLogin } from "@/lib/api";
import { baseUnidades, puedeUnidades, RELACION, type ResultadoImportacion, TIPO_VEHICULO, type VistaPrevia } from "@/lib/unidades";
import { cn } from "@/lib/utils";

import { useRefrescarUnidades } from "./comunes";

const CAMPOS: Record<string, string> = {
  tipo: "Tipo",
  coefficient: "Coeficiente",
  area_m2: "Área",
  matricula_inmobiliaria: "Matrícula",
  observaciones: "Observaciones",
  unidad_principal: "Anexo de",
};

async function subir<T>(url: string, archivo: File, extra: Record<string, string> = {}): Promise<T> {
  const form = new FormData();
  form.append("archivo", archivo);
  for (const [k, v] of Object.entries(extra)) form.append(k, v);
  const res = await fetch(`/api/proxy${url}`, { method: "POST", body: form });
  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError(401, "Tu sesión expiró");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorMessage(data, `Error ${res.status}`), data);
  return data as T;
}

function valorTexto(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

export function ImportarView() {
  const { tenant } = useTenant();
  const b = baseUnidades(tenant.tenant_id);
  const refrescar = useRefrescarUnidades();
  const entrada = useRef<HTMLInputElement>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<VistaPrevia | null>(null);
  const [resultado, setResultado] = useState<ResultadoImportacion | null>(null);
  const [cargando, setCargando] = useState<"previa" | "confirmar" | null>(null);
  const [arrastrando, setArrastrando] = useState(false);

  if (!puedeUnidades(tenant.role, "importar")) return <SinAcceso />;

  const paso = resultado ? 3 : previa ? 2 : 1;

  async function revisar(f: File) {
    if (!f.name.toLowerCase().endsWith(".xlsx")) {
      toast.error("Suba un archivo de Excel (.xlsx). Si tiene .xls o .csv, ábralo y guárdelo como .xlsx");
      return;
    }
    setArchivo(f);
    setCargando("previa");
    try {
      setPrevia(await subir<VistaPrevia>(`${b}/importar/previa`, f));
    } catch (e) {
      toast.error(mensajeError(e));
      setArchivo(null);
    } finally {
      setCargando(null);
    }
  }

  async function confirmar() {
    if (!archivo || !previa) return;
    setCargando("confirmar");
    try {
      const r = await subir<ResultadoImportacion>(`${b}/importar/confirmar`, archivo, { sha256: previa.sha256 });
      setResultado(r);
      void refrescar(tenant.tenant_id);
      toast.success("Censo importado");
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setCargando(null);
    }
  }

  function reiniciar() {
    setArchivo(null);
    setPrevia(null);
    setResultado(null);
    if (entrada.current) entrada.current.value = "";
  }

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Importar censo desde Excel"
        description="Cargue unidades, propietarios, residentes y vehículos de una sola vez."
        actions={
          <Button variant="ghost" size="icon" asChild aria-label="Volver a unidades">
            <Link href={`/${tenant.tenant_slug}/unidades`}>
              <ArrowLeft className="size-4" />
            </Link>
          </Button>
        }
      />

      <div className="mx-auto w-full max-w-5xl space-y-5 p-4 sm:p-6">
        {/* Pasos */}
        <ol className="flex items-center gap-2 text-sm">
          {["Subir el archivo", "Revisar los cambios", "Listo"].map((t, i) => (
            <li key={t} className="flex flex-1 items-center gap-2">
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                  paso > i + 1 ? "border-success bg-success text-white" : paso === i + 1 ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground",
                )}
              >
                {paso > i + 1 ? <Check className="size-3.5" /> : i + 1}
              </span>
              <span className={cn("hidden sm:inline", paso === i + 1 ? "font-medium" : "text-muted-foreground")}>{t}</span>
              {i < 2 && <span className="h-px flex-1 bg-border" />}
            </li>
          ))}
        </ol>

        {/* Paso 1 */}
        {paso === 1 && (
          <div className="grid gap-4 md:grid-cols-[1fr_1.4fr]">
            <Seccion titulo="1. Descargue la plantilla" descripcion="Tiene las hojas Unidades, Personas y Vehículos, con ejemplos y listas.">
              <div className="space-y-3 p-4 text-sm">
                <Button variant="outline" asChild className="w-full">
                  <a href={`/api/proxy${b}/importar/plantilla`} download>
                    <Download className="size-4" /> Plantilla del censo (.xlsx)
                  </a>
                </Button>
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  <li>¿Ya tiene un Excel del administrador anterior? Súbalo tal cual: se reconocen columnas como «Apto», «Cédula» o «Celular».</li>
                  <li>Una celda vacía significa «no cambiar». Puede reimportar para completar datos.</li>
                  <li>Nada se borra ni se desactiva por no venir en el archivo.</li>
                </ul>
              </div>
            </Seccion>
            <Seccion titulo="2. Suba su archivo" descripcion="Primero verá una vista previa. Nada se guarda hasta que confirme.">
              <div className="p-4">
                <label
                  onDragOver={(e) => {
                    e.preventDefault();
                    setArrastrando(true);
                  }}
                  onDragLeave={() => setArrastrando(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setArrastrando(false);
                    const f = e.dataTransfer.files[0];
                    if (f) void revisar(f);
                  }}
                  className={cn(
                    "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-10 text-center transition-colors hover:bg-accent/40",
                    arrastrando && "border-primary bg-accent/60",
                  )}
                >
                  {cargando === "previa" ? (
                    <>
                      <Loader2 className="size-8 animate-spin text-primary" />
                      <span className="text-sm font-medium">Leyendo {archivo?.name}…</span>
                    </>
                  ) : (
                    <>
                      <FileSpreadsheet className="size-8 text-primary" />
                      <span className="text-sm font-medium">Arrastre el Excel aquí o haga clic para elegirlo</span>
                      <span className="text-xs text-muted-foreground">Solo .xlsx, máximo 5 MB</span>
                    </>
                  )}
                  <input
                    ref={entrada}
                    type="file"
                    accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    className="sr-only"
                    disabled={!!cargando}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void revisar(f);
                    }}
                  />
                </label>
              </div>
            </Seccion>
          </div>
        )}

        {/* Paso 2 */}
        {paso === 2 && previa && (
          <>
            <div
              className={cn(
                "flex flex-wrap items-center gap-3 rounded-lg border p-4",
                previa.total_errores ? "border-destructive/30 bg-destructive/5" : previa.hay_cambios ? "border-success/30 bg-success-soft/40" : "bg-card",
              )}
            >
              {previa.total_errores ? (
                <XCircle className="size-6 text-destructive" />
              ) : previa.hay_cambios ? (
                <CheckCircle2 className="size-6 text-success" />
              ) : (
                <Check className="size-6 text-muted-foreground" />
              )}
              <div className="min-w-0 flex-1">
                <p className="font-medium">
                  {previa.total_errores
                    ? `El archivo tiene ${previa.total_errores} ${previa.total_errores === 1 ? "error" : "errores"}: corríjalos y vuelva a subirlo`
                    : previa.hay_cambios
                      ? "El archivo está listo para importar"
                      : "Todo lo que trae el archivo ya está registrado"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {previa.archivo} · {previa.filas_leidas} filas leídas
                </p>
              </div>
              <Button variant="outline" onClick={reiniciar}>
                <RotateCcw className="size-4" /> Subir otro archivo
              </Button>
              {previa.puede_aplicar && (
                <Button onClick={confirmar} disabled={!!cargando}>
                  {cargando === "confirmar" ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
                  Confirmar e importar
                </Button>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
              <Kpi titulo="Unidades nuevas" valor={String(previa.totales.unidades_nuevas)} detalle={previa.totales.unidades_con_cambios ? `${previa.totales.unidades_con_cambios} con cambios` : undefined} />
              <Kpi titulo="Personas nuevas" valor={String(previa.totales.personas_nuevas)} detalle={previa.totales.personas_con_cambios ? `${previa.totales.personas_con_cambios} con datos actualizados` : undefined} />
              <Kpi titulo="Vínculos nuevos" valor={String(previa.totales.vinculos_nuevos)} detalle="Persona ↔ unidad" />
              <Kpi titulo="Vehículos nuevos" valor={String(previa.totales.vehiculos_nuevos)} detalle={previa.totales.sin_cambios ? `${previa.totales.sin_cambios} filas ya registradas` : undefined} />
            </div>

            {previa.coeficientes && (
              <p className={cn("rounded-md border px-3 py-2 text-sm", previa.coeficientes.cuadra ? "border-success/30 bg-success-soft/30" : "border-warning/30 bg-warning-soft/40")}>
                Coeficientes después de importar: <strong>{previa.coeficientes.mensaje}</strong>
              </p>
            )}

            {previa.errores.length > 0 && (
              <Seccion titulo="Errores por corregir" descripcion="Corrija estas filas en su Excel y vuelva a subirlo. Se muestran los primeros 500.">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-28">Hoja</TableHead>
                      <TableHead className="w-16 text-right">Fila</TableHead>
                      <TableHead>Problema</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {previa.errores.map((e, i) => (
                      <TableRow key={i}>
                        <TableCell>{e.hoja}</TableCell>
                        <TableCell className="text-right tabular-nums">{e.fila}</TableCell>
                        <TableCell className="text-destructive">{e.mensaje}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Seccion>
            )}

            {previa.advertencias.length > 0 && (
              <Seccion titulo="Advertencias" descripcion="No impiden importar, pero conviene revisarlas.">
                <ul className="space-y-1 p-4 text-sm">
                  {previa.advertencias.map((a, i) => (
                    <li key={i} className="flex gap-2">
                      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" /> {a}
                    </li>
                  ))}
                </ul>
              </Seccion>
            )}

            {previa.unidades_con_cambios.length > 0 && (
              <Seccion titulo="Unidades que cambian" descripcion="Antes → después.">
                <ul className="divide-y text-sm">
                  {previa.unidades_con_cambios.map((u) => (
                    <li key={u.etiqueta} className="px-4 py-2">
                      <span className="font-medium">{u.etiqueta}</span>
                      <span className="ml-2 text-muted-foreground">
                        {Object.entries(u.cambios).map(([k, c]) => `${CAMPOS[k] ?? k}: ${valorTexto(c.antes)} → ${valorTexto(c.despues)}`).join(" · ")}
                      </span>
                    </li>
                  ))}
                </ul>
              </Seccion>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              {previa.unidades_nuevas.length > 0 && (
                <Seccion titulo={`Unidades nuevas (${previa.totales.unidades_nuevas})`}>
                  <p className="max-h-64 overflow-y-auto p-4 text-sm leading-relaxed">{previa.unidades_nuevas.map((u) => u.etiqueta).join(" · ")}</p>
                </Seccion>
              )}
              {previa.vinculos_nuevos.length > 0 && (
                <Seccion titulo={`Personas que se vinculan (${previa.totales.vinculos_nuevos})`}>
                  <ul className="max-h-64 divide-y overflow-y-auto text-sm">
                    {previa.vinculos_nuevos.map((v) => (
                      <li key={`${v.fila}-${v.unidad}`} className="flex items-center gap-2 px-4 py-1.5">
                        <span className="w-16 text-muted-foreground">{v.unidad}</span>
                        <span className="min-w-0 flex-1 truncate">{v.nombre}</span>
                        <span className="text-xs text-muted-foreground">
                          {RELACION[v.relacion].label}
                          {!v.persona_nueva && " · ya en el directorio"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Seccion>
              )}
              {previa.vehiculos_nuevos.length > 0 && (
                <Seccion titulo={`Vehículos nuevos (${previa.totales.vehiculos_nuevos})`}>
                  <p className="max-h-48 overflow-y-auto p-4 text-sm">
                    {previa.vehiculos_nuevos.map((v) => `${v.placa} (${TIPO_VEHICULO[v.tipo].toLowerCase()}, ${v.unidad})`).join(" · ")}
                  </p>
                </Seccion>
              )}
            </div>
          </>
        )}

        {/* Paso 3 */}
        {paso === 3 && resultado && (
          <div className="rounded-lg border bg-card p-6 text-center">
            <CheckCircle2 className="mx-auto size-10 text-success" />
            <h2 className="mt-3 text-lg font-semibold">Censo importado</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {resultado.unidades_creadas} unidades nuevas, {resultado.unidades_actualizadas} actualizadas, {resultado.personas_creadas} personas nuevas,{" "}
              {resultado.vinculos_creados} vínculos y {resultado.vehiculos_creados} vehículos. Todo quedó en la auditoría.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              <Button variant="outline" onClick={reiniciar}>
                <Upload className="size-4" /> Importar otro archivo
              </Button>
              <Button asChild>
                <Link href={`/${tenant.tenant_slug}/unidades`}>Ver las unidades</Link>
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
