"use client";

import { CalendarClock, Gavel, Loader2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, mensajeError, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import {
  type AsambleaDetalle,
  type AsambleaResumen,
  baseAsambleas,
  ESTADO_ASAMBLEA,
  fechaHoraLarga,
  MAYORIA,
  type Mayoria,
  MODALIDAD,
  type Modalidad,
  pct,
  puedeAsambleas,
} from "@/lib/asambleas";

interface PuntoBorrador {
  titulo: string;
  tipo: "INFORMATIVO" | "VOTACION";
  mayoria: Mayoria;
  opciones: string;
}

const PUNTOS_TIPICOS: PuntoBorrador[] = [
  { titulo: "Verificación del quórum e instalación", tipo: "INFORMATIVO", mayoria: "SIMPLE", opciones: "" },
  { titulo: "Elección del presidente y secretario de la asamblea", tipo: "INFORMATIVO", mayoria: "SIMPLE", opciones: "" },
  { titulo: "Informe de gestión de la administración", tipo: "INFORMATIVO", mayoria: "SIMPLE", opciones: "" },
  { titulo: "Aprobación de los estados financieros", tipo: "VOTACION", mayoria: "SIMPLE", opciones: "" },
  { titulo: "Aprobación del presupuesto", tipo: "VOTACION", mayoria: "SIMPLE", opciones: "" },
  { titulo: "Proposiciones y varios", tipo: "INFORMATIVO", mayoria: "SIMPLE", opciones: "" },
];

export function AsambleasView() {
  const { tenant } = useTenant();
  const b = baseAsambleas(tenant.tenant_id);
  const { data, isLoading } = useSWR<AsambleaResumen[]>(puedeAsambleas(tenant.role, "ver") ? b : null, fetcher);
  const [nueva, setNueva] = useState(false);
  if (!puedeAsambleas(tenant.role, "ver")) return <SinAcceso />;
  const gestiona = puedeAsambleas(tenant.role, "gestionar");

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Asambleas"
        description="Asambleas de copropietarios: convocatoria, quórum, votaciones por coeficiente y actas (Ley 675 de 2001)."
        actions={
          gestiona && (
            <Button onClick={() => setNueva(true)}>
              <Plus className="size-4" /> Programar asamblea
            </Button>
          )
        }
      />
      <div className="p-4 sm:p-6">
        <div className="rounded-lg border bg-card">
          {isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : !data?.length ? (
            <Vacio icono={Gavel} titulo="No hay asambleas" texto={gestiona ? "Programe la próxima asamblea con su orden del día y convóquela desde aquí." : "Cuando la administración convoque una asamblea, la verá aquí."} />
          ) : (
            <ul className="divide-y">
              {data.map((a) => {
                const e = ESTADO_ASAMBLEA[a.estado];
                return (
                  <li key={a.id}>
                    <Link href={`/${tenant.tenant_slug}/asambleas/${a.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 hover:bg-accent/40">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{a.titulo}</span>
                          <Etiqueta tono={e.tono}>{e.label}</Etiqueta>
                          {a.estado === "PROGRAMADA" && !a.convocada && <Etiqueta tono="warning">Sin convocar</Etiqueta>}
                          {a.acta_document_id && <Etiqueta tono="neutral">Acta en Documentos</Etiqueta>}
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground first-letter:uppercase">
                          {fechaHoraLarga(a.fecha_hora)} · {MODALIDAD[a.modalidad]}
                          {a.lugar ? ` · ${a.lugar}` : ""} · {a.puntos} puntos
                        </p>
                      </div>
                      {a.quorum_pct && (
                        <div className="text-right">
                          <p className="text-sm font-semibold tabular-nums">{pct(a.quorum_pct)}</p>
                          <p className="text-xs text-muted-foreground">{a.estado === "EN_CURSO" ? "quórum actual" : "quórum"}</p>
                        </div>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
      {nueva && <NuevaAsambleaDialog onClose={() => setNueva(false)} />}
    </div>
  );
}

/** Fecha y hora local (Bogotá) por defecto: dentro de 20 días a las 8:00 a. m. */
function fechaPorDefecto(): string {
  const d = new Date(Date.now() + 20 * 86_400_000);
  return `${d.toISOString().slice(0, 10)}T08:00`;
}

function NuevaAsambleaDialog({ onClose }: { onClose: () => void }) {
  const { tenant } = useTenant();
  const router = useRouter();
  const [titulo, setTitulo] = useState(`Asamblea general ordinaria ${new Date().getFullYear() + (new Date().getMonth() > 5 ? 1 : 0)}`);
  const [tipo, setTipo] = useState<"ORDINARIA" | "EXTRAORDINARIA">("ORDINARIA");
  const [modalidad, setModalidad] = useState<Modalidad>("MIXTA");
  const [convocatoria, setConvocatoria] = useState<"PRIMERA" | "SEGUNDA">("PRIMERA");
  const [fecha, setFecha] = useState(fechaPorDefecto());
  const [lugar, setLugar] = useState("Salón social");
  const [poderes, setPoderes] = useState("2");
  const [puntos, setPuntos] = useState<PuntoBorrador[]>(PUNTOS_TIPICOS);
  const [guardando, setGuardando] = useState(false);

  const cambiar = (i: number, cambio: Partial<PuntoBorrador>) => setPuntos((ps) => ps.map((p, j) => (j === i ? { ...p, ...cambio } : p)));

  async function guardar() {
    setGuardando(true);
    try {
      const a = await api<AsambleaDetalle>(baseAsambleas(tenant.tenant_id), {
        method: "POST",
        json: {
          titulo: titulo.trim(),
          tipo,
          modalidad,
          convocatoria,
          fecha_hora: `${fecha}:00-05:00`,
          lugar: lugar.trim() || null,
          max_poderes_por_apoderado: Number(poderes) || 2,
          puntos: puntos
            .filter((p) => p.titulo.trim())
            .map((p) => ({
              titulo: p.titulo.trim(),
              tipo: p.tipo,
              ...(p.tipo === "VOTACION"
                ? { mayoria: p.mayoria, opciones: p.opciones.split(/[\n,]/).map((o) => o.trim()).filter(Boolean) }
                : {}),
            })),
        },
      });
      toast.success("Asamblea programada. Revise el orden del día y convóquela.");
      router.push(`/${tenant.tenant_slug}/asambleas/${a.id}`);
    } catch (e) {
      toast.error(mensajeError(e));
      setGuardando(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Programar asamblea</DialogTitle>
          <DialogDescription>La convocatoria debe publicarse con al menos 15 días calendario de anticipación (art. 39 Ley 675).</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo label="Título" className="sm:col-span-2">
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} />
          </Campo>
          <Campo label="Tipo">
            <select className={campoClase()} value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)}>
              <option value="ORDINARIA">Ordinaria</option>
              <option value="EXTRAORDINARIA">Extraordinaria</option>
            </select>
          </Campo>
          <Campo label="Modalidad" ayuda={modalidad !== "PRESENCIAL" ? "Los propietarios con cuenta podrán asistir y votar desde el portal" : undefined}>
            <select className={campoClase()} value={modalidad} onChange={(e) => setModalidad(e.target.value as Modalidad)}>
              {(Object.keys(MODALIDAD) as Modalidad[]).map((m) => (
                <option key={m} value={m}>
                  {MODALIDAD[m]}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Fecha y hora">
            <Input type="datetime-local" value={fecha} onChange={(e) => setFecha(e.target.value)} />
          </Campo>
          <Campo label="Lugar">
            <Input value={lugar} onChange={(e) => setLugar(e.target.value)} />
          </Campo>
          <Campo label="Convocatoria" ayuda={convocatoria === "SEGUNDA" ? "Decide con cualquier número plural de propietarios (art. 41)" : "Quórum: más del 50 % de los coeficientes"}>
            <select className={campoClase()} value={convocatoria} onChange={(e) => setConvocatoria(e.target.value as typeof convocatoria)}>
              <option value="PRIMERA">Primera convocatoria</option>
              <option value="SEGUNDA">Segunda convocatoria</option>
            </select>
          </Campo>
          <Campo label="Máximo de poderes por apoderado" ayuda="Según el reglamento de propiedad horizontal">
            <Input type="number" min={1} max={50} value={poderes} onChange={(e) => setPoderes(e.target.value)} />
          </Campo>
        </div>

        <div className="mt-2">
          <p className="text-sm font-medium">Orden del día</p>
          <ol className="mt-2 space-y-2">
            {puntos.map((p, i) => (
              <li key={i} className="rounded-md border p-2">
                <div className="flex items-center gap-2">
                  <span className="w-5 text-right text-sm text-muted-foreground tabular-nums">{i + 1}.</span>
                  <Input value={p.titulo} onChange={(e) => cambiar(i, { titulo: e.target.value })} aria-label={`Punto ${i + 1}`} className="flex-1" />
                  <Button variant="ghost" size="icon" aria-label={`Quitar punto ${i + 1}`} onClick={() => setPuntos((ps) => ps.filter((_, j) => j !== i))}>
                    <Trash2 className="size-4" />
                  </Button>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 pl-7">
                  <select aria-label={`Tipo del punto ${i + 1}`} className={campoClase()} style={{ width: "auto" }} value={p.tipo} onChange={(e) => cambiar(i, { tipo: e.target.value as PuntoBorrador["tipo"] })}>
                    <option value="INFORMATIVO">Informativo</option>
                    <option value="VOTACION">Se vota</option>
                  </select>
                  {p.tipo === "VOTACION" && (
                    <select aria-label={`Mayoría del punto ${i + 1}`} title={MAYORIA[p.mayoria].ayuda} className={campoClase()} style={{ width: "auto" }} value={p.mayoria} onChange={(e) => cambiar(i, { mayoria: e.target.value as Mayoria })}>
                      {(Object.keys(MAYORIA) as Mayoria[]).map((m) => (
                        <option key={m} value={m}>
                          {MAYORIA[m].label}
                        </option>
                      ))}
                    </select>
                  )}
                  {p.tipo === "VOTACION" && p.mayoria === "ELECCION" && (
                    <Input value={p.opciones} onChange={(e) => cambiar(i, { opciones: e.target.value })} placeholder="Candidatos o planchas, separados por coma" aria-label={`Opciones del punto ${i + 1}`} className="min-w-60 flex-1" />
                  )}
                </div>
              </li>
            ))}
          </ol>
          <Button variant="outline" size="sm" className="mt-2" onClick={() => setPuntos((ps) => [...ps, { titulo: "", tipo: "INFORMATIVO", mayoria: "SIMPLE", opciones: "" }])}>
            <Plus className="size-4" /> Agregar punto
          </Button>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={guardar} disabled={guardando || titulo.trim().length < 5 || !fecha}>
            {guardando ? <Loader2 className="size-4 animate-spin" /> : <CalendarClock className="size-4" />} Programar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

