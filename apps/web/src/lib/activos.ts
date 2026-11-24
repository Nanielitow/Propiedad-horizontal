// Módulo de activos y mantenimiento: tipos de la API, etiquetas y permisos por rol.
// Los permisos aquí solo deciden qué se MUESTRA; quien decide es la API (y RLS y
// triggers en PostgreSQL). Los costos llegan en null a quien no debe verlos.

import type { Tono } from "./recaudos";
import type { Role } from "./types";

export type Color = "VERDE" | "AMARILLO" | "ROJO";
export type EstadoActivo = "OPERATIVO" | "OPERATIVO_CON_OBSERVACIONES" | "EN_MANTENIMIENTO" | "FUERA_DE_SERVICIO" | "DADO_DE_BAJA";
export type Criticidad = "ALTA" | "MEDIA" | "BAJA";
export type Periodicidad =
  | "SEMANAL"
  | "QUINCENAL"
  | "MENSUAL"
  | "BIMESTRAL"
  | "TRIMESTRAL"
  | "SEMESTRAL"
  | "ANUAL"
  | "POR_HORAS_USO";
export type BaseCalculo = "CALENDARIO_FIJO" | "DESDE_ULTIMA_EJECUCION";
export type EstadoActividad = "PROGRAMADA" | "EJECUTADA" | "CANCELADA";
export type TipoMantenimiento = "PREVENTIVO" | "CORRECTIVO" | "PREDICTIVO" | "INSPECCION_TECNICA" | "EMERGENCIA";
export type PrioridadNovedad = "BAJA" | "MEDIA" | "ALTA" | "CRITICA";
export type EstadoNovedad =
  | "REPORTADA"
  | "EN_GESTION"
  | "PENDIENTE_COTIZACION"
  | "PROGRAMADA"
  | "EN_EJECUCION"
  | "CERRADA"
  | "DESCARTADA";
export type PrioridadRecomendacion = "BAJA" | "MEDIA" | "ALTA";
export type EstadoRecomendacion = "PENDIENTE" | "EN_PROCESO" | "EJECUTADA" | "DESCARTADA_CON_JUSTIFICACION";
export type TipoDocumentoActivo =
  | "MANUAL"
  | "PLANO"
  | "FICHA_TECNICA"
  | "GARANTIA"
  | "CONTRATO"
  | "ACTA"
  | "CERTIFICACION"
  | "FACTURA"
  | "INFORME_TECNICO"
  | "OTRO";
export type EntidadEvidencia = "ACTIVO" | "MANTENIMIENTO" | "NOVEDAD";
export type MomentoEvidencia = "ANTES" | "DESPUES" | "EVIDENCIA" | "FOTO_ACTIVO" | "INFORME" | "FACTURA";

export interface Ref {
  id: string;
  nombre: string;
}

export interface Categoria {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string | null;
  subtipos: string[];
  es_infraestructura: boolean;
}

export interface Contratista {
  id: string;
  razon_social: string;
  nit: string | null;
  contacto_nombre: string | null;
  telefono: string | null;
  email: string | null;
  especialidades: string[];
  vigencia_contrato_inicio: string | null;
  vigencia_contrato_fin: string | null;
  alcance_contrato: string | null;
  periodicidad_pactada: string | null;
  valor_contrato: string | null;
  contrato_documento_id: string | null;
  activo: boolean;
}

export interface ContratistaDetalle extends Contratista {
  activos: Ref[];
  mantenimientos: number;
  correctivos: number;
  costo_total: string | null;
}

export interface PersonaAsignable {
  id: string;
  nombre: string;
  rol: Role;
}

export interface ActivoResumen {
  id: string;
  codigo_interno: string;
  nombre: string;
  categoria: Ref;
  subtipo: string | null;
  ubicacion: string;
  estado: EstadoActivo;
  criticidad: Criticidad;
  semaforo: Color | null;
  proxima_fecha: string | null;
  novedades_abiertas: number;
}

export interface ActivosPagina {
  items: ActivoResumen[];
  total: number;
  page: number;
  page_size: number;
  por_semaforo: Record<Color | "SIN_PLAN", number>;
  por_estado: Partial<Record<EstadoActivo, number>>;
}

export interface Actividad {
  id: string;
  plan: Ref;
  activo: Ref;
  activo_codigo: string;
  ubicacion: string;
  fecha_programada: string;
  fecha_original: string;
  estado: EstadoActividad;
  asignado_a: Ref | null;
  contratista: Ref | null;
  semaforo: Color | null;
  dias_restantes: number | null;
  reprogramada: boolean;
  mantenimiento_id: string | null;
}

export interface Plan {
  id: string;
  activo: Ref;
  activo_codigo: string;
  nombre: string;
  actividades_checklist: string[];
  periodicidad: Periodicidad;
  intervalo_horas: number | null;
  base_calculo: BaseCalculo;
  fecha_inicio: string;
  contratista: Ref | null;
  costo_estimado: string | null;
  aprobado: boolean;
  aprobado_por: Ref | null;
  aprobado_at: string | null;
  activo_plan: boolean;
  proxima_fecha: string | null;
  ejecuciones: number;
}

export interface MantenimientoResumen {
  id: string;
  codigo: string;
  activo: Ref;
  activo_codigo: string;
  tipo: TipoMantenimiento;
  fecha_ejecucion: string;
  nombre_tecnico: string;
  contratista: Ref | null;
  estado_post_intervencion: EstadoActivo;
  costo_total: string | null;
  anulado: boolean;
}

export interface Recomendacion {
  id: string;
  activo: Ref;
  activo_codigo: string;
  mantenimiento_origen: Ref | null;
  descripcion: string;
  prioridad: PrioridadRecomendacion;
  estado: EstadoRecomendacion;
  responsable: Ref | null;
  fecha_limite: string | null;
  vencida: boolean;
  costo_estimado: string | null;
  observaciones_administracion: string | null;
  justificacion_descarte: string | null;
  mantenimiento_ejecucion_id: string | null;
  created_at: string;
}

export interface MantenimientoDetalle extends MantenimientoResumen {
  tiempo_ejecucion_horas: string | null;
  diagnostico_inicial: string | null;
  actividades_realizadas: string;
  repuestos_utilizados: string | null;
  novedades_encontradas: string | null;
  recomendaciones_tecnico: string | null;
  checklist: { actividad: string; resultado: "HECHO" | "NO_APLICA" | "PENDIENTE"; nota?: string | null }[];
  costo_mano_obra: string | null;
  costo_repuestos: string | null;
  fecha_proximo_recomendado: string | null;
  actividad_id: string | null;
  plan: Ref | null;
  novedad: Ref | null;
  informe_documento_id: string | null;
  factura_documento_id: string | null;
  registrado_por: Ref;
  created_at: string;
  anulado_por: Ref | null;
  anulado_at: string | null;
  motivo_anulacion: string | null;
  recomendaciones: Recomendacion[];
}

export interface Novedad {
  id: string;
  codigo: string;
  activo: Ref;
  activo_codigo: string;
  ubicacion: string;
  fecha_reporte: string;
  reportado_por: Ref;
  descripcion: string;
  riesgo_identificado: string | null;
  prioridad: PrioridadNovedad;
  estado: EstadoNovedad;
  contratista_asignado: Ref | null;
  asignado_a: Ref | null;
  cotizacion_id: string | null;
  fecha_atencion: string | null;
  diagnostico: string | null;
  solucion_implementada: string | null;
  costo_reparacion: string | null;
  cerrada_por: Ref | null;
  cerrada_at: string | null;
  motivo_descarte: string | null;
  mantenimientos: Ref[];
  horas_sin_atender: number | null;
}

export interface Evidencia {
  id: string;
  entidad: EntidadEvidencia;
  entidad_id: string;
  momento: MomentoEvidencia;
  content_type: string;
  size_bytes: number;
  descripcion: string | null;
  subido_por: Ref | null;
  created_at: string;
  url: string;
}

export interface Lectura {
  id: string;
  fecha: string;
  horas_acumuladas: string;
}

export interface EstadoHoras {
  plan_id: string;
  intervalo_horas: number;
  horas_desde_ultimo: string;
  horas_restantes: string;
  uso_diario: string | null;
  fecha_estimada: string | null;
}

export interface ActivoDetalle {
  id: string;
  codigo_interno: string;
  qr_token: string;
  qr_url: string;
  nombre: string;
  categoria: Ref;
  subtipo: string | null;
  ubicacion: string;
  marca: string | null;
  modelo: string | null;
  fabricante: string | null;
  numero_serie: string | null;
  especificaciones: Record<string, string | number | boolean>;
  vida_util_anios: number | null;
  vida_util_consumida: string | null;
  fecha_instalacion: string | null;
  instalador: Ref | null;
  mantenedor: Ref | null;
  fecha_vencimiento_garantia: string | null;
  garantia_vigente: boolean | null;
  criticidad: Criticidad;
  estado: EstadoActivo;
  motivo_baja: string | null;
  fecha_baja: string | null;
  semaforo: Color | null;
  created_at: string;
  updated_at: string;
  documentos: { document_id: string; titulo: string; tipo: TipoDocumentoActivo; fecha_documento: string | null; vinculado_at: string }[];
  vencimientos: { id: string; title: string; due_date: string | null; status: string }[];
  planes: Plan[];
  proximas_actividades: Actividad[];
  mantenimientos: MantenimientoResumen[];
  novedades: Novedad[];
  recomendaciones: Recomendacion[];
  lecturas: Lectura[];
  horas: EstadoHoras[];
  costo_acumulado: string | null;
  costo_anio: string | null;
  puede_ver_costos: boolean;
}

export interface QrResuelto {
  id: string;
  codigo_interno: string;
  nombre: string;
  ubicacion: string;
  estado: EstadoActivo;
  criticidad: Criticidad;
  semaforo: Color | null;
  ultimo_mantenimiento: MantenimientoResumen | null;
  proxima_actividad: Actividad | null;
  novedades_abiertas: Novedad[];
  usa_horometro: boolean;
}

export interface AuditoriaActivo {
  id: number;
  entidad: string;
  entidad_id: string;
  accion: "CREACION" | "EDICION" | "CAMBIO_ESTADO" | "ANULACION";
  usuario: Ref | null;
  valores_anteriores: Record<string, unknown> | null;
  valores_nuevos: Record<string, unknown> | null;
  motivo: string | null;
  fecha_hora: string;
}

export interface Reprogramacion {
  id: string;
  fecha_anterior: string;
  nueva_fecha: string;
  motivo: string;
  created_at: string;
}

// --- Etiquetas -----------------------------------------------------------------------

export const SEMAFORO: Record<Color, { label: string; tono: Tono; punto: string; ayuda: string }> = {
  VERDE: { label: "Al día", tono: "success", punto: "bg-success", ayuda: "Faltan más de 15 días" },
  AMARILLO: { label: "Próximo", tono: "warning", punto: "bg-warning", ayuda: "Vence en 15 días o menos" },
  ROJO: { label: "Vencido", tono: "danger", punto: "bg-destructive", ayuda: "La fecha pasó sin ejecutarse" },
};

export const ESTADO_ACTIVO: Record<EstadoActivo, { label: string; tono: Tono }> = {
  OPERATIVO: { label: "Operativo", tono: "success" },
  OPERATIVO_CON_OBSERVACIONES: { label: "Con observaciones", tono: "warning" },
  EN_MANTENIMIENTO: { label: "En mantenimiento", tono: "info" },
  FUERA_DE_SERVICIO: { label: "Fuera de servicio", tono: "danger" },
  DADO_DE_BAJA: { label: "Dado de baja", tono: "neutral" },
};

export const CRITICIDAD: Record<Criticidad, { label: string; tono: Tono }> = {
  ALTA: { label: "Criticidad alta", tono: "danger" },
  MEDIA: { label: "Criticidad media", tono: "warning" },
  BAJA: { label: "Criticidad baja", tono: "neutral" },
};

export const PERIODICIDAD: Record<Periodicidad, string> = {
  SEMANAL: "Semanal",
  QUINCENAL: "Quincenal (cada 15 días)",
  MENSUAL: "Mensual",
  BIMESTRAL: "Bimestral",
  TRIMESTRAL: "Trimestral",
  SEMESTRAL: "Semestral",
  ANUAL: "Anual",
  POR_HORAS_USO: "Por horas de uso",
};

export const TIPO_MANTENIMIENTO: Record<TipoMantenimiento, { label: string; tono: Tono }> = {
  PREVENTIVO: { label: "Preventivo", tono: "success" },
  CORRECTIVO: { label: "Correctivo", tono: "warning" },
  PREDICTIVO: { label: "Predictivo", tono: "info" },
  INSPECCION_TECNICA: { label: "Inspección técnica", tono: "info" },
  EMERGENCIA: { label: "Emergencia", tono: "danger" },
};

export const PRIORIDAD_NOVEDAD: Record<PrioridadNovedad, { label: string; tono: Tono }> = {
  CRITICA: { label: "Crítica", tono: "danger" },
  ALTA: { label: "Alta", tono: "warning" },
  MEDIA: { label: "Media", tono: "info" },
  BAJA: { label: "Baja", tono: "neutral" },
};

export const ESTADO_NOVEDAD: Record<EstadoNovedad, { label: string; tono: Tono; ayuda: string }> = {
  REPORTADA: { label: "Reportada", tono: "danger", ayuda: "Nadie la ha atendido todavía" },
  EN_GESTION: { label: "En gestión", tono: "warning", ayuda: "La administración la está revisando" },
  PENDIENTE_COTIZACION: { label: "Pendiente de cotización", tono: "warning", ayuda: "Se esperan cotizaciones" },
  PROGRAMADA: { label: "Programada", tono: "info", ayuda: "La reparación tiene fecha" },
  EN_EJECUCION: { label: "En ejecución", tono: "info", ayuda: "Se está reparando" },
  CERRADA: { label: "Cerrada", tono: "success", ayuda: "Resuelta" },
  DESCARTADA: { label: "Descartada", tono: "neutral", ayuda: "Duplicada o no procede" },
};

/** Igual que dominio.TRANSICIONES_NOVEDAD y el trigger de la base de datos. */
export const TRANSICIONES: Record<EstadoNovedad, EstadoNovedad[]> = {
  REPORTADA: ["EN_GESTION", "DESCARTADA"],
  EN_GESTION: ["PENDIENTE_COTIZACION", "PROGRAMADA", "EN_EJECUCION", "DESCARTADA"],
  PENDIENTE_COTIZACION: ["PROGRAMADA", "DESCARTADA"],
  PROGRAMADA: ["EN_EJECUCION"],
  EN_EJECUCION: ["CERRADA"],
  CERRADA: [],
  DESCARTADA: [],
};
export const NOVEDAD_ABIERTA: EstadoNovedad[] = ["REPORTADA", "EN_GESTION", "PENDIENTE_COTIZACION", "PROGRAMADA", "EN_EJECUCION"];

export const PRIORIDAD_RECOMENDACION: Record<PrioridadRecomendacion, { label: string; tono: Tono }> = {
  ALTA: { label: "Alta", tono: "danger" },
  MEDIA: { label: "Media", tono: "warning" },
  BAJA: { label: "Baja", tono: "neutral" },
};

export const ESTADO_RECOMENDACION: Record<EstadoRecomendacion, { label: string; tono: Tono }> = {
  PENDIENTE: { label: "Pendiente", tono: "warning" },
  EN_PROCESO: { label: "En proceso", tono: "info" },
  EJECUTADA: { label: "Ejecutada", tono: "success" },
  DESCARTADA_CON_JUSTIFICACION: { label: "Descartada", tono: "neutral" },
};

export const TIPO_DOCUMENTO: Record<TipoDocumentoActivo, string> = {
  MANUAL: "Manual",
  PLANO: "Plano",
  FICHA_TECNICA: "Ficha técnica",
  GARANTIA: "Garantía",
  CONTRATO: "Contrato",
  ACTA: "Acta",
  CERTIFICACION: "Certificación",
  FACTURA: "Factura",
  INFORME_TECNICO: "Informe técnico",
  OTRO: "Otro",
};

export const MOMENTO: Record<MomentoEvidencia, string> = {
  ANTES: "Antes",
  DESPUES: "Después",
  EVIDENCIA: "Evidencia",
  FOTO_ACTIVO: "Foto del activo",
  INFORME: "Informe",
  FACTURA: "Factura",
};

// --- Permisos de pantalla (docs/MANTENIMIENTO.md §3) --------------------------------------

type Accion =
  | "ver"
  | "crearActivo"
  | "editarActivo"
  | "darDeBaja"
  | "documentar"
  | "subirFotos"
  | "contratistas"
  | "gestionarContratistas"
  | "crearPlan"
  | "aprobarPlan"
  | "reprogramar"
  | "asignar"
  | "registrarMantenimiento"
  | "anularMantenimiento"
  | "reportarNovedad"
  | "gestionarNovedad"
  | "cerrarNovedad"
  | "gestionarRecomendacion"
  | "descartarRecomendacion"
  | "miTrabajo"
  | "auditoria";

const PERSONAL: Role[] = ["ADMIN", "AUXILIAR", "MANTENIMIENTO", "CONTABILIDAD"];
const OPERACION: Role[] = ["ADMIN", "AUXILIAR", "MANTENIMIENTO"];
const PERMISOS: Record<Accion, Role[]> = {
  ver: PERSONAL,
  crearActivo: ["ADMIN"],
  editarActivo: ["ADMIN", "AUXILIAR"],
  darDeBaja: ["ADMIN"],
  documentar: ["ADMIN", "AUXILIAR"],
  subirFotos: OPERACION,
  contratistas: ["ADMIN", "AUXILIAR", "CONTABILIDAD"],
  gestionarContratistas: ["ADMIN"],
  crearPlan: ["ADMIN", "AUXILIAR"],
  aprobarPlan: ["ADMIN"],
  reprogramar: ["ADMIN", "AUXILIAR"],
  asignar: ["ADMIN", "AUXILIAR"],
  registrarMantenimiento: OPERACION,
  anularMantenimiento: ["ADMIN"],
  reportarNovedad: OPERACION,
  gestionarNovedad: OPERACION,
  cerrarNovedad: ["ADMIN"],
  gestionarRecomendacion: OPERACION,
  descartarRecomendacion: ["ADMIN"],
  miTrabajo: ["MANTENIMIENTO"],
  auditoria: ["ADMIN", "AUXILIAR", "CONTABILIDAD"],
};

export function puedeActivos(rol: Role, accion: Accion): boolean {
  return PERMISOS[accion].includes(rol);
}

export const baseActivos = (tenantId: string) => `/tenants/${tenantId}/activos`;

/** "faltan 3 días", "vence hoy", "venció hace 2 días". */
export function textoDias(dias: number | null): string {
  if (dias === null) return "";
  if (dias === 0) return "vence hoy";
  if (dias === 1) return "vence mañana";
  if (dias > 0) return `en ${dias} días`;
  return dias === -1 ? "venció ayer" : `venció hace ${-dias} días`;
}

export function horasTexto(horas: number): string {
  if (horas < 24) return `${horas} h`;
  const d = Math.floor(horas / 24);
  return `${d} día${d === 1 ? "" : "s"}`;
}

/** Archivo del navegador → evidencia: URL firmada, subida directa y registro. */
export const TIPOS_EVIDENCIA = "image/jpeg,image/png,image/webp,application/pdf";
