import type { AccessLevel, Category, DocStatus, Role } from "./types";

export const CATEGORIES: Record<
  Category,
  { label: string; hint: string; defaultAccess: AccessLevel }
> = {
  CONVIVENCIA: {
    label: "Convivencia",
    hint: "Manual de convivencia, reglamento de propiedad horizontal",
    defaultAccess: "PUBLIC",
  },
  COMUNICADOS: {
    label: "Comunicados",
    hint: "Circulares y avisos para los residentes",
    defaultAccess: "PUBLIC",
  },
  ACTAS: {
    label: "Actas",
    hint: "Actas de asamblea y del consejo de administración",
    defaultAccess: "ADMIN",
  },
  CONTRATOS: {
    label: "Contratos",
    hint: "Vigilancia, aseo, pólizas de seguro, proveedores",
    defaultAccess: "ADMIN",
  },
  MANTENIMIENTO: {
    label: "Mantenimiento",
    hint: "Ascensores, tanques de agua, certificados técnicos",
    defaultAccess: "ADMIN",
  },
  FINANCIERO: {
    label: "Financiero",
    hint: "Estados financieros, presupuestos, informes contables",
    defaultAccess: "ADMIN",
  },
  COTIZACIONES: {
    label: "Cotizaciones",
    hint: "Propuestas de proveedores para comparar",
    defaultAccess: "ADMIN",
  },
};

export const CATEGORY_ORDER = Object.keys(CATEGORIES) as Category[];

export const ACCESS: Record<AccessLevel, { label: string; short: string }> = {
  PUBLIC: { label: "Residentes y administración", short: "Residentes" },
  ADMIN: { label: "Solo administración", short: "Administración" },
};

export const ROLE_LABEL: Record<Role, string> = {
  ADMIN: "Administración",
  RESIDENTE: "Residente",
  AUXILIAR: "Recepción",
  CONTABILIDAD: "Contabilidad",
  CONSEJO: "Consejo de administración",
  MANTENIMIENTO: "Mantenimiento",
};

export const STATUS: Record<DocStatus, { label: string; tone: "neutral" | "info" | "success" | "danger" }> = {
  UPLOADED: { label: "Subida incompleta", tone: "neutral" },
  QUEUED: { label: "En cola", tone: "info" },
  PROCESSING: { label: "Procesando", tone: "info" },
  READY: { label: "Disponible", tone: "success" },
  FAILED: { label: "Con error", tone: "danger" },
};

// Paso del pipeline de ingesta -> texto para el usuario
export const STEP_LABEL: Record<string, string> = {
  download: "Preparando archivo",
  extract: "Leyendo el texto",
  ocr: "Reconociendo texto escaneado",
  chunking: "Organizando el contenido",
  embedding: "Indexando para el buscador",
  saving: "Guardando",
  done: "Listo",
};

export const isProcessing = (status: DocStatus) => status === "QUEUED" || status === "PROCESSING";

const dateFmt = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

export const formatDate = (iso: string) => dateFmt.format(new Date(iso));
export const formatDateTime = (iso: string) => dateTimeFmt.format(new Date(iso));

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function pageLabel(from: number, to: number): string {
  return from === to ? `pág. ${from}` : `págs. ${from}–${to}`;
}
