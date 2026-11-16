"use client";

import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatShortDay, parseDay, toISODay, today, urgency } from "@/lib/deadlines";
import type { Deadline } from "@/lib/types";
import { cn } from "@/lib/utils";

import { URGENCY_STYLE } from "./badges";

const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const monthFmt = new Intl.DateTimeFormat("es-CO", { month: "long", year: "numeric" });
const MAX_PER_DAY = 3;

function chipClass(d: Deadline) {
  if (d.status === "PENDING_REVIEW") return "border-dashed border-warning/60 bg-card text-warning";
  if (d.status === "DONE") return "border-transparent bg-muted text-muted-foreground line-through";
  return URGENCY_STYLE[urgency(d.due_date)];
}

export function DeadlineCalendar({ deadlines, onSelect }: { deadlines: Deadline[]; onSelect: (d: Deadline) => void }) {
  const now = today();
  const [month, setMonth] = useState(() => new Date(now.getFullYear(), now.getMonth(), 1));

  const byDay = useMemo(() => {
    const map = new Map<string, Deadline[]>();
    for (const d of deadlines) map.set(d.due_date, [...(map.get(d.due_date) ?? []), d]);
    return map;
  }, [deadlines]);

  // Cuadrícula de 6 semanas empezando en lunes
  const cells = useMemo(() => {
    const offset = (month.getDay() + 6) % 7;
    const start = new Date(month.getFullYear(), month.getMonth(), 1 - offset);
    return Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
  }, [month]);

  const monthEnd = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const inMonth = deadlines.filter((d) => {
    const day = parseDay(d.due_date);
    return day >= month && day <= monthEnd;
  });
  // Atajo útil: si el mes visible está vacío, ofrecer saltar al próximo vencimiento
  const nextUpcoming = deadlines
    .filter((d) => d.status !== "DONE" && parseDay(d.due_date) > monthEnd)
    .sort((a, b) => a.due_date.localeCompare(b.due_date))[0];

  const shift = (n: number) => setMonth((m) => new Date(m.getFullYear(), m.getMonth() + n, 1));
  const title = monthFmt.format(month);

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
        <h3 className="font-medium first-letter:uppercase">{title}</h3>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" onClick={() => setMonth(new Date(now.getFullYear(), now.getMonth(), 1))}>
            Hoy
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={() => shift(-1)} aria-label="Mes anterior">
            <ChevronLeft />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={() => shift(1)} aria-label="Mes siguiente">
            <ChevronRight />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-7 border-b bg-muted/50 text-center text-xs font-medium text-muted-foreground">
        {WEEKDAYS.map((w) => (
          <div key={w} className="py-1.5">
            {w}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7">
        {cells.map((day, i) => {
          const iso = toISODay(day);
          const items = byDay.get(iso) ?? [];
          const outside = day.getMonth() !== month.getMonth();
          const isToday = iso === toISODay(now);
          return (
            <div
              key={iso}
              className={cn(
                "min-h-24 border-b p-1.5",
                i % 7 !== 6 && "border-r",
                outside && "bg-muted/30",
                i >= 35 && "border-b-0",
              )}
            >
              <div
                className={cn(
                  "mb-1 flex size-6 items-center justify-center rounded-full text-xs",
                  outside ? "text-muted-foreground/60" : "text-muted-foreground",
                  isToday && "bg-primary font-semibold text-primary-foreground",
                )}
              >
                {day.getDate()}
              </div>
              <div className="space-y-1">
                {items.slice(0, MAX_PER_DAY).map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => onSelect(d)}
                    title={d.title}
                    className={cn(
                      "block w-full truncate rounded border px-1.5 py-0.5 text-left text-[11px] leading-tight font-medium transition-opacity hover:opacity-80",
                      chipClass(d),
                    )}
                  >
                    {d.title}
                  </button>
                ))}
                {items.length > MAX_PER_DAY && (
                  <p className="px-1 text-[11px] text-muted-foreground">+{items.length - MAX_PER_DAY} más</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-2.5 text-xs text-muted-foreground">
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm border border-destructive/40 bg-destructive/15" /> Vencido o ≤ 7 días
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm border border-warning/40 bg-warning-soft" /> ≤ 30 días
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm border border-dashed border-warning/60" /> Por revisar
          </span>
        </div>
        {inMonth.length === 0 && nextUpcoming && (
          <button
            type="button"
            onClick={() => {
              const d = parseDay(nextUpcoming.due_date);
              setMonth(new Date(d.getFullYear(), d.getMonth(), 1));
            }}
            className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
          >
            Próximo vencimiento: {formatShortDay(nextUpcoming.due_date)} <ArrowRight className="size-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
