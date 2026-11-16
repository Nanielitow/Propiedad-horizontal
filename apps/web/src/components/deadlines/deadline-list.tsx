"use client";

import { CheckCheck, ChevronDown, Repeat } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { daysUntil, formatShortDay, parseDay, recurrenceLabel } from "@/lib/deadlines";
import type { Deadline } from "@/lib/types";
import { cn } from "@/lib/utils";

import { TypeBadge, UrgencyBadge } from "./badges";

const GROUPS = [
  { key: "overdue", title: "Vencidos", test: (d: number) => d < 0 },
  { key: "month", title: "Próximos 30 días", test: (d: number) => d >= 0 && d <= 30 },
  { key: "quarter", title: "Entre 1 y 3 meses", test: (d: number) => d > 30 && d <= 90 },
  { key: "later", title: "Más adelante", test: (d: number) => d > 90 },
];

const monthShort = new Intl.DateTimeFormat("es-CO", { month: "short" });

function Row({
  d,
  onSelect,
  onComplete,
}: {
  d: Deadline;
  onSelect: (d: Deadline) => void;
  onComplete?: (d: Deadline) => void;
}) {
  const date = parseDay(d.due_date);
  const recurrence = recurrenceLabel(d.recurrence_months);
  return (
    <li>
      <div
        role="button"
        tabIndex={0}
        onClick={() => onSelect(d)}
        onKeyDown={(e) => e.key === "Enter" && onSelect(d)}
        className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none"
      >
        <div className="flex w-12 shrink-0 flex-col items-center rounded-md border bg-card py-1">
          <span className="text-[10px] font-medium text-muted-foreground uppercase">{monthShort.format(date).replace(".", "")}</span>
          <span className="text-lg leading-none font-semibold">{date.getDate()}</span>
          <span className="text-[10px] text-muted-foreground">{date.getFullYear()}</span>
        </div>
        <div className="min-w-0 flex-1">
          <p className={cn("truncate font-medium", d.status === "DONE" && "text-muted-foreground line-through")}>
            {d.title}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <TypeBadge type={d.type} />
            {d.provider_name && <span className="truncate">{d.provider_name}</span>}
            {recurrence && (
              <span className="inline-flex items-center gap-1">
                <Repeat className="size-3" /> {recurrence}
              </span>
            )}
          </p>
        </div>
        {d.status === "DONE" ? (
          <span className="text-xs text-muted-foreground">{formatShortDay(d.due_date)}</span>
        ) : (
          <UrgencyBadge due={d.due_date} className="hidden sm:inline-flex" />
        )}
        {onComplete && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  onComplete(d);
                }}
                aria-label={d.type === "MAINTENANCE" ? "Marcar como realizado" : "Marcar como renovado"}
              >
                <CheckCheck />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{d.type === "MAINTENANCE" ? "Marcar como realizado" : "Marcar como renovado"}</TooltipContent>
          </Tooltip>
        )}
      </div>
    </li>
  );
}

export function DeadlineList({
  active,
  done,
  onSelect,
  onComplete,
}: {
  active: Deadline[];
  done: Deadline[];
  onSelect: (d: Deadline) => void;
  onComplete: (d: Deadline) => void;
}) {
  const [showDone, setShowDone] = useState(false);

  return (
    <div className="space-y-4">
      {active.length === 0 && (
        <p className="rounded-lg border border-dashed bg-card px-4 py-8 text-center text-sm text-muted-foreground">
          No hay vencimientos confirmados. Confirme las fechas pendientes de revisión para empezar a recibir avisos.
        </p>
      )}
      {GROUPS.map((group) => {
        const items = active.filter((d) => group.test(daysUntil(d.due_date)));
        if (!items.length) return null;
        return (
          <section key={group.key} className="overflow-hidden rounded-lg border bg-card">
            <h3
              className={cn(
                "border-b bg-muted/50 px-4 py-2 text-xs font-medium tracking-wide uppercase",
                group.key === "overdue" ? "text-destructive" : "text-muted-foreground",
              )}
            >
              {group.title} · {items.length}
            </h3>
            <ul className="divide-y">
              {items.map((d) => (
                <Row key={d.id} d={d} onSelect={onSelect} onComplete={onComplete} />
              ))}
            </ul>
          </section>
        );
      })}

      {done.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowDone((v) => !v)}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            aria-expanded={showDone}
          >
            <ChevronDown className={cn("size-4 transition-transform", showDone && "rotate-180")} />
            Realizados o renovados ({done.length})
          </button>
          {showDone && (
            <ul className="mt-2 divide-y overflow-hidden rounded-lg border bg-card">
              {done.map((d) => (
                <Row key={d.id} d={d} onSelect={onSelect} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
