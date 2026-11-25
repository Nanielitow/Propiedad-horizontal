// Portal del residente: tipos de la API, etiquetas y permisos por rol.
// Los permisos aquí solo deciden qué se MUESTRA; quien decide es la API (y la RLS).

import type { Tono } from "./recaudos";
import type { Role } from "./types";

export type TipoPqrs = "PETICION" | "QUEJA" | "RECLAMO" | "SUGERENCIA" | "FELICITACION";
export type CategoriaPqrs = "ADMINISTRACION" | "CONVIVENCIA" | "MANTENIMIENTO" | "SEGURIDAD" | "ASEO" | "PARQUEADEROS" | "ZONAS_COMUNES" | "CARTERA" | "OTRO";
export type EstadoPqrs = "RADICADA" | "EN_TRAMITE" | "RESPONDIDA" | "CERRADA" | "DESISTIDA";
export type CanalPqrs = "PORTAL" | "PRESENCIAL" | "CORREO" | "TELEFONO";
export type PrioridadPqrs = "BAJA" | "MEDIA" | "ALTA";
export type CategoriaCircular = "INFORMATIVA" | "CONVOCATORIA" | "SERVICIOS" | "MANTENIMIENTO" | "SEGURIDAD" | "CARTERA" | "CONVIVENCIA";
export type EstadoReserva = "SOLICITADA" | "CONFIRMADA" | "CANCELADA" | "REALIZADA" | "RECHAZADA";

export interface Adjunto {
  nombre: string;
  tipo: string;
  tamano: number | null;
  url: string;
}

export interface PqrsResumen {
  id: string;
  radicado: string;
  tipo: TipoPqrs;
  categoria: CategoriaPqrs;
  asunto: string;
  estado: EstadoPqrs;
  prioridad: PrioridadPqrs;
  canal: CanalPqrs;
  unidad: string | null;
  solicitante_nombre: string;
  asignado_a: string | null;
  fecha_limite: string;
  dias_habiles_restantes: number | null;
  vencida: boolean;
  calificacion: number | null;
  mensajes: number;
  created_at: string;
  updated_at: string;
}

export interface Mensaje {
  id: string;
  autor: string;
  autor_rol: string;
  es_mio: boolean;
  texto: string;
  interno: boolean;
  es_respuesta: boolean;
  adjuntos: Adjunto[];
  created_at: string;
}

export interface PqrsDetalle extends PqrsResumen {
  descripcion: string;
  solicitante_contacto: string | null;
  adjuntos: Adjunto[];
  comentario_calificacion: string | null;
  respondida_at: string | null;
  cerrada_at: string | null;
  novedad_id: string | null;
  novedad_codigo: string | null;
  hilo: Mensaje[];
  es_mia: boolean;
  puede_gestionar: boolean;
}

export interface ResumenBandeja {
  por_estado: Partial<Record<EstadoPqrs, number>>;
  abiertas: number;
  vencidas: number;
  por_vencer: number;
  sin_asignar: number;
  tiempo_respuesta_promedio_dias: string | null;
  satisfaccion_promedio: string | null;
}

export interface Circular {
  id: string;
  numero: string | null;
  titulo: string;
  cuerpo: string;
  categoria: CategoriaCircular;
  importante: boolean;
  torres: string[];
  estado: "BORRADOR" | "PUBLICADA" | "ARCHIVADA";
  document_id: string | null;
  documento_titulo: string | null;
  enviar_correo: boolean;
  publicada_at: string | null;
  vigente_hasta: string | null;
  leida: boolean;
  lecturas: number | null;
  destinatarios_con_cuenta: number | null;
  correos_enviados: number;
  created_at: string;
}

export interface Zona {
  id: string;
  nombre: string;
  descripcion: string | null;
  capacidad: number | null;
  reglas: string | null;
  tarifa_alquiler: string | null;
  tarifa_aseo: string | null;
  hora_apertura: string;
  hora_cierre: string;
  anticipacion_min_dias: number;
  anticipacion_max_dias: number;
  max_reservas_mes_unidad: number;
  requiere_paz_y_salvo: boolean;
  requiere_aprobacion: boolean;
  reservable_residentes: boolean;
  activo: boolean;
}

export interface Ocupado {
  fecha_evento: string;
  hora_inicio: string | null;
  hora_fin: string | null;
  propia: boolean;
}

export interface ReservaPortal {
  id: string;
  zona_id: string;
  zona: string;
  unidad_id: string | null;
  unidad: string | null;
  solicitante: string;
  fecha_evento: string;
  hora_inicio: string | null;
  hora_fin: string | null;
  numero_asistentes: number | null;
  estado: EstadoReserva;
  observaciones: string | null;
  solicitada_en_portal: boolean;
  motivo_decision: string | null;
  decidida_at: string | null;
  tarifa_total: string | null;
  created_at: string;
}

export interface InicioResidente {
  nombre: string;
  unidades: string[];
  saldo_total: string | null;
  saldo_vencido: string | null;
  al_dia: boolean | null;
  proximas_reservas: ReservaPortal[];
  pqrs_abiertas: PqrsResumen[];
  pqrs_por_calificar: number;
  circulares_sin_leer: Circular[];
  zonas_reservables: number;
}

export interface PendientesPersonal {
  pqrs_abiertas: number;
  pqrs_vencidas: number;
  pqrs_sin_asignar: number;
  reservas_por_decidir: number;
  circulares_borrador: number;
}

// --- Etiquetas -------------------------------------------------------------------------------

export const TIPO_PQRS: Record<TipoPqrs, { label: string; ayuda: string }> = {
  PETICION: { label: "Petición", ayuda: "Solicitar información, un documento o un servicio" },
  QUEJA: { label: "Queja", ayuda: "Inconformidad con la conducta de alguien (vecinos, personal)" },
  RECLAMO: { label: "Reclamo", ayuda: "Algo no funciona o un cobro o servicio no fue el esperado" },
  SUGERENCIA: { label: "Sugerencia", ayuda: "Una idea para mejorar la copropiedad" },
  FELICITACION: { label: "Felicitación", ayuda: "Reconocer un buen servicio" },
};

export const CATEGORIA_PQRS: Record<CategoriaPqrs, string> = {
  ADMINISTRACION: "Administración",
  CONVIVENCIA: "Convivencia",
  MANTENIMIENTO: "Mantenimiento",
  SEGURIDAD: "Seguridad y portería",
  ASEO: "Aseo",
  PARQUEADEROS: "Parqueaderos",
  ZONAS_COMUNES: "Zonas comunes",
  CARTERA: "Cuotas y pagos",
  OTRO: "Otro",
};

export const ESTADO_PQRS: Record<EstadoPqrs, { label: string; tono: Tono; ayuda: string }> = {
  RADICADA: { label: "Radicada", tono: "info", ayuda: "Recibida, pendiente de atención" },
  EN_TRAMITE: { label: "En trámite", tono: "warning", ayuda: "La administración la está atendiendo" },
  RESPONDIDA: { label: "Respondida", tono: "success", ayuda: "Tiene respuesta; falta que el residente la califique" },
  CERRADA: { label: "Cerrada", tono: "neutral", ayuda: "Resuelta" },
  DESISTIDA: { label: "Desistida", tono: "neutral", ayuda: "El solicitante ya no la necesita" },
};

export const CANAL_PQRS: Record<CanalPqrs, string> = {
  PORTAL: "Portal",
  PRESENCIAL: "Presencial",
  CORREO: "Correo",
  TELEFONO: "Teléfono",
};

export const PRIORIDAD_PQRS: Record<PrioridadPqrs, { label: string; tono: Tono }> = {
  BAJA: { label: "Baja", tono: "neutral" },
  MEDIA: { label: "Media", tono: "info" },
  ALTA: { label: "Alta", tono: "danger" },
};

export const CATEGORIA_CIRCULAR: Record<CategoriaCircular, string> = {
  INFORMATIVA: "Informativa",
  CONVOCATORIA: "Convocatoria",
  SERVICIOS: "Servicios públicos",
  MANTENIMIENTO: "Mantenimiento",
  SEGURIDAD: "Seguridad",
  CARTERA: "Cuotas y pagos",
  CONVIVENCIA: "Convivencia",
};

export const ESTADO_RESERVA: Record<EstadoReserva, { label: string; tono: Tono }> = {
  SOLICITADA: { label: "Esperando aprobación", tono: "warning" },
  CONFIRMADA: { label: "Confirmada", tono: "success" },
  CANCELADA: { label: "Cancelada", tono: "neutral" },
  REALIZADA: { label: "Realizada", tono: "neutral" },
  RECHAZADA: { label: "Rechazada", tono: "danger" },
};

// --- Permisos (docs/PORTAL.md) --------------------------------------------------------------

const PERMISOS = {
  residente: ["RESIDENTE"],
  verPqrs: ["ADMIN", "AUXILIAR", "CONSEJO", "CONTABILIDAD", "MANTENIMIENTO"],
  gestionarPqrs: ["ADMIN", "AUXILIAR"],
  redactarCircular: ["ADMIN", "AUXILIAR"],
  publicarCircular: ["ADMIN"],
  verReservas: ["ADMIN", "AUXILIAR", "CONTABILIDAD", "CONSEJO"],
  decidirReserva: ["ADMIN", "AUXILIAR"],
  configurarZonas: ["ADMIN"],
} satisfies Record<string, Role[]>;

export type AccionPortal = keyof typeof PERMISOS;

export function puedePortal(rol: Role, accion: AccionPortal): boolean {
  return (PERMISOS[accion] as Role[]).includes(rol);
}

export const basePortal = (tenantId: string) => `/tenants/${tenantId}/portal`;

export function hora(h: string | null): string {
  return h ? h.slice(0, 5) : "";
}

/** "faltan 3 días hábiles", "vence hoy", "vencida hace 2 días hábiles". */
export function textoPlazo(p: Pick<PqrsResumen, "dias_habiles_restantes" | "vencida">): string {
  const d = p.dias_habiles_restantes;
  if (d === null) return "";
  if (p.vencida) return `vencida hace ${-d} día${d === -1 ? "" : "s"} hábil${d === -1 ? "" : "es"}`;
  if (d === 0) return "vence hoy";
  return `${d} día${d === 1 ? "" : "s"} hábil${d === 1 ? "" : "es"}`;
}
