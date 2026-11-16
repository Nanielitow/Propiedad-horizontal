"use client";

import { AlertCircle, CheckCircle2, CircleDashed, Loader2 } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { STATUS, STEP_LABEL } from "@/lib/labels";
import type { DocumentItem } from "@/lib/types";

const STEP_ORDER = ["download", "extract", "ocr", "chunking", "embedding", "saving", "done"];

export function StatusCell({ doc }: { doc: DocumentItem }) {
  const { status, job } = doc;

  if (status === "READY") {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-success">
        <CheckCircle2 className="size-4" /> {STATUS.READY.label}
      </span>
    );
  }

  if (status === "FAILED") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex cursor-help items-center gap-1.5 text-sm text-destructive">
            <AlertCircle className="size-4" /> {STATUS.FAILED.label}
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">{doc.error_message ?? job?.error ?? "Error desconocido"}</TooltipContent>
      </Tooltip>
    );
  }

  if (status === "QUEUED" || status === "PROCESSING") {
    const step = job?.current_step ?? null;
    const retrying = job?.status === "RETRYING";
    const index = step ? STEP_ORDER.indexOf(step) : -1;
    const percent = status === "QUEUED" || index < 0 ? 5 : Math.round(((index + 1) / STEP_ORDER.length) * 100);
    return (
      <div className="w-44">
        <span className="inline-flex items-center gap-1.5 text-sm text-primary">
          <Loader2 className="size-3.5 animate-spin" />
          {retrying
            ? `Reintentando (intento ${job.attempts + 1})`
            : status === "QUEUED"
              ? "En cola…"
              : (STEP_LABEL[step ?? ""] ?? "Procesando…")}
        </span>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-secondary">
          <div className="h-full rounded-full bg-primary transition-all duration-700" style={{ width: `${percent}%` }} />
        </div>
      </div>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
      <CircleDashed className="size-4" /> {STATUS.UPLOADED.label}
    </span>
  );
}
