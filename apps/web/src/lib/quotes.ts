const cop = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

export const formatCOP = (value: number | string | null | undefined) =>
  value === null || value === undefined || value === "" ? "—" : cop.format(Number(value));

export const PROGRESS_STEPS = [
  { key: "queued", label: "En cola" },
  { key: "extracting", label: "Leyendo las cotizaciones" },
  { key: "analyzing", label: "Comparando y redactando el análisis" },
] as const;

export const isRunning = (status: string) => ["PENDING", "RUNNING", "RETRYING"].includes(status);
