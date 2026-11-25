"use client";

import { Archive, BellRing, CheckCheck, ChevronDown, Eye, FileText, Loader2, Megaphone, Pencil, Plus, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo, textareaClase } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, mensajeError, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import { basePortal, type Circular, CATEGORIA_CIRCULAR, type CategoriaCircular, puedePortal } from "@/lib/portal";
import { fechaCorta } from "@/lib/recaudos";
import type { ResumenUnidades } from "@/lib/unidades";
import { cn } from "@/lib/utils";

import { Markdown, useRefrescarPortal } from "./comunes";

export function CircularesView() {
  const { tenant } = useTenant();
  const b = basePortal(tenant.tenant_id);
  const residente = tenant.role === "RESIDENTE";
  const redacta = puedePortal(tenant.role, "redactarCircular");
  const publica = puedePortal(tenant.role, "publicarCircular");
  const [archivadas, setArchivadas] = useState(false);
  const { data, isLoading, mutate } = useSWR<Circular[]>(`${b}/circulares${archivadas ? "?incluir_archivadas=true" : ""}`, fetcher);
  const refrescar = useRefrescarPortal();
  const [abierta, setAbierta] = useState<string | null>(null);
  const [editor, setEditor] = useState<Circular | "nueva" | null>(null);

  async function abrir(c: Circular) {
    const nueva = abierta === c.id ? null : c.id;
    setAbierta(nueva);
    if (nueva && c.estado === "PUBLICADA" && !c.leida && residente) {
      try {
        await api(`${b}/circulares/${c.id}/leida`, { method: "POST" });
        void mutate((lista) => lista?.map((x) => (x.id === c.id ? { ...x, leida: true } : x)), { revalidate: false });
        void refrescar(tenant.tenant_id);
      } catch {
        /* marcar leída no debe estorbar la lectura */
      }
    }
  }

  async function accion(c: Circular, que: "publicar" | "archivar") {
    try {
      await api(`${b}/circulares/${c.id}/${que}`, { method: "POST" });
      toast.success(que === "publicar" ? (c.enviar_correo ? "Circular publicada: se está enviando por correo" : "Circular publicada") : "Circular archivada");
      void refrescar(tenant.tenant_id);
    } catch (e) {
      toast.error(mensajeError(e));
    }
  }

  if (!residente && !puedePortal(tenant.role, "verPqrs")) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Circulares"
        description={residente ? "Comunicados de la administración para usted y su torre." : "Comunicados de la administración a los residentes, con acuse de lectura."}
        actions={
          redacta && (
            <Button onClick={() => setEditor("nueva")}>
              <Plus className="size-4" /> Nueva circular
            </Button>
          )
        }
      />
      <div className="mx-auto w-full max-w-4xl space-y-3 p-4 sm:p-6">
        {isLoading ? (
          <Skeleton className="h-64" />
        ) : !data?.length ? (
          <div className="rounded-lg border bg-card">
            <Vacio icono={Megaphone} titulo="No hay circulares" texto={redacta ? "Redacte la primera: puede dirigirla a toda la copropiedad o a una torre." : undefined} />
          </div>
        ) : (
          data.map((c) => (
            <article key={c.id} className={cn("rounded-lg border bg-card", c.importante && c.estado === "PUBLICADA" && "border-primary/40", c.estado !== "PUBLICADA" && "opacity-80")}>
              <button type="button" onClick={() => void abrir(c)} className="flex w-full items-start gap-3 px-4 py-3 text-left" aria-expanded={abierta === c.id}>
                {residente && !c.leida && c.estado === "PUBLICADA" ? (
                  <span className="mt-2 size-2 shrink-0 rounded-full bg-primary" aria-label="Sin leer" />
                ) : (
                  <span className="mt-2 size-2 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {c.importante && (
                      <Etiqueta tono="warning">
                        <BellRing className="mr-1 size-3" /> Importante
                      </Etiqueta>
                    )}
                    {c.estado === "BORRADOR" && <Etiqueta tono="neutral">Borrador</Etiqueta>}
                    {c.estado === "ARCHIVADA" && <Etiqueta tono="neutral">Archivada</Etiqueta>}
                    <span className="text-xs text-muted-foreground">
                      {c.numero && `N.º ${c.numero} · `}
                      {CATEGORIA_CIRCULAR[c.categoria]}
                      {c.torres.length > 0 && ` · torre ${c.torres.join(", ")}`}
                      {c.publicada_at && ` · ${fechaCorta(c.publicada_at)}`}
                    </span>
                  </div>
                  <h2 className={cn("mt-0.5", residente && !c.leida && c.estado === "PUBLICADA" ? "font-semibold" : "font-medium")}>{c.titulo}</h2>
                  {!residente && c.lecturas !== null && c.estado !== "BORRADOR" && (
                    <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <Eye className="size-3.5" /> Leída por {c.lecturas} de {c.destinatarios_con_cuenta ?? 0} residentes con cuenta
                      {c.correos_enviados > 0 && ` · ${c.correos_enviados} correos enviados`}
                    </p>
                  )}
                </div>
                <ChevronDown className={cn("mt-1 size-4 shrink-0 text-muted-foreground transition-transform", abierta === c.id && "rotate-180")} />
              </button>
              {abierta === c.id && (
                <div className="space-y-3 border-t px-4 py-3 sm:pl-9">
                  <Markdown texto={c.cuerpo} />
                  {c.document_id && (
                    <a href={`/${tenant.tenant_slug}/documents?doc=${c.document_id}`} className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
                      <FileText className="size-4" /> {c.documento_titulo ?? "Documento adjunto"}
                    </a>
                  )}
                  {residente && c.leida && c.importante && (
                    <p className="inline-flex items-center gap-1 text-xs text-success">
                      <CheckCheck className="size-3.5" /> Lectura confirmada
                    </p>
                  )}
                  {!residente && (
                    <div className="flex flex-wrap gap-2">
                      {c.estado === "BORRADOR" && redacta && (
                        <Button size="sm" variant="outline" onClick={() => setEditor(c)}>
                          <Pencil className="size-4" /> Editar
                        </Button>
                      )}
                      {c.estado === "BORRADOR" && publica && (
                        <Button size="sm" onClick={() => void accion(c, "publicar")}>
                          <Send className="size-4" /> Publicar{c.enviar_correo ? " y enviar por correo" : ""}
                        </Button>
                      )}
                      {c.estado === "PUBLICADA" && publica && (
                        <Button size="sm" variant="ghost" onClick={() => void accion(c, "archivar")}>
                          <Archive className="size-4" /> Archivar
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </article>
          ))
        )}
        {!residente && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={archivadas} onChange={(e) => setArchivadas(e.target.checked)} className="size-3.5" />
            Mostrar archivadas
          </label>
        )}
      </div>
      {redacta && <EditorCircular circular={editor} onCerrar={() => setEditor(null)} onGuardada={() => refrescar(tenant.tenant_id)} />}
    </div>
  );
}

function EditorCircular({ circular, onCerrar, onGuardada }: { circular: Circular | "nueva" | null; onCerrar: () => void; onGuardada: () => void }) {
  const { tenant } = useTenant();
  const b = basePortal(tenant.tenant_id);
  const { data: resumen } = useSWR<ResumenUnidades>(circular ? `/tenants/${tenant.tenant_id}/unidades/resumen` : null, fetcher);
  const [titulo, setTitulo] = useState("");
  const [cuerpo, setCuerpo] = useState("");
  const [categoria, setCategoria] = useState<CategoriaCircular>("INFORMATIVA");
  const [importante, setImportante] = useState(false);
  const [torres, setTorres] = useState<string[]>([]);
  const [correo, setCorreo] = useState(true);
  const [vista, setVista] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const existente = circular && circular !== "nueva" ? circular : null;

  useEffect(() => {
    if (!circular) return;
    setTitulo(existente?.titulo ?? "");
    setCuerpo(existente?.cuerpo ?? "");
    setCategoria(existente?.categoria ?? "INFORMATIVA");
    setImportante(existente?.importante ?? false);
    setTorres(existente?.torres ?? []);
    setCorreo(existente?.enviar_correo ?? true);
    setVista(false);
  }, [circular, existente]);

  async function guardar() {
    setEnviando(true);
    try {
      const json = { titulo: titulo.trim(), cuerpo: cuerpo.trim(), categoria, importante, torres, enviar_correo: correo };
      if (existente) await api(`${b}/circulares/${existente.id}`, { method: "PATCH", json });
      else await api(`${b}/circulares`, { method: "POST", json });
      toast.success("Borrador guardado. Revíselo y publíquelo cuando esté listo.");
      onGuardada();
      onCerrar();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={!!circular} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{existente ? "Editar borrador" : "Nueva circular"}</DialogTitle>
          <DialogDescription>Se guarda como borrador. Al publicarla queda numerada y ya no se puede editar.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Campo label="Título">
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={200} placeholder="Corte de agua el jueves en la torre 2" />
          </Campo>
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo label="Tipo">
              <select value={categoria} onChange={(e) => setCategoria(e.target.value as CategoriaCircular)} className={campoClase()}>
                {(Object.keys(CATEGORIA_CIRCULAR) as CategoriaCircular[]).map((k) => (
                  <option key={k} value={k}>
                    {CATEGORIA_CIRCULAR[k]}
                  </option>
                ))}
              </select>
            </Campo>
            <div className="flex flex-col gap-1.5 text-sm" role="group" aria-labelledby="dest-titulo">
              <span id="dest-titulo" className="font-medium">
                Para
              </span>
              <div className="flex flex-wrap gap-1.5">
                <button type="button" aria-pressed={!torres.length} onClick={() => setTorres([])} className={cn("rounded-full border px-2.5 py-1 text-xs", !torres.length && "border-primary bg-accent font-medium")}>
                  Toda la copropiedad
                </button>
                {resumen?.torres.map((t) => (
                  <button
                    key={t}
                    type="button"
                    aria-pressed={torres.includes(t)}
                    onClick={() => setTorres((x) => (x.includes(t) ? x.filter((y) => y !== t) : [...x, t]))}
                    className={cn("rounded-full border px-2.5 py-1 text-xs", torres.includes(t) && "border-primary bg-accent font-medium")}
                  >
                    Torre {t}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div>
            <div className="mb-1.5 flex items-center justify-between text-sm">
              <span className="font-medium">Texto</span>
              <button type="button" onClick={() => setVista((v) => !v)} className="text-xs font-medium text-primary hover:underline">
                {vista ? "Editar" : "Vista previa"}
              </button>
            </div>
            {vista ? (
              <div className="min-h-40 rounded-md border bg-card p-3">
                <Markdown texto={cuerpo || "_Sin texto_"} />
              </div>
            ) : (
              <textarea value={cuerpo} onChange={(e) => setCuerpo(e.target.value)} rows={8} className={textareaClase()} aria-label="Texto de la circular" />
            )}
            <p className="mt-1 text-xs text-muted-foreground">Admite formato sencillo: **negrita**, listas con guion y enlaces.</p>
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={importante} onChange={(e) => setImportante(e.target.checked)} className="mt-0.5 size-4" />
            <span>
              Importante
              <span className="block text-xs text-muted-foreground">Se destaca en el inicio de los residentes y se registra quién la leyó.</span>
            </span>
          </label>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={correo} onChange={(e) => setCorreo(e.target.checked)} className="mt-0.5 size-4" />
            <span>
              Enviar por correo al publicar
              <span className="block text-xs text-muted-foreground">También a propietarios sin cuenta que tengan correo en el directorio.</span>
            </span>
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button disabled={titulo.trim().length < 3 || cuerpo.trim().length < 10 || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar borrador
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
