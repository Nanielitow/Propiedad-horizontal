"use client";

import { Building2, Check, Pencil, Repeat, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatLongDay, recurrenceLabel } from "@/lib/deadlines";
import type { Deadline } from "@/lib/types";

import { ConfidencePill, TypeBadge, UrgencyBadge } from "./badges";
import { SourceQuote } from "./source-quote";

interface Props {
  deadline: Deadline;
  onConfirm: () => void;
  onEdit: () => void;
  onDismiss: () => void;
}

export function ReviewCard({ deadline: d, onConfirm, onEdit, onDismiss }: Props) {
  const recurrence = recurrenceLabel(d.recurrence_months);
  return (
    <article className="flex flex-col rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <TypeBadge type={d.type} />
        <ConfidencePill value={d.confidence} />
      </div>

      <h3 className="mt-3 font-medium leading-snug">{d.title}</h3>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-lg font-semibold tracking-tight">{formatLongDay(d.due_date)}</span>
        <UrgencyBadge due={d.due_date} />
      </div>
      <div className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
        {d.provider_name && (
          <p className="flex items-center gap-1.5">
            <Building2 className="size-3.5" /> {d.provider_name}
          </p>
        )}
        {recurrence && (
          <p className="flex items-center gap-1.5">
            <Repeat className="size-3.5" /> {recurrence}
          </p>
        )}
      </div>

      <div className="mt-3 flex-1">
        <SourceQuote deadline={d} />
      </div>

      <div className="mt-4 flex gap-2">
        <Button onClick={onConfirm} className="flex-1">
          <Check /> Confirmar
        </Button>
        <Button variant="outline" onClick={onEdit}>
          <Pencil /> Editar
        </Button>
        <Button variant="ghost" onClick={onDismiss} className="text-muted-foreground" aria-label="Descartar">
          <X /> Descartar
        </Button>
      </div>
    </article>
  );
}
