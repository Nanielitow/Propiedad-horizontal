"use client";

import { Loader2, Search, UserPlus, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Campo, textareaClase } from "@/components/activos/comunes";
import { campoClase, mensajeError } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, fetcher } from "@/lib/api";
import { hoyBogota } from "@/lib/recaudos";
import {
  baseTenant,
  baseUnidades,
  esAnexo,
  type Ocupacion,
  OCUPACION,
  type Persona,
  type PersonaDetalle,
  type PersonasPagina,
  type Relacion,
  RELACION,
  TIPO_DOCUMENTO,
  TIPO_UNIDAD,
  TIPO_VEHICULO,
  type TipoDocumento,
  type TipoUnidad,
  type TipoVehiculo,
  type UnidadDetalle,
  type UnidadesPagina,
  type Vehiculo,
  type Vinculo,
} from "@/lib/unidades";
import { cn } from "@/lib/utils";

const vacio = (v: string) => (v.trim() === "" ? null : v.trim());

interface PropsDialogo {
  tenantId: string;
  abierto: boolean;
  onCambio: (v: boolean) => void;
}

function Pie({ onCancelar, enviando, valido, texto, onGuardar }: { onCancelar: () => void; enviando: boolean; valido: boolean; texto: string; onGuardar: () => void }) {
  return (
    <DialogFooter>
      <Button variant="outline" onClick={onCancelar}>
        Cancelar
      </Button>
      <Button disabled={!valido || enviando} onClick={onGuardar}>
        {enviando && <Loader2 className="size-4 animate-spin" />}
        {texto}
      </Button>
    </DialogFooter>
  );
}

// --- Unidad: alta y edición ----------------------------------------------------------------

interface FormUnidad {
  tower: string;
  number: string;
  tipo: TipoUnidad;
  coefficient: string;
  area_m2: string;
  matricula_inmobiliaria: string;
  unidad_principal_id: string;
  ocupacion: Ocupacion;
  observaciones: string;
}

function inicialUnidad(u?: UnidadDetalle): FormUnidad {
  return {
    tower: u?.tower ?? "",
    number: u?.number ?? "",
    tipo: u?.tipo ?? "APARTAMENTO",
    coefficient: u?.coefficient ? String(Number(u.coefficient)) : "",
    area_m2: u?.area_m2 ? String(Number(u.area_m2)) : "",
    matricula_inmobiliaria: u?.matricula_inmobiliaria ?? "",
    unidad_principal_id: u?.unidad_principal?.id ?? "",
    ocupacion: u?.ocupacion ?? "SIN_INFORMACION",
    observaciones: u?.observaciones ?? "",
  };
}

const numero = (v: string) => (v.trim() === "" ? null : v.trim().replace(",", "."));

export function UnidadFormDialog({
  tenantId,
  abierto,
  onCambio,
  unidad,
  onGuardado,
}: PropsDialogo & { unidad?: UnidadDetalle; onGuardado: (u: UnidadDetalle) => void }) {
  const b = baseUnidades(tenantId);
  const [f, setF] = useState<FormUnidad>(() => inicialUnidad(unidad));
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const anexo = esAnexo(f.tipo);
  // Unidades principales para elegir de quién es anexo un parqueadero o depósito
  const { data: principales } = useSWR<UnidadesPagina>(abierto && anexo ? `${b}?solo_principales=true&page_size=200` : null, fetcher);

  useEffect(() => {
    if (!abierto) return;
    setF(inicialUnidad(unidad));
    setMotivo("");
  }, [abierto, unidad]);

  const set = <K extends keyof FormUnidad>(k: K, v: FormUnidad[K]) => setF((x) => ({ ...x, [k]: v }));
  const cambiaCoeficiente = !!unidad?.coefficient && numero(f.coefficient) !== String(Number(unidad.coefficient));
  const valido = f.number.trim().length > 0 && (!cambiaCoeficiente || motivo.trim().length >= 10);

  async function guardar() {
    setEnviando(true);
    try {
      const datos = {
        tower: f.tower.trim(),
        number: f.number.trim(),
        tipo: f.tipo,
        coefficient: numero(f.coefficient),
        area_m2: numero(f.area_m2),
        matricula_inmobiliaria: vacio(f.matricula_inmobiliaria),
        unidad_principal_id: anexo ? f.unidad_principal_id || null : null,
        observaciones: vacio(f.observaciones),
        ...(unidad ? { ocupacion: f.ocupacion } : {}),
      };
      let r: UnidadDetalle;
      if (unidad) {
        const antes = inicialUnidad(unidad);
        const cambios = Object.fromEntries(
          Object.entries(datos).filter(([k]) => {
            const clave = k as keyof FormUnidad;
            if (clave === "coefficient" || clave === "area_m2") return numero(f[clave]) !== numero(antes[clave]);
            if (clave === "unidad_principal_id") return (anexo ? f.unidad_principal_id : "") !== antes.unidad_principal_id;
            return String(f[clave] ?? "").trim() !== String(antes[clave] ?? "").trim();
          }),
        );
        if (!Object.keys(cambios).length) {
          toast.info("No hay cambios para guardar");
          return;
        }
        r = await api<UnidadDetalle>(`${b}/${unidad.id}`, { method: "PATCH", json: { ...cambios, motivo: vacio(motivo) } });
        toast.success("Unidad actualizada");
      } else {
        r = await api<UnidadDetalle>(b, { method: "POST", json: datos });
        toast.success(`Unidad ${r.etiqueta} registrada`);
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
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{unidad ? `Editar ${unidad.etiqueta}` : "Nueva unidad"}</DialogTitle>
          <DialogDescription>
            {unidad ? "Los cambios quedan en la auditoría." : "Apartamento, casa, local o un parqueadero o depósito privado (anexo)."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-3">
          <Campo label="Torre o bloque" ayuda="Vacío si no hay torres">
            <Input value={f.tower} onChange={(e) => set("tower", e.target.value)} placeholder="1" />
          </Campo>
          <Campo label="Número">
            <Input value={f.number} onChange={(e) => set("number", e.target.value)} placeholder="502" autoFocus={!unidad} />
          </Campo>
          <Campo label="Tipo">
            <select value={f.tipo} onChange={(e) => set("tipo", e.target.value as TipoUnidad)} className={campoClase()}>
              {(Object.keys(TIPO_UNIDAD) as TipoUnidad[]).map((t) => (
                <option key={t} value={t}>
                  {TIPO_UNIDAD[t]}
                </option>
              ))}
            </select>
          </Campo>
          {anexo && (
            <Campo label="Anexo de" ayuda="Unidad a la que pertenece (opcional)" className="sm:col-span-3">
              <select value={f.unidad_principal_id} onChange={(e) => set("unidad_principal_id", e.target.value)} className={campoClase()}>
                <option value="">Independiente (no es anexo)</option>
                {principales?.items.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.etiqueta} · {TIPO_UNIDAD[u.tipo]}
                  </option>
                ))}
              </select>
            </Campo>
          )}
          <Campo label="Coeficiente (%)" ayuda={anexo ? "Vacío si va incluido en el de la unidad principal" : "Según el reglamento, ej. 1,8506"}>
            <Input value={f.coefficient} onChange={(e) => set("coefficient", e.target.value)} inputMode="decimal" placeholder="1,8506" />
          </Campo>
          <Campo label="Área privada (m²)">
            <Input value={f.area_m2} onChange={(e) => set("area_m2", e.target.value)} inputMode="decimal" placeholder="62,3" />
          </Campo>
          <Campo label="Matrícula inmobiliaria">
            <Input value={f.matricula_inmobiliaria} onChange={(e) => set("matricula_inmobiliaria", e.target.value)} placeholder="50C-1234567" />
          </Campo>
          {unidad && !anexo && (
            <Campo label="Ocupación" ayuda={`Sugerida por las personas vinculadas: ${OCUPACION[unidad.ocupacion_sugerida].label}`} className="sm:col-span-3">
              <select value={f.ocupacion} onChange={(e) => set("ocupacion", e.target.value as Ocupacion)} className={campoClase()}>
                {(Object.keys(OCUPACION) as Ocupacion[]).map((o) => (
                  <option key={o} value={o}>
                    {OCUPACION[o].label}
                  </option>
                ))}
              </select>
            </Campo>
          )}
          <Campo label="Observaciones" className="sm:col-span-3">
            <textarea value={f.observaciones} onChange={(e) => set("observaciones", e.target.value)} className={textareaClase()} rows={2} />
          </Campo>
          {cambiaCoeficiente && (
            <Campo label="Motivo del cambio de coeficiente" ayuda="El coeficiente define votos y cuotas: explique el cambio (mínimo 10 caracteres)" className="sm:col-span-3">
              <Input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Reforma del reglamento aprobada en asamblea 2026" />
            </Campo>
          )}
        </div>
        <Pie onCancelar={() => onCambio(false)} enviando={enviando} valido={valido} texto={unidad ? "Guardar cambios" : "Registrar unidad"} onGuardar={guardar} />
      </DialogContent>
    </Dialog>
  );
}

// --- Persona: campos compartidos -------------------------------------------------------------

interface FormPersona {
  nombre_completo: string;
  tipo_documento: TipoDocumento | "";
  numero_documento: string;
  telefono: string;
  telefono_alterno: string;
  email: string;
  autoriza_datos: boolean;
  notas: string;
}

function inicialPersona(p?: Persona): FormPersona {
  return {
    nombre_completo: p?.nombre_completo ?? "",
    tipo_documento: p?.tipo_documento ?? (p ? "" : "CC"),
    numero_documento: p?.numero_documento ?? "",
    telefono: p?.telefono ?? "",
    telefono_alterno: p?.telefono_alterno ?? "",
    email: p?.email ?? "",
    autoriza_datos: !!p?.autoriza_datos_at,
    notas: p?.notas ?? "",
  };
}

function personaJson(f: FormPersona) {
  const doc = vacio(f.numero_documento);
  return {
    nombre_completo: f.nombre_completo.trim(),
    tipo_documento: doc ? f.tipo_documento || "CC" : null,
    numero_documento: doc,
    telefono: vacio(f.telefono),
    telefono_alterno: vacio(f.telefono_alterno),
    email: vacio(f.email),
    autoriza_datos: f.autoriza_datos,
    notas: vacio(f.notas),
  };
}

function CamposPersona({ f, set, completo = true }: { f: FormPersona; set: <K extends keyof FormPersona>(k: K, v: FormPersona[K]) => void; completo?: boolean }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Campo label="Nombre completo" className="sm:col-span-2">
        <Input value={f.nombre_completo} onChange={(e) => set("nombre_completo", e.target.value)} placeholder="Nombres y apellidos" />
      </Campo>
      <Campo label="Tipo de documento">
        <select value={f.tipo_documento} onChange={(e) => set("tipo_documento", e.target.value as TipoDocumento)} className={campoClase()}>
          {(Object.keys(TIPO_DOCUMENTO) as TipoDocumento[]).map((t) => (
            <option key={t} value={t}>
              {t} · {TIPO_DOCUMENTO[t]}
            </option>
          ))}
        </select>
      </Campo>
      <Campo label="Número de documento" ayuda="Opcional, con o sin puntos">
        <Input value={f.numero_documento} onChange={(e) => set("numero_documento", e.target.value)} inputMode="numeric" />
      </Campo>
      <Campo label="Celular">
        <Input value={f.telefono} onChange={(e) => set("telefono", e.target.value)} inputMode="tel" placeholder="300 123 4567" />
      </Campo>
      <Campo label="Correo">
        <Input value={f.email} onChange={(e) => set("email", e.target.value)} type="email" />
      </Campo>
      {completo && (
        <>
          <Campo label="Teléfono alterno">
            <Input value={f.telefono_alterno} onChange={(e) => set("telefono_alterno", e.target.value)} inputMode="tel" />
          </Campo>
          <Campo label="Notas internas" ayuda="Solo las ven administración y contabilidad">
            <Input value={f.notas} onChange={(e) => set("notas", e.target.value)} />
          </Campo>
        </>
      )}
      <label className="flex items-start gap-2 text-sm sm:col-span-2">
        <input type="checkbox" checked={f.autoriza_datos} onChange={(e) => set("autoriza_datos", e.target.checked)} className="mt-0.5 size-4" />
        <span>
          Autorizó el tratamiento de sus datos personales
          <span className="block text-xs text-muted-foreground">Ley 1581 de 2012. Se guarda la fecha de la autorización.</span>
        </span>
      </label>
    </div>
  );
}

export function PersonaFormDialog({
  tenantId,
  abierto,
  onCambio,
  persona,
  onGuardado,
}: PropsDialogo & { persona: Persona; onGuardado: (p: PersonaDetalle) => void }) {
  const [f, setF] = useState<FormPersona>(() => inicialPersona(persona));
  const [enviando, setEnviando] = useState(false);
  useEffect(() => {
    if (abierto) setF(inicialPersona(persona));
  }, [abierto, persona]);
  const set = <K extends keyof FormPersona>(k: K, v: FormPersona[K]) => setF((x) => ({ ...x, [k]: v }));

  async function guardar() {
    setEnviando(true);
    try {
      const nuevo = personaJson(f);
      const antes = personaJson(inicialPersona(persona));
      const cambios = Object.fromEntries(Object.entries(nuevo).filter(([k, v]) => v !== antes[k as keyof typeof antes]));
      if (!Object.keys(cambios).length) {
        toast.info("No hay cambios para guardar");
        return;
      }
      const r = await api<PersonaDetalle>(`${baseTenant(tenantId)}/personas/${persona.id}`, { method: "PATCH", json: cambios });
      toast.success("Datos actualizados");
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
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Editar datos de {persona.nombre_completo}</DialogTitle>
          <DialogDescription>Los cambios aplican en todas las unidades donde figura.</DialogDescription>
        </DialogHeader>
        <CamposPersona f={f} set={set} />
        <Pie onCancelar={() => onCambio(false)} enviando={enviando} valido={f.nombre_completo.trim().length >= 2} texto="Guardar" onGuardar={guardar} />
      </DialogContent>
    </Dialog>
  );
}

// --- Vincular persona a una unidad -----------------------------------------------------------

export function VincularDialog({
  tenantId,
  abierto,
  onCambio,
  unidad,
  onGuardado,
}: PropsDialogo & { unidad: UnidadDetalle; onGuardado: (u: UnidadDetalle) => void }) {
  const [modo, setModo] = useState<"buscar" | "nueva">("buscar");
  const [busqueda, setBusqueda] = useState("");
  const [elegida, setElegida] = useState<Persona | null>(null);
  const [f, setF] = useState<FormPersona>(() => inicialPersona());
  const [relacion, setRelacion] = useState<Relacion>("PROPIETARIO");
  const [reside, setReside] = useState(true);
  const [porcentaje, setPorcentaje] = useState("");
  const [fechaInicio, setFechaInicio] = useState("");
  const [enviando, setEnviando] = useState(false);
  const termino = busqueda.trim();
  const { data: resultados, isLoading } = useSWR<PersonasPagina>(
    abierto && modo === "buscar" && termino.length >= 3 ? `${baseTenant(tenantId)}/personas?texto=${encodeURIComponent(termino)}&page_size=8` : null,
    fetcher,
    { keepPreviousData: true },
  );

  useEffect(() => {
    if (!abierto) return;
    setModo("buscar");
    setBusqueda("");
    setElegida(null);
    setF(inicialPersona());
    const tieneProp = unidad.vinculos.some((v) => v.relacion === "PROPIETARIO");
    setRelacion(tieneProp ? "RESIDENTE" : "PROPIETARIO");
    setReside(!esAnexo(unidad.tipo));
    setPorcentaje("");
    setFechaInicio("");
  }, [abierto, unidad]);

  const set = <K extends keyof FormPersona>(k: K, v: FormPersona[K]) => setF((x) => ({ ...x, [k]: v }));
  const valido = modo === "buscar" ? !!elegida : f.nombre_completo.trim().length >= 2;

  async function guardar() {
    setEnviando(true);
    try {
      const r = await api<UnidadDetalle>(`${baseUnidades(tenantId)}/${unidad.id}/vinculos`, {
        method: "POST",
        json: {
          ...(modo === "buscar" ? { persona_id: elegida?.id } : { persona: personaJson(f) }),
          relacion,
          reside,
          porcentaje_propiedad: relacion === "PROPIETARIO" ? numero(porcentaje) : null,
          fecha_inicio: fechaInicio || null,
        },
      });
      // El nombre que guardó el servidor (normalizado: «ANA GÓMEZ» -> «Ana Gómez»)
      const nuevo = r.vinculos.find((v) => v.relacion === relacion && !unidad.vinculos.some((x) => x.id === v.id));
      toast.success(`${nuevo?.persona.nombre_completo ?? "La persona"} quedó vinculada como ${RELACION[relacion].label.toLowerCase()}`);
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
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Agregar persona a {unidad.etiqueta}</DialogTitle>
          <DialogDescription>Busque si ya está en el directorio (por ejemplo, un propietario de varias unidades) o regístrela.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo label="Relación con la unidad" ayuda={RELACION[relacion].ayuda}>
              <select value={relacion} onChange={(e) => setRelacion(e.target.value as Relacion)} className={campoClase()}>
                {(Object.keys(RELACION) as Relacion[]).map((r) => (
                  <option key={r} value={r}>
                    {RELACION[r].label}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo label="Desde" ayuda="Vacío = hoy">
              <input type="date" value={fechaInicio} max={hoyBogota()} onChange={(e) => setFechaInicio(e.target.value)} className={campoClase()} />
            </Campo>
            {relacion === "PROPIETARIO" && (
              <Campo label="% de propiedad" ayuda="Solo si hay varios copropietarios">
                <Input value={porcentaje} onChange={(e) => setPorcentaje(e.target.value)} inputMode="decimal" placeholder="50" />
              </Campo>
            )}
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
              <input type="checkbox" checked={reside} onChange={(e) => setReside(e.target.checked)} className="size-4" />
              Vive en la unidad
            </label>
          </div>

          <div className="flex gap-1 rounded-lg bg-muted p-1 text-sm">
            {(["buscar", "nueva"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setModo(m)}
                className={cn("flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-1.5 font-medium transition-colors", modo === m ? "bg-card shadow-sm" : "text-muted-foreground")}
              >
                {m === "buscar" ? <Search className="size-4" /> : <UserPlus className="size-4" />}
                {m === "buscar" ? "Ya está en el directorio" : "Persona nueva"}
              </button>
            ))}
          </div>

          {modo === "buscar" ? (
            <div className="space-y-2">
              <Input value={busqueda} onChange={(e) => { setBusqueda(e.target.value); setElegida(null); }} placeholder="Nombre, documento o teléfono (mínimo 3 letras)" autoFocus />
              {termino.length >= 3 && (
                <ul className="max-h-56 divide-y overflow-y-auto rounded-md border">
                  {isLoading && !resultados && <li className="px-3 py-2 text-sm text-muted-foreground">Buscando…</li>}
                  {resultados?.items.length === 0 && (
                    <li className="px-3 py-3 text-sm text-muted-foreground">
                      No está en el directorio.{" "}
                      <button type="button" className="font-medium text-primary hover:underline" onClick={() => { setModo("nueva"); set("nombre_completo", termino); }}>
                        Registrarla como persona nueva
                      </button>
                    </li>
                  )}
                  {resultados?.items.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => setElegida(p)}
                        className={cn("flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-accent", elegida?.id === p.id && "bg-accent")}
                      >
                        <UserRound className="size-4 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1">
                          <span className="block font-medium">{p.nombre_completo}</span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {p.unidades.length ? p.unidades.map((u) => u.etiqueta).join(", ") : "Sin unidad vigente"}
                            {p.numero_documento && ` · ${p.tipo_documento} ${p.numero_documento}`}
                          </span>
                        </span>
                        {elegida?.id === p.id && <span className="text-xs font-medium text-primary">Elegida</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <CamposPersona f={f} set={set} completo={false} />
          )}
        </div>

        <Pie onCancelar={() => onCambio(false)} enviando={enviando} valido={valido} texto="Vincular" onGuardar={guardar} />
      </DialogContent>
    </Dialog>
  );
}

// --- Cerrar vínculo (venta, fin del arriendo, mudanza) -----------------------------------------

const MOTIVOS_CIERRE: Record<Relacion, string[]> = {
  PROPIETARIO: ["Venta del inmueble", "Sucesión", "Error de registro"],
  ARRENDATARIO: ["Terminación del contrato de arriendo", "Mudanza", "Error de registro"],
  RESIDENTE: ["Mudanza", "Fallecimiento", "Error de registro"],
  AUTORIZADO: ["Retiro de la autorización", "Error de registro"],
};

export function CerrarVinculoDialog({
  tenantId,
  vinculo,
  onCerrar,
  onGuardado,
}: {
  tenantId: string;
  vinculo: Vinculo | null;
  onCerrar: () => void;
  onGuardado: (u: UnidadDetalle) => void;
}) {
  const [motivo, setMotivo] = useState("");
  const [fecha, setFecha] = useState("");
  const [enviando, setEnviando] = useState(false);
  useEffect(() => {
    setMotivo("");
    setFecha("");
  }, [vinculo]);

  async function guardar() {
    if (!vinculo) return;
    setEnviando(true);
    try {
      const r = await api<UnidadDetalle>(`${baseTenant(tenantId)}/vinculos/${vinculo.id}/cerrar`, {
        method: "POST",
        json: { motivo: motivo.trim(), fecha_fin: fecha || null },
      });
      toast.success(`${vinculo.persona.nombre_completo} pasó al historial de ${vinculo.unidad.etiqueta}`);
      onGuardado(r);
      onCerrar();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={!!vinculo} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="sm:max-w-md">
        {vinculo && (
          <>
            <DialogHeader>
              <DialogTitle>Retirar a {vinculo.persona.nombre_completo}</DialogTitle>
              <DialogDescription>
                Deja de figurar como {RELACION[vinculo.relacion].label.toLowerCase()} de {vinculo.unidad.etiqueta}. No se borra: queda en el historial con la fecha y el motivo.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {MOTIVOS_CIERRE[vinculo.relacion].map((m) => (
                  <button key={m} type="button" onClick={() => setMotivo(m)} className={cn("rounded-full border px-2.5 py-1 text-xs transition-colors hover:bg-accent", motivo === m && "border-primary bg-accent font-medium")}>
                    {m}
                  </button>
                ))}
              </div>
              <Campo label="Motivo">
                <Input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ej.: venta del inmueble, escritura 1234 de 2026" />
              </Campo>
              <Campo label="Fecha" ayuda="Vacío = hoy">
                <input type="date" value={fecha} min={vinculo.fecha_inicio} max={hoyBogota()} onChange={(e) => setFecha(e.target.value)} className={campoClase()} />
              </Campo>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={onCerrar}>
                Cancelar
              </Button>
              <Button variant="destructive" disabled={motivo.trim().length < 3 || enviando} onClick={guardar}>
                {enviando && <Loader2 className="size-4 animate-spin" />}
                Retirar
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// --- Vehículo ------------------------------------------------------------------------------

export function VehiculoDialog({
  tenantId,
  abierto,
  onCambio,
  unidad,
  vehiculo,
  onGuardado,
}: PropsDialogo & { unidad: UnidadDetalle; vehiculo?: Vehiculo; onGuardado: (u: UnidadDetalle) => void }) {
  const [placa, setPlaca] = useState("");
  const [tipo, setTipo] = useState<TipoVehiculo>("CARRO");
  const [marca, setMarca] = useState("");
  const [color, setColor] = useState("");
  const [personaId, setPersonaId] = useState("");
  const [enviando, setEnviando] = useState(false);
  useEffect(() => {
    if (!abierto) return;
    setPlaca(vehiculo?.placa ?? "");
    setTipo(vehiculo?.tipo ?? "CARRO");
    setMarca(vehiculo?.marca ?? "");
    setColor(vehiculo?.color ?? "");
    setPersonaId(vehiculo?.persona?.id ?? "");
  }, [abierto, vehiculo]);
  const placaNormal = placa.replace(/[\s.-]/g, "").toUpperCase();
  const valido = /^[A-Z0-9]{3,7}$/.test(placaNormal);

  async function guardar() {
    setEnviando(true);
    try {
      const datos = { placa: placaNormal, tipo, marca: vacio(marca), color: vacio(color), persona_id: personaId || null };
      const r = vehiculo
        ? await api<UnidadDetalle>(`${baseTenant(tenantId)}/vehiculos/${vehiculo.id}`, { method: "PATCH", json: datos })
        : await api<UnidadDetalle>(`${baseUnidades(tenantId)}/${unidad.id}/vehiculos`, { method: "POST", json: datos });
      toast.success(vehiculo ? "Vehículo actualizado" : `Vehículo ${placaNormal} registrado`);
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
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{vehiculo ? `Editar vehículo ${vehiculo.placa}` : `Registrar vehículo en ${unidad.etiqueta}`}</DialogTitle>
          <DialogDescription>Recepción lo reconocerá como vehículo de residente al registrar el parqueadero.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo label="Placa">
            <Input value={placa} onChange={(e) => setPlaca(e.target.value.toUpperCase())} className="font-mono tracking-wider uppercase" placeholder="ABC123" maxLength={9} autoFocus />
          </Campo>
          <Campo label="Tipo">
            <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoVehiculo)} className={campoClase()}>
              {(Object.keys(TIPO_VEHICULO) as TipoVehiculo[]).map((t) => (
                <option key={t} value={t}>
                  {TIPO_VEHICULO[t]}
                </option>
              ))}
            </select>
          </Campo>
          <Campo label="Marca y línea">
            <Input value={marca} onChange={(e) => setMarca(e.target.value)} placeholder="Mazda 3" />
          </Campo>
          <Campo label="Color">
            <Input value={color} onChange={(e) => setColor(e.target.value)} />
          </Campo>
          <Campo label="Dueño" className="sm:col-span-2">
            <select value={personaId} onChange={(e) => setPersonaId(e.target.value)} className={campoClase()}>
              <option value="">Sin especificar</option>
              {unidad.vinculos.filter((v, i, todos) => todos.findIndex((x) => x.persona.id === v.persona.id) === i).map((v) => (
                <option key={v.persona.id} value={v.persona.id}>
                  {v.persona.nombre_completo} · {RELACION[v.relacion].label}
                </option>
              ))}
            </select>
          </Campo>
        </div>
        <Pie onCancelar={() => onCambio(false)} enviando={enviando} valido={valido} texto={vehiculo ? "Guardar" : "Registrar"} onGuardar={guardar} />
      </DialogContent>
    </Dialog>
  );
}
