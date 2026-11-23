// Módulo de recaudos: tipos de la API, etiquetas y permisos por rol.
// Los permisos aquí solo deciden qué se MUESTRA; quien decide de verdad es la
// API (y, debajo, PostgreSQL con RLS y triggers).

import type { Role } from "./types";

export type MedioPago = "EFECTIVO" | "TRANSFERENCIA" | "CONSIGNACION";
export type EstadoRecaudo =
  | "RECAUDADO_EN_CAJA"
  | "ENTREGADO_ADMINISTRACION"
  | "PENDIENTE_VERIFICACION"
  | "CONSIGNADO"
  | "VERIFICADO"
  | "ANULADO";
export type TipoCobro = "FIJO" | "POR_HORA" | "VARIABLE";
export type EstadoEntrega = "PENDIENTE_CONFIRMACION" | "CONFIRMADA" | "RECHAZADA";
export type EstadoConsignacion = "REGISTRADA" | "APROBADA" | "VERIFICADA" | "RECHAZADA";
export type Severidad = "INFO" | "ADVERTENCIA" | "CRITICA";

export interface Concepto {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string | null;
  tipo_cobro: TipoCobro;
  tarifa_base: string | null;
  fraccion_minutos: number | null;
  requiere_reserva: boolean;
  requiere_vehiculo: boolean;
  activo: boolean;
}

export interface Zona {
  id: string;
  nombre: string;
  tarifa_alquiler: string | null;
  tarifa_aseo: string | null;
  activo: boolean;
}

export interface Reserva {
  id: string;
  zona_id: string;
  unidad_id: string | null;
  solicitante: string;
  fecha_evento: string;
  hora_inicio: string | null;
  hora_fin: string | null;
  estado: "SOLICITADA" | "CONFIRMADA" | "CANCELADA" | "REALIZADA";
  observaciones: string | null;
}

export interface Persona {
  id: string;
  nombre: string;
  rol: Role;
}

export interface Unidad {
  id: string;
  etiqueta: string;
}

export interface RecaudoFila {
  id: string;
  consecutivo: number;
  fecha_recaudo: string;
  concepto_id: string;
  concepto: string;
  valor_recibido: string;
  nombre_pagador: string;
  identificacion_pagador: string | null;
  unidad_id: string | null;
  unidad: string | null;
  medio_pago: MedioPago;
  estado: EstadoRecaudo;
  numero_comprobante: string | null;
  usuario_receptor_id: string;
  receptor: string;
  placa: string | null;
  tiene_soporte: boolean;
  cierre_id: string | null;
  entrega_id: string | null;
}

export interface RecaudosPagina {
  items: RecaudoFila[];
  total: number;
  suma: string;
  page: number;
  page_size: number;
}

export interface RecaudoDetalle extends RecaudoFila {
  observaciones: string | null;
  items: { concepto_id: string; concepto: string; descripcion: string | null; valor: string }[];
  parqueadero: {
    placa_vehiculo: string;
    hora_ingreso: string;
    hora_salida: string;
    minutos_totales: number;
    tarifa_sugerida: string;
  } | null;
  reserva: Reserva | null;
  zona: string | null;
  consignaciones: {
    consignacion_id: string;
    consecutivo: number;
    banco_destino: string;
    referencia_bancaria: string;
    estado: EstadoConsignacion;
    valor_aplicado: string;
  }[];
  saldo_por_consignar: string;
  soporte_url: string | null;
  anulado_por: string | null;
  anulado_at: string | null;
  motivo_anulacion: string | null;
  verificado_por: string | null;
  verificado_at: string | null;
}

export interface Auditoria {
  id: number;
  entidad: string;
  accion: "CREACION" | "EDICION" | "CAMBIO_ESTADO" | "ANULACION";
  usuario: string | null;
  fecha_hora: string;
  valores_anteriores: Record<string, unknown> | null;
  valores_nuevos: Record<string, unknown> | null;
  motivo: string | null;
}

export interface ResumenCaja {
  inicio_turno: string;
  cantidad: number;
  total_efectivo: string;
  recaudos: RecaudoFila[];
}

export interface Cierre {
  id: string;
  consecutivo: number;
  usuario_id: string;
  usuario: string;
  inicio_turno: string;
  fin_turno: string;
  saldo_inicial: string;
  saldo_esperado_sistema: string;
  valor_fisico_contado: string;
  diferencia: string;
  tipo_diferencia: "CUADRADO" | "SOBRANTE" | "FALTANTE";
  observacion_justificacion: string | null;
  cantidad_recaudos: number;
}

export interface Entrega {
  id: string;
  consecutivo: number;
  entregado_por_id: string;
  entregado_por: string;
  recibido_por_id: string;
  recibido_por: string;
  fecha_entrega: string;
  valor_total: string;
  valor_contado: string | null;
  estado: EstadoEntrega;
  confirmada_at: string | null;
  observaciones: string | null;
  cantidad_recaudos: number;
}

export interface Pendiente {
  recaudo: RecaudoFila;
  saldo: string;
}

export interface Consignacion {
  id: string;
  consecutivo: number;
  fecha_consignacion: string;
  banco_destino: string;
  referencia_bancaria: string;
  valor_consignado: string;
  valor_aplicado: string;
  usuario_consigna_id: string;
  usuario_consigna: string;
  estado: EstadoConsignacion;
  aprobada_at: string | null;
  verificada_at: string | null;
  observaciones: string | null;
  cantidad_recaudos: number;
}

export interface ConsignacionDetalle extends Consignacion {
  aplicaciones: { recaudo: RecaudoFila; valor_aplicado: string }[];
  soporte_url: string | null;
  aprobada_por: string | null;
  verificada_por: string | null;
}

export interface Alerta {
  id: string;
  tipo: "DIFERENCIA_CIERRE" | "DESCUADRE_CONSIGNACION" | "DESCUADRE_ENTREGA" | "TRANSFERENCIA_SIN_VERIFICAR" | "ANULACION_POSTERIOR";
  severidad: Severidad;
  entidad: string;
  entidad_id: string;
  mensaje: string;
  monto: string | null;
  estado: "ABIERTA" | "ATENDIDA";
  atendida_at: string | null;
  resolucion: string | null;
  created_at: string;
}

export interface Dashboard {
  periodo: string;
  total_mes: string;
  cantidad_mes: number;
  total_anio: string;
  por_concepto: { codigo: string; concepto: string; total: string }[];
  por_medio: Partial<Record<MedioPago, string>>;
  por_estado: Partial<Record<EstadoRecaudo, string>>;
  serie_diaria: { dia: string; total: string }[];
  efectivo_en_caja: string;
  efectivo_en_administracion: string;
  transferencias_pendientes: { cantidad: number; total: string };
  alertas_abiertas: number;
}

// --- Etiquetas -----------------------------------------------------------------

export type Tono = "neutral" | "info" | "success" | "warning" | "danger";

export const ESTADO: Record<EstadoRecaudo, { label: string; tono: Tono; ayuda: string }> = {
  RECAUDADO_EN_CAJA: { label: "En caja", tono: "warning", ayuda: "Efectivo en poder de recepción" },
  ENTREGADO_ADMINISTRACION: { label: "En administración", tono: "info", ayuda: "Efectivo entregado a la administración" },
  PENDIENTE_VERIFICACION: { label: "Por verificar", tono: "warning", ayuda: "Transferencia aún no validada en el extracto" },
  CONSIGNADO: { label: "Consignado", tono: "info", ayuda: "Depositado en el banco, falta conciliar" },
  VERIFICADO: { label: "Verificado", tono: "success", ayuda: "Conciliado por contabilidad" },
  ANULADO: { label: "Anulado", tono: "danger", ayuda: "Anulado con motivo; no suma en los totales" },
};

export const ESTADOS_ORDEN = Object.keys(ESTADO) as EstadoRecaudo[];

export const MEDIO: Record<MedioPago, string> = {
  EFECTIVO: "Efectivo",
  TRANSFERENCIA: "Transferencia",
  CONSIGNACION: "Consignación",
};

export const ESTADO_ENTREGA: Record<EstadoEntrega, { label: string; tono: Tono }> = {
  PENDIENTE_CONFIRMACION: { label: "Por confirmar", tono: "warning" },
  CONFIRMADA: { label: "Confirmada", tono: "success" },
  RECHAZADA: { label: "Rechazada", tono: "danger" },
};

export const ESTADO_CONSIGNACION: Record<EstadoConsignacion, { label: string; tono: Tono }> = {
  REGISTRADA: { label: "Por aprobar", tono: "warning" },
  APROBADA: { label: "Por verificar", tono: "info" },
  VERIFICADA: { label: "Verificada", tono: "success" },
  RECHAZADA: { label: "Rechazada", tono: "danger" },
};

export const SEVERIDAD: Record<Severidad, { label: string; tono: Tono }> = {
  CRITICA: { label: "Crítica", tono: "danger" },
  ADVERTENCIA: { label: "Advertencia", tono: "warning" },
  INFO: { label: "Información", tono: "neutral" },
};

export const TIPO_ALERTA: Record<Alerta["tipo"], string> = {
  DIFERENCIA_CIERRE: "Diferencia en cierre de caja",
  DESCUADRE_CONSIGNACION: "Consignación descuadrada",
  DESCUADRE_ENTREGA: "Entrega descuadrada",
  TRANSFERENCIA_SIN_VERIFICAR: "Transferencia sin verificar",
  ANULACION_POSTERIOR: "Anulación de dinero ya consignado",
};

export const ACCION: Record<Auditoria["accion"], string> = {
  CREACION: "Registro",
  EDICION: "Edición",
  CAMBIO_ESTADO: "Cambio de estado",
  ANULACION: "Anulación",
};

// --- Permisos (qué ve cada rol) ---------------------------------------------------

type Accion =
  | "resumen"
  | "registrar"
  | "movimientos"
  | "caja"
  | "conciliacion"
  | "aprobar"
  | "anular"
  | "verificar"
  | "auditoria"
  | "alertas"
  | "atender"
  | "configurar"
  | "recibir"
  | "reportes"
  | "cortes"
  | "generarCorte";

const PERMISOS: Record<Accion, Role[]> = {
  resumen: ["ADMIN", "CONTABILIDAD", "CONSEJO"],
  registrar: ["ADMIN", "AUXILIAR"],
  movimientos: ["ADMIN", "CONTABILIDAD", "AUXILIAR"],
  caja: ["ADMIN", "AUXILIAR"],
  conciliacion: ["ADMIN", "CONTABILIDAD", "AUXILIAR"],
  aprobar: ["ADMIN", "CONTABILIDAD"],
  anular: ["ADMIN"],
  verificar: ["ADMIN", "CONTABILIDAD"],
  auditoria: ["ADMIN", "CONTABILIDAD"],
  alertas: ["ADMIN", "CONTABILIDAD"],
  atender: ["ADMIN"],
  configurar: ["ADMIN"],
  recibir: ["ADMIN"],
  reportes: ["ADMIN", "CONTABILIDAD", "AUXILIAR", "CONSEJO"],
  cortes: ["ADMIN", "CONTABILIDAD", "CONSEJO"],
  generarCorte: ["ADMIN"],
};

export function puede(rol: Role, accion: Accion): boolean {
  return PERMISOS[accion].includes(rol);
}

export function tieneRecaudos(rol: Role): boolean {
  return rol !== "RESIDENTE";
}

// --- Formato --------------------------------------------------------------------

const COP = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

export function pesos(valor: string | number | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  return COP.format(Number(valor));
}

export function fechaHora(iso: string): string {
  return new Date(iso).toLocaleString("es-CO", {
    timeZone: "America/Bogota",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fechaCorta(iso: string): string {
  // Las fechas sin hora (AAAA-MM-DD) se interpretan como día local, no UTC
  const d = iso.length === 10 ? new Date(`${iso}T12:00:00`) : new Date(iso);
  return d.toLocaleDateString("es-CO", { timeZone: "America/Bogota", day: "2-digit", month: "short", year: "numeric" });
}

export function duracion(minutos: number): string {
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h ? `${h} h ${m ? `${m} min` : ""}`.trim() : `${m} min`;
}

/** "AAAA-MM-DD" de hoy en Bogotá (para inputs de fecha). */
export function hoyBogota(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" });
}

/** Valor para <input type="datetime-local"> en hora de Bogotá. */
export function aDatetimeLocal(d: Date): string {
  const s = d.toLocaleString("sv-SE", { timeZone: "America/Bogota" }); // "2026-11-22 14:05:00"
  return s.slice(0, 16).replace(" ", "T");
}

/** <input type="datetime-local"> (hora de Bogotá, UTC-5 sin horario de verano) -> ISO con zona. */
export function desdeDatetimeLocal(valor: string): string {
  return `${valor}:00-05:00`;
}

export const base = (tenantId: string) => `/tenants/${tenantId}/recaudos`;

// --- Reportes y cortes ------------------------------------------------------------

export type TipoReporte = "general" | "parqueadero" | "zonas" | "aseo" | "caja" | "auditoria";
export type TipoColumna = "texto" | "dinero" | "entero" | "fecha" | "fechahora" | "porcentaje";

export const REPORTES: Record<TipoReporte, { titulo: string; descripcion: string; roles: Role[] }> = {
  general: { titulo: "General de ingresos", descripcion: "Totales por concepto, medio de pago y estado del dinero", roles: ["ADMIN", "CONTABILIDAD"] },
  parqueadero: { titulo: "Parqueadero", descripcion: "Cada vehículo con placa, horas, tiempo y cobro", roles: ["ADMIN", "CONTABILIDAD"] },
  zonas: { titulo: "Zonas sociales", descripcion: "Alquileres con fecha del evento, alquiler y aseo", roles: ["ADMIN", "CONTABILIDAD"] },
  aseo: { titulo: "Aseo", descripcion: "Aseo cobrado directamente y con alquileres", roles: ["ADMIN", "CONTABILIDAD"] },
  caja: { titulo: "Caja (arqueo)", descripcion: "Saldos, ingresos en efectivo, entregas, consignaciones y diferencias", roles: ["ADMIN", "CONTABILIDAD", "AUXILIAR"] },
  auditoria: { titulo: "Trazabilidad y auditoría", descripcion: "Historial de movimientos, anulaciones y alertas", roles: ["ADMIN", "CONTABILIDAD"] },
};

export interface ReporteJson {
  tipo: TipoReporte;
  titulo: string;
  copropiedad: string;
  periodo: string;
  desde: string;
  hasta: string;
  generado: string;
  resumen: { etiqueta: string; valor: string }[];
  tablas: {
    titulo: string;
    columnas: { titulo: string; tipo: TipoColumna }[];
    filas: (string | number | null)[][];
    totales: (string | number | null)[] | null;
    nota: string | null;
  }[];
}

export interface Corte {
  periodo: string;
  nombre: string;
  total_mes: string;
  cantidad_mes: number;
  generado_at: string;
  pdf_url: string | null;
  xlsx_url: string | null;
  resumen: Record<string, string>;
}

export function celdaReporte(valor: string | number | null, tipo: TipoColumna): string {
  if (valor === null || valor === "") return "";
  if (tipo === "dinero") return pesos(valor);
  if (tipo === "porcentaje") return `${Number(valor).toLocaleString("es-CO", { maximumFractionDigits: 1 })} %`;
  if (tipo === "entero") return Number(valor).toLocaleString("es-CO");
  if (tipo === "fechahora") return fechaHora(String(valor));
  if (tipo === "fecha") return fechaCorta(String(valor).slice(0, 10));
  return String(valor);
}
