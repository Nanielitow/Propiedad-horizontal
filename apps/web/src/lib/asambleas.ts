// Asambleas de copropietarios: tipos de la API, etiquetas y permisos por rol.

import type { Tono } from "./recaudos";
import type { Role } from "./types";

export type TipoAsamblea = "ORDINARIA" | "EXTRAORDINARIA";
export type Modalidad = "PRESENCIAL" | "VIRTUAL" | "MIXTA";
export type Convocatoria = "PRIMERA" | "SEGUNDA";
export type EstadoAsamblea = "PROGRAMADA" | "EN_CURSO" | "CERRADA" | "CANCELADA";
export type TipoPunto = "INFORMATIVO" | "VOTACION";
export type Mayoria = "SIMPLE" | "CALIFICADA_70" | "ELECCION";
export type EstadoPunto = "PENDIENTE" | "EN_VOTACION" | "CERRADO";

export interface Quorum {
  presente: string;
  total: string;
  porcentaje: string;
  unidades_presentes: number;
  unidades_total: number;
  hay_quorum: boolean;
  falta: string;
  mensaje: string;
}

export interface Resultado {
  por_opcion: Record<string, string>;
  unidades_por_opcion: Record<string, number>;
  votantes: string;
  presente: string;
  total: string;
  aprobado: boolean | null;
  ganador: string | null;
  umbral: string;
  explicacion: string;
}

export interface Punto {
  id: string;
  orden: number;
  titulo: string;
  descripcion: string | null;
  tipo: TipoPunto;
  mayoria: Mayoria | null;
  opciones: string[];
  estado: EstadoPunto;
  abierto_at: string | null;
  cerrado_at: string | null;
  resultado: Resultado | null;
  aprobado: boolean | null;
  conclusion: string | null;
  votos: number;
  mis_votos: Record<string, string>;
}

export interface Padron {
  unidad_id: string;
  etiqueta: string;
  coeficiente: string;
  propietarios: string | null;
  al_dia: boolean | null;
  presente: boolean;
  asistencia_id: string | null;
  asistente: string | null;
  tipo: "PROPIETARIO" | "APODERADO" | null;
  virtual: boolean;
  llegada_at: string | null;
  con_cuenta: boolean;
}

export interface AsambleaResumen {
  id: string;
  consecutivo: number;
  titulo: string;
  tipo: TipoAsamblea;
  modalidad: Modalidad;
  convocatoria: Convocatoria;
  fecha_hora: string;
  lugar: string | null;
  estado: EstadoAsamblea;
  convocada: boolean;
  puntos: number;
  quorum_pct: string | null;
  acta_document_id: string | null;
}

export interface AsambleaDetalle extends AsambleaResumen {
  max_poderes_por_apoderado: number;
  presidente: string | null;
  secretario: string | null;
  observaciones: string | null;
  abierta_at: string | null;
  cerrada_at: string | null;
  circular_id: string | null;
  quorum: Quorum | null;
  puntos_lista: Punto[];
  padron: Padron[];
  soy_votante: boolean;
  puede_asistir_portal: boolean;
  votaron: string[];
}

export const ESTADO_ASAMBLEA: Record<EstadoAsamblea, { label: string; tono: Tono }> = {
  PROGRAMADA: { label: "Programada", tono: "info" },
  EN_CURSO: { label: "En curso", tono: "success" },
  CERRADA: { label: "Cerrada", tono: "neutral" },
  CANCELADA: { label: "Cancelada", tono: "danger" },
};

export const MODALIDAD: Record<Modalidad, string> = { PRESENCIAL: "Presencial", VIRTUAL: "Virtual", MIXTA: "Mixta (presencial y virtual)" };

export const MAYORIA: Record<Mayoria, { label: string; ayuda: string }> = {
  SIMPLE: { label: "Mayoría simple", ayuda: "Más de la mitad de los coeficientes presentes (art. 45)" },
  CALIFICADA_70: { label: "Mayoría calificada (70 %)", ayuda: "70 % de los coeficientes de todo el conjunto: reformas del reglamento, cuotas extraordinarias altas, cambios de destinación (art. 46)" },
  ELECCION: { label: "Elección", ayuda: "Gana la opción con más coeficiente (consejo, revisor fiscal)" },
};

const PERMISOS = {
  ver: ["ADMIN", "AUXILIAR", "CONSEJO", "CONTABILIDAD", "RESIDENTE"],
  gestionar: ["ADMIN"],
  registrar: ["ADMIN", "AUXILIAR"],
} satisfies Record<string, Role[]>;

export function puedeAsambleas(rol: Role, accion: keyof typeof PERMISOS): boolean {
  return (PERMISOS[accion] as Role[]).includes(rol);
}

export const baseAsambleas = (tenantId: string) => `/tenants/${tenantId}/asambleas`;

export function pct(v: string | number): string {
  return `${Number(v).toLocaleString("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} %`;
}

export function fechaHoraLarga(iso: string): string {
  return new Date(iso).toLocaleString("es-CO", { dateStyle: "full", timeStyle: "short", timeZone: "America/Bogota" });
}
