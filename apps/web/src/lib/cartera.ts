// Módulo de cartera de cuotas: tipos de la API, etiquetas y permisos por rol.
// Los permisos aquí solo deciden qué se MUESTRA; quien decide es la API (y la RLS).

import type { MedioPago, Tono } from "./recaudos";
import type { Role } from "./types";
import type { TipoUnidad } from "./unidades";

export type MetodoCuota = "COEFICIENTE" | "TARIFA_POR_TIPO";
export type TipoConcepto = "ORDINARIA" | "EXTRAORDINARIA" | "INTERES" | "MULTA" | "OTRO";
export type Rango = "corriente" | "1_30" | "31_60" | "61_90" | "mas_90";

export interface ConfigCartera {
  metodo: MetodoCuota;
  presupuesto_mensual: string | null;
  tarifas_por_tipo: Partial<Record<TipoUnidad, string>>;
  redondeo: number;
  dia_vencimiento: number;
  descuento_pct: string;
  dia_limite_descuento: number | null;
  cobrar_intereses: boolean;
  tasa_mora_mensual: string;
  nota_cuenta_cobro: string | null;
  updated_at: string;
}

export interface ConceptoCartera {
  id: string;
  codigo: string;
  nombre: string;
  tipo: TipoConcepto;
  genera_interes: boolean;
  activo: boolean;
}

export interface Periodo {
  id: string;
  anio: number;
  mes: number;
  nombre: string;
  estado: "EMITIDO" | "ANULADO";
  fecha_emision: string;
  fecha_vencimiento: string;
  fecha_limite_descuento: string | null;
  metodo: MetodoCuota;
  presupuesto_mensual: string | null;
  descuento_pct: string;
  tasa_mora_mensual: string | null;
  unidades_facturadas: number;
  total_cuotas: string;
  total_intereses: string;
  recaudado: string;
  pendiente: string;
  advertencias: string[];
  motivo_anulacion: string | null;
}

export interface Prefactura {
  anio: number;
  mes: number;
  nombre: string;
  fecha_emision: string;
  fecha_vencimiento: string;
  fecha_limite_descuento: string | null;
  metodo: MetodoCuota;
  total_cuotas: string;
  total_intereses: string;
  unidades: number;
  lineas: { unidad_id: string; etiqueta: string; responsable: string | null; cuota: string | null; capital_vencido: string; interes: string }[];
  advertencias: string[];
}

export interface Cargo {
  id: string;
  unidad_id: string;
  unidad: string;
  concepto: string;
  tipo_concepto: TipoConcepto;
  descripcion: string;
  valor: string;
  saldo: string;
  fecha_causacion: string;
  fecha_vencimiento: string;
  dias_mora: number;
  responsable_nombre: string | null;
  estado: "VIGENTE" | "ANULADO";
  periodo_id: string | null;
}

export interface Pago {
  id: string;
  consecutivo: number;
  unidad_id: string;
  unidad: string;
  fecha_pago: string;
  valor: string;
  aplicado: string;
  a_favor: string;
  descuentos: string;
  medio_pago: MedioPago;
  referencia: string | null;
  pagador_nombre: string | null;
  tiene_soporte: boolean;
  observaciones: string | null;
  estado: "APLICADO" | "ANULADO";
  registrado_por: string | null;
  created_at: string;
  motivo_anulacion: string | null;
}

export interface PagosPagina {
  items: Pago[];
  total: number;
  total_valor: string;
  page: number;
  page_size: number;
}

export interface ResultadoPago {
  pago: Pago;
  aplicaciones: { cargo_id: string; descripcion: string; valor: string; descuento: string }[];
  a_favor: string;
  saldo_pendiente: string;
}

export interface Movimiento {
  fecha: string;
  tipo: "CARGO" | "PAGO" | "AJUSTE";
  descripcion: string;
  cargo: string;
  abono: string;
  saldo: string;
  anulado: boolean;
  referencia_id: string;
  consecutivo: number | null;
}

export interface EstadoCuenta {
  unidad_id: string;
  unidad: string;
  responsable: string | null;
  copropiedad: string;
  corte: string;
  saldo_total: string;
  saldo_vencido: string;
  saldo_corriente: string;
  saldo_a_favor: string;
  dias_mora: number;
  edades: Record<Rango, string>;
  al_dia: boolean;
  pendientes: Cargo[];
  movimientos: Movimiento[];
  ultimo_pago: string | null;
}

export interface Moroso {
  unidad_id: string;
  unidad: string;
  responsable: string | null;
  telefono: string | null;
  saldo_total: string;
  saldo_vencido: string;
  edades: Record<Rango, string>;
  dias_mora: number;
  cuotas_vencidas: number;
  ultimo_pago: string | null;
}

export interface Morosos {
  corte: string;
  items: Moroso[];
  total_vencido: string;
  edades: Record<Rango, string>;
}

export interface ResumenCartera {
  corte: string;
  configurada: boolean;
  cartera_total: string;
  cartera_vencida: string;
  saldo_a_favor: string;
  edades: Record<Rango, string>;
  unidades_en_mora: number;
  unidades_al_dia: number;
  unidades_facturadas: number;
  facturado_mes: string;
  recaudado_mes: string;
  recaudo_pct: string | null;
  ultimos_periodos: Periodo[];
  recaudo_mensual: { mes: string; etiqueta: string; facturado: string; recaudado: string }[];
}

export interface PazYSalvo {
  id: string;
  consecutivo: number;
  unidad_id: string;
  fecha_emision: string;
  valido_hasta: string;
  titular_nombre: string | null;
  codigo_verificacion: string;
}

// --- Etiquetas ------------------------------------------------------------------------------

export const RANGO: Record<Rango, { label: string; tono: Tono }> = {
  corriente: { label: "Sin vencer", tono: "neutral" },
  "1_30": { label: "1 a 30 días", tono: "warning" },
  "31_60": { label: "31 a 60 días", tono: "warning" },
  "61_90": { label: "61 a 90 días", tono: "danger" },
  mas_90: { label: "Más de 90 días", tono: "danger" },
};
export const RANGOS_VENCIDOS: Rango[] = ["1_30", "31_60", "61_90", "mas_90"];

export const METODO: Record<MetodoCuota, { label: string; ayuda: string }> = {
  COEFICIENTE: { label: "Por coeficiente", ayuda: "Presupuesto mensual × coeficiente de cada unidad (Ley 675)" },
  TARIFA_POR_TIPO: { label: "Tarifa por tipo de unidad", ayuda: "Un valor fijo para apartamentos, otro para locales, etc." },
};

export function tonoMora(dias: number): Tono {
  if (dias <= 0) return "success";
  if (dias <= 60) return "warning";
  return "danger";
}

// --- Permisos (docs/CARTERA.md §3) -----------------------------------------------------------

const PERMISOS = {
  ver: ["ADMIN", "CONTABILIDAD", "AUXILIAR", "CONSEJO"],
  configurar: ["ADMIN"],
  facturar: ["ADMIN"],
  registrarPago: ["ADMIN", "CONTABILIDAD"],
  anular: ["ADMIN"],
  pazYSalvo: ["ADMIN", "CONTABILIDAD", "AUXILIAR"],
  miCartera: ["RESIDENTE"],
} satisfies Record<string, Role[]>;

export type AccionCartera = keyof typeof PERMISOS;

export function puedeCartera(rol: Role, accion: AccionCartera): boolean {
  return (PERMISOS[accion] as Role[]).includes(rol);
}

export const baseCartera = (tenantId: string) => `/tenants/${tenantId}/cartera`;

export function compactoPesos(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toLocaleString("es-CO", { maximumFractionDigits: 1 })} M`;
  if (Math.abs(v) >= 1_000) return `$${Math.round(v / 1_000)} mil`;
  return `$${v}`;
}
