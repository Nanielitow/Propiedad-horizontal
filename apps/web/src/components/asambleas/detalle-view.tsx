"use client";

import {
  ArrowLeft,
  CheckCircle2,
  FileDown,
  FileText,
  Gavel,
  Loader2,
  LogOut,
  Megaphone,
  Play,
  Plus,
  Search,
  Square,
  Trash2,
  UserCheck,
  Users,
  Vote,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo, textareaClase } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, mensajeError, MotivoDialog, Seccion, SinAcceso } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, fetcher } from "@/lib/api";
import {
  type AsambleaDetalle,
  baseAsambleas,
  ESTADO_ASAMBLEA,
  fechaHoraLarga,
  MAYORIA,
  type Mayoria,
  MODALIDAD,
  type Padron,
  pct,
  puedeAsambleas,
  type Punto,
  type Quorum,
} from "@/lib/asambleas";
import { cn } from "@/lib/utils";

const hora = (iso: string) => new Date(iso).toLocaleTimeString("es-CO", { timeStyle: "short", timeZone: "America/Bogota" });
const mayuscula = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function AsambleaDetalleView({ asambleaId }: { asambleaId: string }) {
  const { tenant } = useTenant();
  const b = baseAsambleas(tenant.tenant_id);
  const clave = `${b}/${asambleaId}`;
  // Durante la asamblea el detalle se refresca solo: quórum y votos en vivo
  const { data: a, error, mutate } = useSWR<AsambleaDetalle>(clave, fetcher, {
    refreshInterval: (d) => (d?.estado === "EN_CURSO" ? 4000 : 0),
  });
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [instalar, setInstalar] = useState(false);
  const [cancelar, setCancelar] = useState(false);
  const [cerrar, setCerrar] = useState(false);
  const [nuevoPunto, setNuevoPunto] = useState(false);

  if (!puedeAsambleas(tenant.role, "ver")) return <SinAcceso />;
  if (error instanceof ApiError && error.status === 404) return <SinAcceso texto="La asamblea no existe" />;
  if (!a)
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    );

  const gestiona = puedeAsambleas(tenant.role, "gestionar");
  const registra = puedeAsambleas(tenant.role, "registrar");
  const residente = tenant.role === "RESIDENTE";
  const e = ESTADO_ASAMBLEA[a.estado];
  const pendientes = a.puntos_lista.filter((p) => p.estado !== "CERRADO").length;

  async function accion(id: string, ruta: string, body?: unknown, exito?: string, metodo = "POST") {
    setOcupado(id);
    try {
      const r = await api<AsambleaDetalle>(`${b}${ruta}`, metodo === "DELETE" ? { method: "DELETE" } : { method: "POST", json: body ?? {} });
      void mutate(r, { revalidate: false });
      if (exito) toast.success(exito);
      return r;
    } catch (err) {
      toast.error(mensajeError(err));
      return null;
    } finally {
      setOcupado(null);
    }
  }

  async function convocar() {
    setOcupado("convocar");
    try {
      const r = await api<{ asamblea: AsambleaDetalle; aviso: string | null }>(`${clave}/convocar`, { method: "POST", json: { enviar_correo: true } });
      void mutate(r.asamblea, { revalidate: false });
      toast.success("Convocatoria publicada como circular y enviada por correo");
      if (r.aviso) toast.warning(r.aviso, { duration: 10_000 });
    } catch (err) {
      toast.error(mensajeError(err));
    } finally {
      setOcupado(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title={a.titulo}
        description={`${mayuscula(fechaHoraLarga(a.fecha_hora))} · ${MODALIDAD[a.modalidad]}${a.lugar ? ` · ${a.lugar}` : ""} · ${a.convocatoria === "PRIMERA" ? "Primera" : "Segunda"} convocatoria`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" asChild>
              <Link href={`/${tenant.tenant_slug}/asambleas`}>
                <ArrowLeft className="size-4" /> Asambleas
              </Link>
            </Button>
            {gestiona && a.estado === "PROGRAMADA" && (
              <>
                {!a.convocada && (
                  <Button variant="outline" onClick={convocar} disabled={ocupado === "convocar" || !a.puntos_lista.length}>
                    {ocupado === "convocar" ? <Loader2 className="size-4 animate-spin" /> : <Megaphone className="size-4" />} Convocar
                  </Button>
                )}
                <Button variant="outline" onClick={() => setCancelar(true)}>
                  <XCircle className="size-4" /> Cancelar
                </Button>
                <Button onClick={() => setInstalar(true)}>
                  <Play className="size-4" /> Instalar asamblea
                </Button>
              </>
            )}
            {gestiona && a.estado === "EN_CURSO" && (
              <Button onClick={() => setCerrar(true)}>
                <Square className="size-4" /> Cerrar asamblea
              </Button>
            )}
            {a.estado === "CERRADA" && (
              <>
                <Button variant="outline" asChild>
                  <a href={`/api/proxy${clave}/acta.pdf`} target="_blank" rel="noreferrer">
                    <FileDown className="size-4" /> Acta en PDF
                  </a>
                </Button>
                {a.acta_document_id ? (
                  <Button variant="outline" asChild>
                    <Link href={`/${tenant.tenant_slug}/documents`}>
                      <FileText className="size-4" /> Ver en Documentos
                    </Link>
                  </Button>
                ) : (
                  gestiona && (
                    <Button onClick={() => accion("acta", `/${a.id}/acta/guardar`, undefined, "Acta guardada en Documentos: en unos minutos estará en el buscador y en el resumen de actas")} disabled={ocupado === "acta"}>
                      {ocupado === "acta" ? <Loader2 className="size-4 animate-spin" /> : <FileText className="size-4" />} Guardar acta en Documentos
                    </Button>
                  )
                )}
              </>
            )}
          </div>
        }
      />

      <div className="space-y-4 p-4 sm:p-6">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Etiqueta tono={e.tono}>{e.label}</Etiqueta>
          {a.estado === "PROGRAMADA" && (a.convocada ? <Etiqueta tono="success">Convocada</Etiqueta> : <Etiqueta tono="warning">Sin convocar</Etiqueta>)}
          {a.presidente && (
            <span className="text-muted-foreground">
              Presidente: <span className="text-foreground">{a.presidente}</span> · Secretario: <span className="text-foreground">{a.secretario}</span>
            </span>
          )}
        </div>

        {residente && <AvisoResidente a={a} ocupado={ocupado} onAsistir={() => accion("asistir", `/${a.id}/asistir`, undefined, "Asistencia registrada: ya cuenta para el quórum")} />}

        {a.quorum && <QuorumPanel q={a.quorum} cerrada={a.estado === "CERRADA"} />}

        <Seccion
          titulo="Orden del día"
          descripcion={a.estado === "EN_CURSO" ? "Se vota un punto a la vez. Los resultados se actualizan solos." : undefined}
          acciones={
            gestiona && a.estado === "PROGRAMADA" && (
              <Button size="sm" variant="outline" onClick={() => setNuevoPunto(true)}>
                <Plus className="size-4" /> Agregar punto
              </Button>
            )
          }
        >
          {!a.puntos_lista.length ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">Agregue los puntos del orden del día antes de convocar.</p>
          ) : (
            <ol className="divide-y">
              {a.puntos_lista.map((p) => (
                <PuntoFila key={p.id} a={a} p={p} gestiona={gestiona} registra={registra} residente={residente} ocupado={ocupado} accion={accion} />
              ))}
            </ol>
          )}
        </Seccion>

        {!residente && a.estado !== "PROGRAMADA" && a.estado !== "CANCELADA" && <PadronPanel a={a} registra={registra && a.estado === "EN_CURSO"} accion={accion} ocupado={ocupado} />}

        {a.observaciones && (
          <Seccion titulo="Observaciones">
            <p className="px-4 py-3 text-sm whitespace-pre-line">{a.observaciones}</p>
          </Seccion>
        )}
      </div>

      {instalar && <InstalarDialog onClose={() => setInstalar(false)} onConfirmar={(body) => accion("abrir", `/${a.id}/abrir`, body, "Asamblea instalada: el padrón quedó fijo. Registre la asistencia.")} />}
      <MotivoDialog
        abierto={cancelar}
        onCambio={setCancelar}
        titulo="Cancelar asamblea"
        descripcion="La asamblea queda cancelada y no se puede reabrir. Si ya fue convocada, publique una circular informando a los copropietarios."
        boton="Cancelar asamblea"
        onConfirmar={async (motivo) => {
          await api(`${clave}/cancelar`, { method: "POST", json: { motivo } });
          void mutate();
          toast.success("Asamblea cancelada");
        }}
      />
      {cerrar && (
        <CerrarDialog
          pendientes={pendientes}
          onClose={() => setCerrar(false)}
          onConfirmar={(observaciones) => accion("cerrar", `/${a.id}/cerrar`, { observaciones: observaciones || null }, "Asamblea cerrada. Ya puede descargar el acta.")}
        />
      )}
      {nuevoPunto && <NuevoPuntoDialog onClose={() => setNuevoPunto(false)} onConfirmar={(body) => accion("punto", `/${a.id}/puntos`, body, "Punto agregado")} />}
    </div>
  );
}

// --- Quórum ------------------------------------------------------------------------------------------

function QuorumPanel({ q, cerrada }: { q: Quorum; cerrada: boolean }) {
  const valor = Math.min(100, Number(q.porcentaje));
  return (
    <section className={cn("rounded-lg border bg-card p-4", q.hay_quorum ? "border-success/40" : "border-warning/40")} aria-label="Quórum">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">{cerrada ? "Asistencia al cierre" : "Quórum en este momento"}</p>
          <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">{pct(q.porcentaje)}</p>
          <p className="text-xs text-muted-foreground">
            {q.unidades_presentes} de {q.unidades_total} unidades presentes · coeficientes
          </p>
        </div>
        <div className={cn("flex items-center gap-1.5 text-sm font-medium", q.hay_quorum ? "text-success" : "text-warning")}>
          {q.hay_quorum ? <CheckCircle2 className="size-4" /> : <Users className="size-4" />}
          {q.mensaje}
        </div>
      </div>
      <div className="relative mt-3 h-3 rounded-full bg-muted" role="progressbar" aria-valuenow={valor} aria-valuemin={0} aria-valuemax={100} aria-label="Coeficientes presentes">
        <div className={cn("h-3 rounded-full transition-all", q.hay_quorum ? "bg-success" : "bg-warning")} style={{ width: `${valor}%` }} />
        <div className="absolute top-[-4px] left-1/2 h-5 w-px bg-foreground/60" title="50 %: quórum de primera convocatoria" />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span>0 %</span>
        <span>50 %</span>
        <span>100 %</span>
      </div>
    </section>
  );
}

// --- Residente ----------------------------------------------------------------------------------------

function AvisoResidente({ a, ocupado, onAsistir }: { a: AsambleaDetalle; ocupado: string | null; onAsistir: () => void }) {
  if (!a.soy_votante) {
    if (a.estado === "CERRADA" || a.estado === "CANCELADA") return null;
    return (
      <p className="rounded-lg border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
        En la asamblea votan los propietarios. Si usted es propietario y no aparece como tal, comuníquese con la administración.
      </p>
    );
  }
  const presentes = a.padron.filter((p) => p.presente);
  if (a.estado === "PROGRAMADA")
    return (
      <p className="rounded-lg border bg-info-soft/40 px-4 py-3 text-sm">
        {a.modalidad === "PRESENCIAL"
          ? "La asamblea es presencial. Si no puede asistir, otorgue un poder por escrito a otra persona."
          : "El día de la asamblea podrá registrar su asistencia y votar desde aquí. Si prefiere, otorgue un poder por escrito."}
      </p>
    );
  if (a.estado !== "EN_CURSO") return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card px-4 py-3">
      <div className="text-sm">
        <p className="font-medium">Su participación</p>
        <p className="text-muted-foreground">
          {a.padron.map((p) => `${p.etiqueta}: ${p.presente ? (p.tipo === "APODERADO" ? `presente por apoderado (${p.asistente})` : "presente") : "ausente"}`).join(" · ")}
        </p>
      </div>
      {a.puede_asistir_portal && presentes.length < a.padron.length && (
        <Button onClick={onAsistir} disabled={ocupado === "asistir"}>
          {ocupado === "asistir" ? <Loader2 className="size-4 animate-spin" /> : <UserCheck className="size-4" />} Registrar mi asistencia
        </Button>
      )}
    </div>
  );
}

// --- Puntos ---------------------------------------------------------------------------------------------

type Accion = (id: string, ruta: string, body?: unknown, exito?: string, metodo?: string) => Promise<AsambleaDetalle | null>;

function PuntoFila({
  a,
  p,
  gestiona,
  registra,
  residente,
  ocupado,
  accion,
}: {
  a: AsambleaDetalle;
  p: Punto;
  gestiona: boolean;
  registra: boolean;
  residente: boolean;
  ocupado: string | null;
  accion: Accion;
}) {
  const [conclusion, setConclusion] = useState(false);
  const enCurso = a.estado === "EN_CURSO";
  const votacion = p.tipo === "VOTACION";
  const hayAbierto = a.puntos_lista.some((x) => x.estado === "EN_VOTACION");

  return (
    <li className={cn("px-4 py-3", p.estado === "EN_VOTACION" && "bg-info-soft/30")}>
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <span className="w-6 pt-0.5 text-right text-sm text-muted-foreground tabular-nums">{p.orden}.</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{p.titulo}</span>
            {votacion && p.mayoria && (
              <span className="text-xs text-muted-foreground" title={MAYORIA[p.mayoria].ayuda}>
                {MAYORIA[p.mayoria].label}
              </span>
            )}
            {p.estado === "EN_VOTACION" && <Etiqueta tono="info">En votación · {p.votos} {p.votos === 1 ? "voto" : "votos"}</Etiqueta>}
            {p.estado === "CERRADO" && votacion && p.mayoria !== "ELECCION" && (p.aprobado ? <Etiqueta tono="success">Aprobado</Etiqueta> : <Etiqueta tono="danger">No aprobado</Etiqueta>)}
            {p.estado === "CERRADO" && p.mayoria === "ELECCION" && p.resultado?.ganador && <Etiqueta tono="success">Elegido: {p.resultado.ganador}</Etiqueta>}
            {p.estado === "CERRADO" && !votacion && <Etiqueta tono="neutral">Tratado</Etiqueta>}
            {a.estado === "CERRADA" && p.estado !== "CERRADO" && <Etiqueta tono="warning">Sin tratar</Etiqueta>}
          </div>
          {p.descripcion && <p className="mt-0.5 text-sm text-muted-foreground">{p.descripcion}</p>}
          {p.resultado && <ResultadoBarras p={p} />}
          {p.conclusion && p.conclusion !== p.resultado?.explicacion && <p className="mt-1.5 text-sm italic">{p.conclusion}</p>}
          {residente && p.estado === "EN_VOTACION" && <VotoResidente a={a} p={p} ocupado={ocupado} accion={accion} />}
          {residente && p.estado === "CERRADO" && Object.keys(p.mis_votos).length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">Su voto: {Object.entries(p.mis_votos).map(([u, o]) => `${u} → ${o}`).join(" · ")}</p>
          )}
          {registra && p.estado === "EN_VOTACION" && <VotoSala a={a} p={p} ocupado={ocupado} accion={accion} />}
        </div>
        {gestiona && (
          <div className="flex flex-wrap gap-2">
            {a.estado === "PROGRAMADA" && (
              <Button size="icon" variant="ghost" aria-label={`Quitar el punto ${p.orden}`} disabled={!!ocupado} onClick={() => accion(`quitar-${p.id}`, `/puntos/${p.id}`, undefined, "Punto quitado", "DELETE")}>
                <Trash2 className="size-4" />
              </Button>
            )}
            {enCurso && votacion && p.estado === "PENDIENTE" && (
              <Button size="sm" variant="outline" disabled={hayAbierto || !a.quorum?.hay_quorum || !!ocupado} title={!a.quorum?.hay_quorum ? "No se puede votar sin quórum" : hayAbierto ? "Cierre primero la votación abierta" : undefined} onClick={() => accion(`abrir-${p.id}`, `/puntos/${p.id}/abrir`, undefined, "Votación abierta")}>
                <Vote className="size-4" /> Abrir votación
              </Button>
            )}
            {enCurso && p.estado !== "CERRADO" && (votacion ? p.estado === "EN_VOTACION" : true) && (
              <Button size="sm" variant={p.estado === "EN_VOTACION" ? "default" : "outline"} disabled={!!ocupado} onClick={() => (votacion ? accion(`cerrar-${p.id}`, `/puntos/${p.id}/cerrar`, undefined, "Votación cerrada: resultado fijado") : setConclusion(true))}>
                {ocupado === `cerrar-${p.id}` ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                {votacion ? "Cerrar votación" : "Marcar tratado"}
              </Button>
            )}
          </div>
        )}
      </div>
      {conclusion && <ConclusionDialog p={p} onClose={() => setConclusion(false)} accion={accion} />}
    </li>
  );
}

function ResultadoBarras({ p }: { p: Punto }) {
  const r = p.resultado!;
  const total = Number(r.total) || 1;
  const umbral = p.mayoria === "CALIFICADA_70" ? 70 : null;
  return (
    <div className="mt-2 max-w-xl space-y-1.5">
      {p.opciones.map((o) => {
        const v = Number(r.por_opcion[o] ?? 0);
        const ancho = (v / total) * 100;
        return (
          <div key={o} className="text-xs">
            <div className="flex justify-between gap-2">
              <span>{o}</span>
              <span className="text-muted-foreground tabular-nums">
                {r.unidades_por_opcion[o] ?? 0} unid. · {pct(ancho)}
              </span>
            </div>
            <div className="relative mt-0.5 h-2 rounded-full bg-muted">
              <div className={cn("h-2 rounded-full", o === r.ganador || (o === "Sí" && r.aprobado) ? "bg-primary" : "bg-muted-foreground/40")} style={{ width: `${Math.min(100, ancho)}%` }} />
              {umbral && o === p.opciones[0] && <div className="absolute top-[-2px] h-3 w-px bg-foreground/60" style={{ left: `${umbral}%` }} title="70 % del conjunto" />}
            </div>
          </div>
        );
      })}
      <p className="pt-0.5 text-xs text-muted-foreground">
        {p.estado === "EN_VOTACION" ? "Parcial · " : ""}
        {r.explicacion} · Porcentajes sobre el total de coeficientes del conjunto.
      </p>
    </div>
  );
}

function VotoResidente({ a, p, ocupado, accion }: { a: AsambleaDetalle; p: Punto; ocupado: string | null; accion: Accion }) {
  const presentes = a.padron.filter((u) => u.presente);
  const pendientes = presentes.filter((u) => !p.mis_votos[u.etiqueta]);
  const votadas = Object.entries(p.mis_votos);
  if (!a.soy_votante) return null;
  if (!presentes.length) return <p className="mt-2 text-sm text-muted-foreground">Para votar, registre primero su asistencia.</p>;
  return (
    <div className="mt-2 rounded-md border bg-card p-3">
      {votadas.length > 0 && <p className="text-sm text-success">Voto registrado: {votadas.map(([u, o]) => `${u} → ${o}`).join(" · ")}</p>}
      {pendientes.length > 0 && (
        <>
          <p className="text-sm font-medium">Su voto{pendientes.length > 1 ? ` (por ${pendientes.map((u) => u.etiqueta).join(", ")})` : ""}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {p.opciones.map((o) => (
              <Button key={o} variant="outline" disabled={!!ocupado} onClick={() => accion(`votar-${p.id}`, `/puntos/${p.id}/votar`, { opcion: o }, "Voto registrado")}>
                {o}
              </Button>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">El voto no se puede cambiar después de emitido.</p>
        </>
      )}
    </div>
  );
}

/** Registro de votos en la sala: unidades presentes que aún no votan, con un botón por opción. */
function VotoSala({ a, p, ocupado, accion }: { a: AsambleaDetalle; p: Punto; ocupado: string | null; accion: Accion }) {
  const [filtro, setFiltro] = useState("");
  const votaron = new Set(a.votaron);
  const faltan = a.padron.filter((u) => u.presente && !votaron.has(u.unidad_id));
  const visibles = faltan.filter((u) => !filtro || `${u.etiqueta} ${u.asistente ?? ""}`.toLowerCase().includes(filtro.toLowerCase()));
  return (
    <div className="mt-3 rounded-md border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <p className="text-sm font-medium">
          Votos en la sala · faltan {faltan.length} de {a.padron.filter((u) => u.presente).length} unidades presentes
        </p>
        <div className="relative w-48">
          <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder="Unidad o nombre" aria-label="Buscar unidad para votar" className="h-8 pl-7 text-sm" />
        </div>
      </div>
      {!faltan.length ? (
        <p className="px-3 py-3 text-sm text-muted-foreground">Todas las unidades presentes ya votaron.</p>
      ) : (
        <ul className="max-h-72 divide-y overflow-y-auto">
          {visibles.slice(0, 60).map((u) => (
            <li key={u.unidad_id} className="flex flex-wrap items-center gap-2 px-3 py-1.5">
              <span className="w-20 text-sm font-medium">{u.etiqueta}</span>
              <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                {u.asistente} · {pct(Number(u.coeficiente))}
              </span>
              <div className="flex flex-wrap gap-1" role="group" aria-label={`Voto de ${u.etiqueta}`}>
                {p.opciones.map((o) => (
                  <Button key={o} size="sm" variant="outline" className="h-7 px-2 text-xs" disabled={!!ocupado} onClick={() => accion(`voto-${u.unidad_id}`, `/puntos/${p.id}/votos`, { unidad_id: u.unidad_id, opcion: o })}>
                    {o}
                  </Button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- Padrón y asistencia ------------------------------------------------------------------------------

function PadronPanel({ a, registra, accion, ocupado }: { a: AsambleaDetalle; registra: boolean; accion: Accion; ocupado: string | null }) {
  const [filtro, setFiltro] = useState("");
  const [vista, setVista] = useState<"todas" | "presentes" | "ausentes">("todas");
  const [registrar, setRegistrar] = useState<Padron | null>(null);
  const filas = useMemo(
    () =>
      a.padron.filter(
        (u) =>
          (vista === "todas" || (vista === "presentes") === u.presente) &&
          (!filtro || `${u.etiqueta} ${u.propietarios ?? ""} ${u.asistente ?? ""}`.toLowerCase().includes(filtro.toLowerCase())),
      ),
    [a.padron, filtro, vista],
  );
  const apoderados = a.padron.filter((u) => u.tipo === "APODERADO").length;
  return (
    <Seccion titulo="Padrón y asistencia" descripcion={`${a.padron.length} unidades con derecho a voto · ${apoderados} representadas por apoderado · máximo ${a.max_poderes_por_apoderado} poderes por persona`}>
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2">
        <div className="flex gap-1 rounded-lg bg-muted p-1 text-sm" role="group" aria-label="Filtro de asistencia">
          {(
            [
              ["todas", "Todas"],
              ["presentes", "Presentes"],
              ["ausentes", "Ausentes"],
            ] as const
          ).map(([v, l]) => (
            <button key={v} type="button" aria-pressed={vista === v} onClick={() => setVista(v)} className={cn("rounded-md px-3 py-1 font-medium", vista === v ? "bg-card shadow-sm" : "text-muted-foreground")}>
              {l}
            </button>
          ))}
        </div>
        <div className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder="Unidad, propietario o asistente" aria-label="Buscar en el padrón" className="pl-8" />
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b">
              <th className="px-4 py-2 font-medium">Unidad</th>
              <th className="px-2 py-2 font-medium">Propietarios</th>
              <th className="px-2 py-2 text-right font-medium">Coeficiente</th>
              <th className="px-2 py-2 font-medium">Asistencia</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {filas.map((u) => (
              <tr key={u.unidad_id}>
                <td className="px-4 py-2 font-medium whitespace-nowrap">
                  {u.etiqueta}
                  {u.al_dia === false && (
                    <span className="ml-1.5 text-xs font-normal text-warning" title="Tiene saldo vencido. Conserva el derecho a voto.">
                      en mora
                    </span>
                  )}
                </td>
                <td className="max-w-56 truncate px-2 py-2 text-muted-foreground">{u.propietarios ?? "—"}</td>
                <td className="px-2 py-2 text-right tabular-nums">{pct(Number(u.coeficiente))}</td>
                <td className="px-2 py-2">
                  {u.presente ? (
                    <span className="text-xs">
                      <span className="font-medium text-success">Presente</span> · {u.tipo === "APODERADO" ? `apoderado: ${u.asistente}` : u.asistente}
                      {u.virtual ? " · virtual" : ""}
                      {u.llegada_at ? ` · ${hora(u.llegada_at)}` : ""}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">Ausente</span>
                  )}
                </td>
                <td className="px-4 py-2 text-right whitespace-nowrap">
                  {registra &&
                    (u.presente ? (
                      <Button size="sm" variant="ghost" disabled={!!ocupado} onClick={() => accion(`retiro-${u.unidad_id}`, `/asistencias/${u.asistencia_id}/retiro`, undefined, `${u.etiqueta} se retiró: deja de contar para el quórum`)}>
                        <LogOut className="size-4" /> Retiro
                      </Button>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => setRegistrar(u)}>
                        <UserCheck className="size-4" /> Registrar
                      </Button>
                    ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filas.length && <p className="px-4 py-6 text-center text-sm text-muted-foreground">Ninguna unidad coincide.</p>}
      </div>
      {registrar && (
        <AsistenciaDialog
          u={registrar}
          onClose={() => setRegistrar(null)}
          onConfirmar={(body) => accion("asistencia", `/${a.id}/asistencias`, { unidad_id: registrar.unidad_id, ...body }, `${registrar.etiqueta} registrada`)}
        />
      )}
    </Seccion>
  );
}

// --- Diálogos -------------------------------------------------------------------------------------------

function AsistenciaDialog({ u, onClose, onConfirmar }: { u: Padron; onClose: () => void; onConfirmar: (body: object) => Promise<AsambleaDetalle | null> }) {
  const propietarios = (u.propietarios ?? "").split(",").map((x) => x.trim()).filter(Boolean);
  const [tipo, setTipo] = useState<"PROPIETARIO" | "APODERADO">("PROPIETARIO");
  const [nombre, setNombre] = useState(propietarios[0] ?? "");
  const [documento, setDocumento] = useState("");
  const [enviando, setEnviando] = useState(false);
  const valido = nombre.trim().length >= 3 && (tipo === "PROPIETARIO" || documento.trim().length >= 3);

  async function guardar() {
    setEnviando(true);
    const r = await onConfirmar({ tipo, asistente_nombre: nombre.trim(), asistente_documento: documento.trim() || null });
    setEnviando(false);
    if (r) onClose();
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Registrar asistencia · {u.etiqueta}</DialogTitle>
          <DialogDescription>Coeficiente {pct(Number(u.coeficiente))}. Propietarios: {u.propietarios ?? "sin registrar"}.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex gap-1 rounded-lg bg-muted p-1 text-sm" role="group" aria-label="Calidad">
            {(
              [
                ["PROPIETARIO", "Propietario"],
                ["APODERADO", "Apoderado (con poder)"],
              ] as const
            ).map(([v, l]) => (
              <button
                key={v}
                type="button"
                aria-pressed={tipo === v}
                onClick={() => {
                  setTipo(v);
                  setNombre(v === "PROPIETARIO" ? (propietarios[0] ?? "") : "");
                }}
                className={cn("flex-1 rounded-md px-3 py-1.5 font-medium", tipo === v ? "bg-card shadow-sm" : "text-muted-foreground")}
              >
                {l}
              </button>
            ))}
          </div>
          {tipo === "PROPIETARIO" && propietarios.length > 1 ? (
            <Campo label="Quién asiste">
              <select className={campoClase()} value={nombre} onChange={(e) => setNombre(e.target.value)}>
                {propietarios.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </Campo>
          ) : (
            <Campo label={tipo === "APODERADO" ? "Nombre del apoderado" : "Nombre"}>
              <Input value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus={tipo === "APODERADO"} />
            </Campo>
          )}
          {tipo === "APODERADO" && (
            <Campo label="Documento del apoderado" ayuda="Con él se controla el máximo de poderes por persona. Conserve el poder firmado.">
              <Input value={documento} onChange={(e) => setDocumento(e.target.value)} inputMode="numeric" />
            </Campo>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={guardar} disabled={!valido || enviando}>
            {enviando && <Loader2 className="size-4 animate-spin" />} Registrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InstalarDialog({ onClose, onConfirmar }: { onClose: () => void; onConfirmar: (body: object) => Promise<AsambleaDetalle | null> }) {
  const [presidente, setPresidente] = useState("");
  const [secretario, setSecretario] = useState("");
  const [enviando, setEnviando] = useState(false);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Instalar la asamblea</DialogTitle>
          <DialogDescription>
            Se fija el padrón con las unidades, coeficientes y propietarios de hoy; los cambios posteriores en el censo no alteran el quórum. Después se registra la asistencia.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Campo label="Presidente de la asamblea">
            <Input value={presidente} onChange={(e) => setPresidente(e.target.value)} autoFocus />
          </Campo>
          <Campo label="Secretario">
            <Input value={secretario} onChange={(e) => setSecretario(e.target.value)} />
          </Campo>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            disabled={presidente.trim().length < 3 || secretario.trim().length < 3 || enviando}
            onClick={async () => {
              setEnviando(true);
              const r = await onConfirmar({ presidente: presidente.trim(), secretario: secretario.trim() });
              setEnviando(false);
              if (r) onClose();
            }}
          >
            {enviando ? <Loader2 className="size-4 animate-spin" /> : <Gavel className="size-4" />} Instalar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CerrarDialog({ pendientes, onClose, onConfirmar }: { pendientes: number; onClose: () => void; onConfirmar: (obs: string) => Promise<AsambleaDetalle | null> }) {
  const [obs, setObs] = useState("");
  const [enviando, setEnviando] = useState(false);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Cerrar la asamblea</DialogTitle>
          <DialogDescription>
            {pendientes ? `Quedan ${pendientes} puntos sin tratar; quedarán así en el acta. ` : ""}
            Al cerrarla nada se puede modificar y queda lista el acta.
          </DialogDescription>
        </DialogHeader>
        <Campo label="Observaciones (opcional)" ayuda="Aparecen en el acta: comisión verificadora, constancias, etc.">
          <textarea className={textareaClase()} value={obs} onChange={(e) => setObs(e.target.value)} />
        </Campo>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            disabled={enviando}
            onClick={async () => {
              setEnviando(true);
              const r = await onConfirmar(obs.trim());
              setEnviando(false);
              if (r) onClose();
            }}
          >
            {enviando && <Loader2 className="size-4 animate-spin" />} Cerrar asamblea
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ConclusionDialog({ p, onClose, accion }: { p: Punto; onClose: () => void; accion: Accion }) {
  const { tenant } = useTenant();
  const [texto, setTexto] = useState(p.conclusion ?? "");
  const [enviando, setEnviando] = useState(false);
  async function guardar() {
    setEnviando(true);
    try {
      if (texto.trim() && texto.trim() !== p.conclusion) {
        await api(`${baseAsambleas(tenant.tenant_id)}/puntos/${p.id}`, { method: "PATCH", json: { conclusion: texto.trim() } });
      }
      const r = await accion(`cerrar-${p.id}`, `/puntos/${p.id}/cerrar`, undefined, "Punto tratado");
      if (r) onClose();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {p.orden}. {p.titulo}
          </DialogTitle>
          <DialogDescription>Resuma lo tratado o decidido; aparece en el acta.</DialogDescription>
        </DialogHeader>
        <textarea className={textareaClase()} value={texto} onChange={(e) => setTexto(e.target.value)} aria-label="Conclusión" autoFocus />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={guardar} disabled={enviando}>
            {enviando && <Loader2 className="size-4 animate-spin" />} Marcar tratado
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NuevoPuntoDialog({ onClose, onConfirmar }: { onClose: () => void; onConfirmar: (body: object) => Promise<AsambleaDetalle | null> }) {
  const [titulo, setTitulo] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [tipo, setTipo] = useState<"INFORMATIVO" | "VOTACION">("INFORMATIVO");
  const [mayoria, setMayoria] = useState<Mayoria>("SIMPLE");
  const [opciones, setOpciones] = useState("");
  const [enviando, setEnviando] = useState(false);
  const listaOpciones = opciones.split(/[\n,]/).map((o) => o.trim()).filter(Boolean);
  const valido = titulo.trim().length >= 3 && (tipo === "INFORMATIVO" || mayoria !== "ELECCION" || listaOpciones.length >= 2);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Agregar punto al orden del día</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Campo label="Título">
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} autoFocus />
          </Campo>
          <Campo label="Descripción (opcional)">
            <textarea className={textareaClase()} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          </Campo>
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo label="Tipo">
              <select className={campoClase()} value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)}>
                <option value="INFORMATIVO">Informativo</option>
                <option value="VOTACION">Se vota</option>
              </select>
            </Campo>
            {tipo === "VOTACION" && (
              <Campo label="Mayoría requerida" ayuda={MAYORIA[mayoria].ayuda}>
                <select className={campoClase()} value={mayoria} onChange={(e) => setMayoria(e.target.value as Mayoria)}>
                  {(Object.keys(MAYORIA) as Mayoria[]).map((m) => (
                    <option key={m} value={m}>
                      {MAYORIA[m].label}
                    </option>
                  ))}
                </select>
              </Campo>
            )}
          </div>
          {tipo === "VOTACION" && (
            <Campo label={mayoria === "ELECCION" ? "Candidatos o planchas" : "Opciones (opcional)"} ayuda={mayoria === "ELECCION" ? "Separados por coma" : "Si lo deja vacío: Sí, No, Abstención"}>
              <Input value={opciones} onChange={(e) => setOpciones(e.target.value)} />
            </Campo>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            disabled={!valido || enviando}
            onClick={async () => {
              setEnviando(true);
              const r = await onConfirmar({
                titulo: titulo.trim(),
                descripcion: descripcion.trim() || null,
                tipo,
                ...(tipo === "VOTACION" ? { mayoria, opciones: listaOpciones } : {}),
              });
              setEnviando(false);
              if (r) onClose();
            }}
          >
            {enviando && <Loader2 className="size-4 animate-spin" />} Agregar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
