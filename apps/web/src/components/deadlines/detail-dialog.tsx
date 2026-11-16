"use client";

import { Bell, Building2, CheckCheck, Pencil, Repeat, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatLongDay, recurrenceLabel } from "@/lib/deadlines";
import type { Deadline } from "@/lib/types";

import { TypeBadge, UrgencyBadge } from "./badges";
import { SourceQuote } from "./source-quote";

interface Props {
  deadline: Deadline | null;
  onClose: () => void;
  onConfirm: (d: Deadline) => void;
  onComplete: (d: Deadline) => void;
  onEdit: (d: Deadline) => void;
  onDismiss: (d: Deadline) => void;
}

export function DeadlineDetailDialog({ deadline: d, onClose, onConfirm, onComplete, onEdit, onDismiss }: Props) {
  if (!d) return null;
  const recurrence = recurrenceLabel(d.recurrence_months);
  const run = (fn: (d: Deadline) => void) => () => {
    onClose();
    fn(d);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="mb-1 flex items-center gap-2">
            <TypeBadge type={d.type} />
            {d.status === "PENDING_REVIEW" && (
              <span className="rounded border border-warning/30 bg-warning-soft px-1.5 py-0.5 text-xs text-warning">
                Pendiente de revisión
              </span>
            )}
            {d.status === "DONE" && (
              <span className="rounded border border-success/30 bg-success-soft px-1.5 py-0.5 text-xs text-success">
                Realizado
              </span>
            )}
          </div>
          <DialogTitle>{d.title}</DialogTitle>
          <DialogDescription className="flex flex-wrap items-center gap-2 pt-1">
            <span className="font-medium text-foreground">{formatLongDay(d.due_date)}</span>
            {d.status !== "DONE" && <UrgencyBadge due={d.due_date} />}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <div className="space-y-1 text-muted-foreground">
            {d.provider_name && (
              <p className="flex items-center gap-2">
                <Building2 className="size-4" /> {d.provider_name}
              </p>
            )}
            {recurrence && (
              <p className="flex items-center gap-2">
                <Repeat className="size-4" /> {recurrence}
              </p>
            )}
            {d.status === "ACTIVE" && d.reminder_days.length > 0 && (
              <p className="flex items-center gap-2">
                <Bell className="size-4" /> Avisos {d.reminder_days.map((n) => `${n} d`).join(", ")} antes
              </p>
            )}
          </div>
          <SourceQuote deadline={d} />
        </div>

        <DialogFooter className="gap-2 sm:justify-between">
          {d.status !== "DONE" ? (
            <Button variant="ghost" className="text-muted-foreground" onClick={run(onDismiss)}>
              <X /> Descartar
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            {d.status !== "DONE" && (
              <Button variant="outline" onClick={run(onEdit)}>
                <Pencil /> Editar
              </Button>
            )}
            {d.status === "PENDING_REVIEW" && (
              <Button onClick={run(onConfirm)}>
                <CheckCheck /> Confirmar
              </Button>
            )}
            {d.status === "ACTIVE" && (
              <Button onClick={run(onComplete)}>
                <CheckCheck /> {d.type === "MAINTENANCE" ? "Marcar como realizado" : "Marcar como renovado"}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
