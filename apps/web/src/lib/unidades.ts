// Módulo de unidades, copropietarios y residentes: tipos de la API, etiquetas y permisos.
// Los permisos aquí solo deciden qué se MUESTRA; quien decide es la API (y la RLS).
// Los datos que un rol no puede ver llegan en null.

import type { Tono } from "./recaudos";
import type { Role } from "./types";

export type TipoUnidad = "APARTAMENTO" | "CASA" | "LOCAL" | "OFICINA" | "PARQUEADERO" | "DEPOSITO" | "OTRO";
export type Ocupacion = "PROPIETARIO" | "ARRENDADA" | "DESOCUPADA" | "SIN_INFORMACION";
export type Relacion = "PROPIETARIO" | "ARRENDATARIO" | "RESIDENTE" | "AUTORIZADO";
export type TipoDocumento = "CC" | "CE" | "NIT" | "PASAPORTE" | "PPT" | "TI";
export type TipoVehiculo = "CARRO" | "MOTO" | "BICICLETA" | "OTRO";

export interface UnidadRef {
  id: string;
  etiqueta: string;
  tipo: TipoUnidad;
}

export interface PersonaRef {
  id: string;
  nombre: string;
  telefono: string | null;
}

export interface Persona {
  id: string;
  nombre_completo: string;
  telefono: string | null;
  telefono_alterno: string | null;
  tipo_documento: TipoDocumento | null;
  numero_documento: string | null;
  email: string | null;
  notas: string | null;
  tiene_cuenta: boolean;
  autoriza_datos_at: string | null;
  activa: boolean;
}

export interface Vinculo {
  id: string;
  unidad: UnidadRef;
  persona: Persona;
  relacion: Relacion;
  porcentaje_propiedad: string | null;
  es_contacto_principal: boolean;
  responsable_pago: boolean;
  reside: boolean;
  fecha_inicio: string;
  fecha_fin: string | null;
  motivo_cierre: string | null;
}

export interface Vehiculo {
  id: string;
  unidad: UnidadRef;
  persona: PersonaRef | null;
  placa: string;
  tipo: TipoVehiculo;
  marca: string | null;
  color: string | null;
  activo: boolean;
}

export interface UnidadResumen {
  id: string;
  etiqueta: string;
  tower: string;
  number: string;
  tipo: TipoUnidad;
  ocupacion: Ocupacion;
  activa: boolean;
  coefficient: string | null;
  area_m2: string | null;
  unidad_principal: UnidadRef | null;
  anexos: UnidadRef[];
  propietarios: PersonaRef[];
  contacto: PersonaRef | null;
  responsable_pago: PersonaRef | null;
  residentes: number;
  vehiculos: number | null;
}

export interface UnidadesPagina {
  items: UnidadResumen[];
  total: number;
  page: number;
  page_size: number;
}

export interface ResumenUnidades {
  total: number;
  por_tipo: Partial<Record<TipoUnidad, number>>;
  por_ocupacion: Partial<Record<Ocupacion, number>>;
  sin_propietario: number;
  sin_responsable_pago: number;
  personas: number | null;
  vehiculos: number | null;
  torres: string[];
  coeficientes: {
    suma: string;
    diferencia: string;
    cuadra: boolean;
    unidades_con_coeficiente: number;
    unidades_sin_coeficiente: number;
    mensaje: string;
  } | null;
}

export interface AuditoriaUnidad {
  fecha_hora: string;
  entidad: "unidad" | "persona" | "vinculo" | "vehiculo";
  accion: "CREACION" | "EDICION" | "CAMBIO_ESTADO" | "ANULACION";
  usuario: string | null;
  motivo: string | null;
  cambios: Record<string, unknown> | null;
}

export interface UnidadDetalle extends UnidadResumen {
  matricula_inmobiliaria: string | null;
  observaciones: string | null;
  ocupacion_sugerida: Ocupacion;
  vinculos: Vinculo[];
  historial: Vinculo[];
  vehiculos_lista: Vehiculo[];
  recaudos: { id: string; consecutivo: number; fecha_recaudo: string; concepto: string; valor: string; estado: string }[];
  auditoria: AuditoriaUnidad[];
  created_at: string;
  updated_at: string;
}

export interface PersonaResumen extends Persona {
  unidades: UnidadRef[];
  relaciones: Relacion[];
}

export interface PersonasPagina {
  items: PersonaResumen[];
  total: number;
  page: number;
  page_size: number;
}

export interface PersonaDetalle extends Persona {
  vinculos: Vinculo[];
  vehiculos: Vehiculo[];
}

export interface PlacaConsulta {
  placa: string;
  registrada: boolean;
  vehiculo: Vehiculo | null;
}

export interface VistaPrevia {
  archivo: string;
  sha256: string;
  filas_leidas: number;
  puede_aplicar: boolean;
  hay_cambios: boolean;
  totales: {
    unidades_nuevas: number;
    unidades_con_cambios: number;
    personas_nuevas: number;
    personas_con_cambios: number;
    vinculos_nuevos: number;
    vehiculos_nuevos: number;
    sin_cambios: number;
  };
  unidades_nuevas: ({ fila: number; etiqueta: string } & Record<string, unknown>)[];
  unidades_con_cambios: { fila: number; etiqueta: string; cambios: Record<string, { antes: unknown; despues: unknown }> }[];
  vinculos_nuevos: { fila: number; unidad: string; nombre: string; relacion: Relacion; persona_nueva: boolean }[];
  vehiculos_nuevos: { fila: number; unidad: string; placa: string; tipo: TipoVehiculo }[];
  errores: { hoja: string; fila: number; mensaje: string }[];
  total_errores: number;
  advertencias: string[];
  coeficientes: { suma: string; cuadra: boolean; mensaje: string } | null;
}

export interface ResultadoImportacion {
  id: string;
  archivo: string;
  unidades_creadas: number;
  unidades_actualizadas: number;
  personas_creadas: number;
  personas_actualizadas: number;
  vinculos_creados: number;
  vehiculos_creados: number;
  advertencias: string[];
}

// --- Etiquetas -------------------------------------------------------------------------------

export const TIPO_UNIDAD: Record<TipoUnidad, string> = {
  APARTAMENTO: "Apartamento",
  CASA: "Casa",
  LOCAL: "Local",
  OFICINA: "Oficina",
  PARQUEADERO: "Parqueadero",
  DEPOSITO: "Depósito",
  OTRO: "Otro",
};

export const OCUPACION: Record<Ocupacion, { label: string; tono: Tono; ayuda: string }> = {
  PROPIETARIO: { label: "Habitada por propietario", tono: "success", ayuda: "La habita su propietario o su familia" },
  ARRENDADA: { label: "Arrendada", tono: "info", ayuda: "Hay un arrendatario vigente" },
  DESOCUPADA: { label: "Desocupada", tono: "neutral", ayuda: "Tiene propietario, pero nadie reside" },
  SIN_INFORMACION: { label: "Sin información", tono: "warning", ayuda: "No hay propietario registrado" },
};

export const RELACION: Record<Relacion, { label: string; ayuda: string }> = {
  PROPIETARIO: { label: "Propietario", ayuda: "Dueño de la unidad (figura en la escritura)" },
  ARRENDATARIO: { label: "Arrendatario", ayuda: "Vive en la unidad con contrato de arriendo" },
  RESIDENTE: { label: "Residente", ayuda: "Familiar u ocupante que vive en la unidad" },
  AUTORIZADO: { label: "Autorizado", ayuda: "Puede recoger paquetes, pagar o autorizar visitas" },
};

export const TIPO_DOCUMENTO: Record<TipoDocumento, string> = {
  CC: "Cédula de ciudadanía",
  CE: "Cédula de extranjería",
  NIT: "NIT",
  PASAPORTE: "Pasaporte",
  PPT: "Permiso por protección temporal",
  TI: "Tarjeta de identidad",
};

export const TIPO_VEHICULO: Record<TipoVehiculo, string> = {
  CARRO: "Carro",
  MOTO: "Moto",
  BICICLETA: "Bicicleta",
  OTRO: "Otro",
};

export const ENTIDAD_AUDITORIA: Record<AuditoriaUnidad["entidad"], string> = {
  unidad: "Unidad",
  persona: "Persona",
  vinculo: "Vínculo",
  vehiculo: "Vehículo",
};

export const ACCION_AUDITORIA: Record<AuditoriaUnidad["accion"], string> = {
  CREACION: "Creación",
  EDICION: "Edición",
  CAMBIO_ESTADO: "Cambio de estado",
  ANULACION: "Desactivación",
};

// --- Permisos (docs/UNIDADES.md §3) ----------------------------------------------------------

const PERMISOS = {
  verUnidades: ["ADMIN", "AUXILIAR", "CONTABILIDAD", "CONSEJO", "MANTENIMIENTO"],
  directorio: ["ADMIN", "AUXILIAR", "CONTABILIDAD"],
  gestionar: ["ADMIN"],
  importar: ["ADMIN"],
  exportar: ["ADMIN", "CONTABILIDAD", "CONSEJO"],
  vehiculos: ["ADMIN", "AUXILIAR"],
  miUnidad: ["RESIDENTE"],
} satisfies Record<string, Role[]>;

export type AccionUnidades = keyof typeof PERMISOS;

export function puedeUnidades(rol: Role, accion: AccionUnidades): boolean {
  return (PERMISOS[accion] as Role[]).includes(rol);
}

export const baseUnidades = (tenantId: string) => `/tenants/${tenantId}/unidades`;
export const baseTenant = (tenantId: string) => `/tenants/${tenantId}`;

/** "0.8532" -> "0,8532 %". */
export function coeficienteTexto(c: string | null): string {
  if (c === null) return "—";
  return `${Number(c).toLocaleString("es-CO", { minimumFractionDigits: 4, maximumFractionDigits: 4 })} %`;
}

export function telefonoTexto(t: string | null): string {
  if (!t) return "";
  const d = t.replace(/^\+57/, "");
  return d.length === 10 ? `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}` : t;
}

export const esAnexo = (t: TipoUnidad) => t === "PARQUEADERO" || t === "DEPOSITO";
