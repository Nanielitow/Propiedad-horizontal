import type { Deadline, DeadlineType } from "./types";

export const DEADLINE_TYPE: Record<DeadlineType, string> = {
  POLICY_EXPIRY: "Póliza",
  CONTRACT_END: "Contrato",
  MAINTENANCE: "Mantenimiento",
  CERTIFICATION: "Certificado",
  OTHER: "Otro",
};

export const RECURRENCE_OPTIONS = [
  { value: "none", label: "No se repite" },
  { value: "1", label: "Cada mes" },
  { value: "3", label: "Cada 3 meses" },
  { value: "6", label: "Cada 6 meses" },
  { value: "12", label: "Cada año" },
  { value: "24", label: "Cada 2 años" },
];

export const REMINDER_OPTIONS = [60, 30, 15, 7, 1];

export function recurrenceLabel(months: number | null): string | null {
  if (!months) return null;
  if (months === 12) return "Se repite cada año";
  if (months === 1) return "Se repite cada mes";
  return `Se repite cada ${months} meses`;
}

/** "2027-03-31" -> Date local (sin desplazamiento por zona horaria). */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y!, m! - 1, d!);
}

export function toISODay(date: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}

export function today(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

export function daysUntil(iso: string): number {
  return Math.round((parseDay(iso).getTime() - today().getTime()) / 86_400_000);
}

export type Urgency = "overdue" | "critical" | "soon" | "later";

export function urgency(iso: string): Urgency {
  const d = daysUntil(iso);
  if (d < 0) return "overdue";
  if (d <= 7) return "critical";
  if (d <= 30) return "soon";
  return "later";
}

export function relativeLabel(iso: string): string {
  const d = daysUntil(iso);
  if (d === 0) return "Vence hoy";
  if (d === 1) return "Vence mañana";
  if (d === -1) return "Venció ayer";
  if (d < 0) return `Venció hace ${-d} días`;
  if (d <= 90) return `Vence en ${d} días`;
  return `Vence en ${Math.round(d / 30)} meses`;
}

const longFmt = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "long", year: "numeric" });
const shortFmt = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", year: "numeric" });
export const formatLongDay = (iso: string) => longFmt.format(parseDay(iso));
export const formatShortDay = (iso: string) => shortFmt.format(parseDay(iso));

export function confidenceLevel(c: number | null): { label: string; tone: "high" | "medium" | "low" } {
  if (c === null || c >= 0.85) return { label: "Confianza alta", tone: "high" };
  if (c >= 0.65) return { label: "Confianza media", tone: "medium" };
  return { label: "Confianza baja", tone: "low" };
}

/** Alertas para la barra lateral: por revisar + vencidos + vencen en <= 7 días. */
export function alertCount(deadlines: Deadline[] | undefined): number {
  if (!deadlines) return 0;
  return deadlines.filter(
    (d) => d.status === "PENDING_REVIEW" || (d.status === "ACTIVE" && daysUntil(d.due_date) <= 7),
  ).length;
}
