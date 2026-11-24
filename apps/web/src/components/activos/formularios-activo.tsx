"use client";

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { campoClase, mensajeError } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, fetcher } from "@/lib/api";
import {
  type ActivoDetalle,
  baseActivos,
  type Categoria,
  CRITICIDAD,
  type Criticidad,
  ESTADO_ACTIVO,
  type EstadoActivo,
  type Contratista,
  TIPO_DOCUMENTO,
  type TipoDocumentoActivo,
} from "@/lib/activos";
import { hoyBogota } from "@/lib/recaudos";
import type { DocumentItem } from "@/lib/types";

import { Campo, textareaClase } from "./comunes";

const vacio = (v: string) => (v.trim() === "" ? null : v.trim());

interface PropsDialogo {
  tenantId: string;
  abierto: boolean;
  onCambio: (v: boolean) => void;
}

// --- Activo: alta y edición -----------------------------------------------------------------

interface FormActivo {
  nombre: string;
  categoria_id: string;
  subtipo: string;
  ubicacion: string;
  marca: string;
  modelo: string;
  fabricante: string;
  numero_serie: string;
  fecha_instalacion: string;
  vida_util_anios: string;
  fecha_vencimiento_garantia: string;
  criticidad: Criticidad;
  mantenedor_id: string;
  instalador_id: string;
  estado: EstadoActivo;
}

function inicial(a?: ActivoDetalle): FormActivo {
  return {
    nombre: a?.nombre ?? "",
    categoria_id: a?.categoria.id ?? "",
    subtipo: a?.subtipo ?? "",
    ubicacion: a?.ubicacion ?? "",
    marca: a?.marca ?? "",
    modelo: a?.modelo ?? "",
    fabricante: a?.fabricante ?? "",
    numero_serie: a?.numero_serie ?? "",
    fecha_instalacion: a?.fecha_instalacion ?? "",
    vida_util_anios: a?.vida_util_anios ? String(a.vida_util_anios) : "",
    fecha_vencimiento_garantia: a?.fecha_vencimiento_garantia ?? "",
    criticidad: a?.criticidad ?? "MEDIA",
    mantenedor_id: a?.mantenedor?.id ?? "",
    instalador_id: a?.instalador?.id ?? "",
    estado: a?.estado ?? "OPERATIVO",
  };
}

function aJson(f: FormActivo, esp: [string, string][]) {
  return {
    nombre: f.nombre.trim(),
    categoria_id: f.categoria_id,
    subtipo: vacio(f.subtipo),
    ubicacion: f.ubicacion.trim(),
    marca: vacio(f.marca),
    modelo: vacio(f.modelo),
    fabricante: vacio(f.fabricante),
    numero_serie: vacio(f.numero_serie),
    fecha_instalacion: f.fecha_instalacion || null,
    vida_util_anios: f.vida_util_anios ? Number(f.vida_util_anios) : null,
    fecha_vencimiento_garantia: f.fecha_vencimiento_garantia || null,
    criticidad: f.criticidad,
    mantenedor_id: f.mantenedor_id || null,
    instalador_id: f.instalador_id || null,
    especificaciones: Object.fromEntries(esp.filter(([k, v]) => k.trim() && v.trim()).map(([k, v]) => [k.trim(), v.trim()])),
  };
}

export function ActivoFormDialog({
  tenantId,
  abierto,
  onCambio,
  activo,
  onGuardado,
}: PropsDialogo & { activo?: ActivoDetalle; onGuardado: (a: ActivoDetalle) => void }) {
  const b = baseActivos(tenantId);
  const { data: categorias } = useSWR<Categoria[]>(abierto ? `${b}/categorias` : null, fetcher);
  const { data: contratistas } = useSWR<Contratista[]>(abierto ? `${b}/contratistas` : null, fetcher);
  const [f, setF] = useState<FormActivo>(() => inicial(activo));
  const [esp, setEsp] = useState<[string, string][]>([]);
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    setF(inicial(activo));
    setEsp(activo ? Object.entries(activo.especificaciones).map(([k, v]) => [k, String(v)]) : [["", ""]]);
    setMotivo("");
  }, [abierto, activo]);

  const categoria = categorias?.find((c) => c.id === f.categoria_id);
  const set = <K extends keyof FormActivo>(k: K, v: FormActivo[K]) => setF((x) => ({ ...x, [k]: v }));
  const valido = f.nombre.trim().length >= 2 && f.categoria_id && f.ubicacion.trim().length >= 2 && (!activo || motivo.trim().length >= 5);

  async function guardar() {
    setEnviando(true);
    try {
      const datos = aJson(f, esp);
      let r: ActivoDetalle;
      if (activo) {
        // Solo lo que cambió: la auditoría registra exactamente esos campos con el motivo
        const antes = aJson(inicial(activo), Object.entries(activo.especificaciones).map(([k, v]) => [k, String(v)]));
        const cambios: Record<string, unknown> = Object.fromEntries(
          Object.entries(datos).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(antes[k as keyof typeof antes])),
        );
        if (f.estado !== activo.estado) cambios.estado = f.estado;
        if (!Object.keys(cambios).length) {
          toast.info("No hay cambios para guardar");
          return;
        }
        r = await api<ActivoDetalle>(`${b}/${activo.id}`, { method: "PATCH", json: { ...cambios, motivo: motivo.trim() } });
        toast.success("Hoja de vida actualizada");
      } else {
        r = await api<ActivoDetalle>(b, { method: "POST", json: datos });
        toast.success(`Activo ${r.codigo_interno} registrado`);
      }
      onGuardado(r);
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{activo ? `Editar ${activo.codigo_interno}` : "Nuevo activo"}</DialogTitle>
          <DialogDescription>
            {activo ? "Los cambios quedan en la auditoría con su motivo." : "El código interno y el QR se generan al guardar."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo label="Nombre" className="sm:col-span-2">
            <Input value={f.nombre} onChange={(e) => set("nombre", e.target.value)} placeholder="Ascensor torre 1" autoFocus />
          </Campo>
          <Campo label="Categoría">
            <select value={f.categoria_id} onChange={(e) => set("categoria_id", e.target.value)} className={campoClase()}>
              <option value="">Seleccione…</option>
              {categorias?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nombre}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Tipo" ayuda="Elija uno de la lista o escriba otro">
            <Input value={f.subtipo} onChange={(e) => set("subtipo", e.target.value)} list="subtipos-activo" />
            <datalist id="subtipos-activo">
              {categoria?.subtipos.map((s) => <option key={s} value={s} />)}
            </datalist>
          </Campo>
          <Campo label="Ubicación" className="sm:col-span-2">
            <Input value={f.ubicacion} onChange={(e) => set("ubicacion", e.target.value)} placeholder="Torre 1 · Sótano 2 · Cuarto de bombas" />
          </Campo>
          <Campo label="Marca">
            <Input value={f.marca} onChange={(e) => set("marca", e.target.value)} />
          </Campo>
          <Campo label="Modelo">
            <Input value={f.modelo} onChange={(e) => set("modelo", e.target.value)} />
          </Campo>
          <Campo label="Fabricante">
            <Input value={f.fabricante} onChange={(e) => set("fabricante", e.target.value)} />
          </Campo>
          <Campo label="Número de serie">
            <Input value={f.numero_serie} onChange={(e) => set("numero_serie", e.target.value)} />
          </Campo>
          <Campo label="Fecha de instalación">
            <input type="date" max={hoyBogota()} value={f.fecha_instalacion} onChange={(e) => set("fecha_instalacion", e.target.value)} className={campoClase()} />
          </Campo>
          <Campo label="Vida útil (años)">
            <Input type="number" min={1} max={200} value={f.vida_util_anios} onChange={(e) => set("vida_util_anios", e.target.value)} />
          </Campo>
          <Campo label="Fin de la garantía">
            <input type="date" value={f.fecha_vencimiento_garantia} onChange={(e) => set("fecha_vencimiento_garantia", e.target.value)} className={campoClase()} />
          </Campo>
          <Campo label="Criticidad" ayuda="Qué tanto afecta a la copropiedad si falla">
            <select value={f.criticidad} onChange={(e) => set("criticidad", e.target.value as Criticidad)} className={campoClase()}>
              {(Object.keys(CRITICIDAD) as Criticidad[]).map((c) => (
                <option key={c} value={c}>
                  {CRITICIDAD[c].label}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Contratista que lo mantiene">
            <select value={f.mantenedor_id} onChange={(e) => set("mantenedor_id", e.target.value)} className={campoClase()}>
              <option value="">Ninguno (personal interno)</option>
              {contratistas?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.razon_social}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Instalado por">
            <select value={f.instalador_id} onChange={(e) => set("instalador_id", e.target.value)} className={campoClase()}>
              <option value="">Sin dato</option>
              {contratistas?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.razon_social}
                </option>
              ))}
            </select>
          </Campo>
          {activo && (
            <Campo label="Estado" ayuda="Para dar de baja use la acción «Dar de baja»" className="sm:col-span-2">
              <select value={f.estado} onChange={(e) => set("estado", e.target.value as EstadoActivo)} className={campoClase()}>
                {(Object.keys(ESTADO_ACTIVO) as EstadoActivo[])
                  .filter((e) => e !== "DADO_DE_BAJA")
                  .map((e) => (
                    <option key={e} value={e}>
                      {ESTADO_ACTIVO[e].label}
                    </option>
                  ))}
              </select>
            </Campo>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Especificaciones técnicas</p>
          {esp.map(([k, v], i) => (
            <div key={i} className="flex gap-2">
              <Input
                value={k}
                onChange={(e) => setEsp(esp.map((x, j) => (j === i ? [e.target.value, x[1]] : x)))}
                placeholder="Potencia"
                className="w-2/5"
                aria-label="Nombre de la especificación"
              />
              <Input
                value={v}
                onChange={(e) => setEsp(esp.map((x, j) => (j === i ? [x[0], e.target.value] : x)))}
                placeholder="15 HP"
                aria-label="Valor de la especificación"
              />
              <Button type="button" variant="ghost" size="icon" onClick={() => setEsp(esp.filter((_, j) => j !== i))} aria-label="Quitar especificación">
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={() => setEsp([...esp, ["", ""]])}>
            <Plus className="size-4" /> Agregar especificación
          </Button>
        </div>

        {activo && (
          <Campo label="Motivo del cambio" ayuda="Queda en la auditoría con su nombre">
            <Input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Dato tomado de la placa del equipo" />
          </Campo>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!valido || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            {activo ? "Guardar cambios" : "Registrar activo"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Documentos -------------------------------------------------------------------------------

export function VincularDocumentoDialog({
  tenantId,
  abierto,
  onCambio,
  activoId,
  yaVinculados,
  onGuardado,
}: PropsDialogo & { activoId: string; yaVinculados: string[]; onGuardado: () => void }) {
  const { data: docs } = useSWR<DocumentItem[]>(abierto ? `/tenants/${tenantId}/documents?limit=200` : null, fetcher);
  const [texto, setTexto] = useState("");
  const [docId, setDocId] = useState("");
  const [tipo, setTipo] = useState<TipoDocumentoActivo>("MANUAL");
  const [fecha, setFecha] = useState("");
  const [enviando, setEnviando] = useState(false);

  const opciones = useMemo(
    () =>
      (docs ?? []).filter(
        (d) => d.status === "READY" && !yaVinculados.includes(d.id) && d.title.toLowerCase().includes(texto.trim().toLowerCase()),
      ),
    [docs, texto, yaVinculados],
  );

  async function guardar() {
    setEnviando(true);
    try {
      await api(`${baseActivos(tenantId)}/${activoId}/documentos`, {
        method: "POST",
        json: { document_id: docId, tipo, fecha_documento: fecha || null },
      });
      toast.success("Documento vinculado");
      setDocId("");
      onGuardado();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Vincular un documento</DialogTitle>
          <DialogDescription>
            Elija un documento del archivo (manual, garantía, contrato…). Sigue disponible en Documentos y en el buscador con IA; si tiene
            vencimientos, aparecerán en la hoja de vida.
          </DialogDescription>
        </DialogHeader>
        <Input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Buscar por título" />
        <ul className="max-h-56 space-y-1 overflow-y-auto rounded-md border p-1" role="listbox" aria-label="Documentos">
          {opciones.map((d) => (
            <li key={d.id}>
              <button
                type="button"
                role="option"
                aria-selected={docId === d.id}
                onClick={() => setDocId(d.id)}
                className={`w-full rounded px-2 py-1.5 text-left text-sm hover:bg-accent ${docId === d.id ? "bg-accent font-medium" : ""}`}
              >
                {d.title}
              </button>
            </li>
          ))}
          {docs && opciones.length === 0 && <li className="px-2 py-3 text-sm text-muted-foreground">No hay documentos para vincular. Súbalos primero en Documentos.</li>}
        </ul>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo label="Tipo">
            <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoDocumentoActivo)} className={campoClase()}>
              {(Object.keys(TIPO_DOCUMENTO) as TipoDocumentoActivo[]).map((t) => (
                <option key={t} value={t}>
                  {TIPO_DOCUMENTO[t]}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Fecha del documento">
            <input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} className={campoClase()} />
          </Campo>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!docId || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Vincular
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Horómetro ----------------------------------------------------------------------------------

export function LecturaDialog({
  tenantId,
  abierto,
  onCambio,
  activoId,
  ultima,
  onGuardado,
}: PropsDialogo & { activoId: string; ultima?: string | null; onGuardado: () => void }) {
  const [horas, setHoras] = useState("");
  const [enviando, setEnviando] = useState(false);
  const minimo = ultima ? Number(ultima) : 0;
  const valido = horas !== "" && Number(horas) >= minimo;

  async function guardar() {
    setEnviando(true);
    try {
      await api(`${baseActivos(tenantId)}/${activoId}/lecturas`, { method: "POST", json: { horas_acumuladas: horas } });
      toast.success("Lectura registrada");
      setHoras("");
      onGuardado();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Lectura del horómetro</DialogTitle>
          <DialogDescription>
            Horas acumuladas que marca el equipo.{ultima ? ` La última lectura fue ${Number(ultima).toLocaleString("es-CO")} h.` : ""}
          </DialogDescription>
        </DialogHeader>
        <Input type="number" inputMode="decimal" step="0.1" min={minimo} value={horas} onChange={(e) => setHoras(e.target.value)} autoFocus aria-label="Horas acumuladas" />
        {horas !== "" && !valido && <p className="text-xs text-destructive">Debe ser mayor o igual a la última lectura.</p>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={!valido || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Registrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Contratistas --------------------------------------------------------------------------------

export function ContratistaFormDialog({
  tenantId,
  abierto,
  onCambio,
  contratista,
  onGuardado,
}: PropsDialogo & { contratista?: Contratista; onGuardado: () => void }) {
  const [f, setF] = useState({
    razon_social: "",
    nit: "",
    contacto_nombre: "",
    telefono: "",
    email: "",
    especialidades: "",
    vigencia_contrato_inicio: "",
    vigencia_contrato_fin: "",
    valor_contrato: "",
    periodicidad_pactada: "",
    alcance_contrato: "",
  });
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    setF({
      razon_social: contratista?.razon_social ?? "",
      nit: contratista?.nit ?? "",
      contacto_nombre: contratista?.contacto_nombre ?? "",
      telefono: contratista?.telefono ?? "",
      email: contratista?.email ?? "",
      especialidades: contratista?.especialidades.join(", ") ?? "",
      vigencia_contrato_inicio: contratista?.vigencia_contrato_inicio ?? "",
      vigencia_contrato_fin: contratista?.vigencia_contrato_fin ?? "",
      valor_contrato: contratista?.valor_contrato ? String(Math.round(Number(contratista.valor_contrato))) : "",
      periodicidad_pactada: contratista?.periodicidad_pactada ?? "",
      alcance_contrato: contratista?.alcance_contrato ?? "",
    });
  }, [abierto, contratista]);

  const set = (k: keyof typeof f, v: string) => setF((x) => ({ ...x, [k]: v }));

  async function guardar() {
    setEnviando(true);
    try {
      const json = {
        razon_social: f.razon_social.trim(),
        nit: vacio(f.nit),
        contacto_nombre: vacio(f.contacto_nombre),
        telefono: vacio(f.telefono),
        email: vacio(f.email),
        especialidades: f.especialidades.split(",").map((s) => s.trim()).filter(Boolean),
        vigencia_contrato_inicio: f.vigencia_contrato_inicio || null,
        vigencia_contrato_fin: f.vigencia_contrato_fin || null,
        valor_contrato: f.valor_contrato ? f.valor_contrato : null,
        periodicidad_pactada: vacio(f.periodicidad_pactada),
        alcance_contrato: vacio(f.alcance_contrato),
      };
      const b = baseActivos(tenantId);
      if (contratista) await api(`${b}/contratistas/${contratista.id}`, { method: "PATCH", json });
      else await api(`${b}/contratistas`, { method: "POST", json });
      toast.success(contratista ? "Contratista actualizado" : "Contratista registrado");
      onGuardado();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{contratista ? contratista.razon_social : "Nuevo contratista"}</DialogTitle>
          <DialogDescription>Empresa o persona que hace mantenimientos. El fin del contrato genera avisos a 60 y 30 días.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo label="Razón social" className="sm:col-span-2">
            <Input value={f.razon_social} onChange={(e) => set("razon_social", e.target.value)} autoFocus />
          </Campo>
          <Campo label="NIT">
            <Input value={f.nit} onChange={(e) => set("nit", e.target.value)} />
          </Campo>
          <Campo label="Contacto">
            <Input value={f.contacto_nombre} onChange={(e) => set("contacto_nombre", e.target.value)} />
          </Campo>
          <Campo label="Teléfono">
            <Input value={f.telefono} onChange={(e) => set("telefono", e.target.value)} />
          </Campo>
          <Campo label="Correo">
            <Input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} />
          </Campo>
          <Campo label="Especialidades" ayuda="Separadas por comas" className="sm:col-span-2">
            <Input value={f.especialidades} onChange={(e) => set("especialidades", e.target.value)} placeholder="Ascensores, Motobombas" />
          </Campo>
          <Campo label="Inicio del contrato">
            <input type="date" value={f.vigencia_contrato_inicio} onChange={(e) => set("vigencia_contrato_inicio", e.target.value)} className={campoClase()} />
          </Campo>
          <Campo label="Fin del contrato">
            <input type="date" value={f.vigencia_contrato_fin} onChange={(e) => set("vigencia_contrato_fin", e.target.value)} className={campoClase()} />
          </Campo>
          <Campo label="Valor anual del contrato">
            <Input type="number" min={0} value={f.valor_contrato} onChange={(e) => set("valor_contrato", e.target.value)} />
          </Campo>
          <Campo label="Periodicidad pactada">
            <Input value={f.periodicidad_pactada} onChange={(e) => set("periodicidad_pactada", e.target.value)} placeholder="Mensual" />
          </Campo>
          <Campo label="Alcance" className="sm:col-span-2">
            <textarea value={f.alcance_contrato} onChange={(e) => set("alcance_contrato", e.target.value)} className={textareaClase()} />
          </Campo>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={f.razon_social.trim().length < 2 || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
