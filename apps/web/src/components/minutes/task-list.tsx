"use client";

import { CalendarDays, FileText, UserRound } from "lucide-react";
import Link from "next/link";

import { useTenant } from "@/components/layout/tenant-context";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { daysUntil, formatShortDay } from "@/lib/deadlines";
import type { MinutesTask, TaskStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export const TASK_STATUS: Record<TaskStatus, string> = {
  OPEN: "Pendiente",
  IN_PROGRESS: "En curso",
  DONE: "Hecha",
};

function DueLabel({ task }: { task: MinutesTask }) {
  if (!task.due_date) return <span className="text-muted-foreground">Sin fecha límite</span>;
  const days = daysUntil(task.due_date);
  const late = task.status !== "DONE" && days < 0;
  return (
    <span className={cn(late ? "font-medium text-destructive" : "text-muted-foreground")}>
      {formatShortDay(task.due_date)}
      {late && ` · vencida hace ${-days} días`}
      {!late && task.status !== "DONE" && days >= 0 && days <= 7 && ` · en ${days} días`}
    </span>
  );
}

export function TaskList({
  tasks,
  onStatus,
  showActa = true,
}: {
  tasks: MinutesTask[];
  onStatus: (task: MinutesTask, status: TaskStatus) => void;
  showActa?: boolean;
}) {
  const { tenant } = useTenant();
  if (!tasks.length) {
    return (
      <p className="rounded-lg border border-dashed bg-card px-4 py-6 text-center text-sm text-muted-foreground">
        No hay compromisos registrados.
      </p>
    );
  }
  return (
    <ul className="divide-y overflow-hidden rounded-lg border bg-card">
      {tasks.map((t) => (
        <li key={t.id} className={cn("flex flex-wrap items-center gap-3 px-4 py-3", t.status === "DONE" && "bg-muted/30")}>
          <div className="min-w-0 flex-1">
            <p className={cn("text-sm font-medium", t.status === "DONE" && "text-muted-foreground line-through")}>
              {t.description}
            </p>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              <span className="inline-flex items-center gap-1 text-muted-foreground">
                <UserRound className="size-3.5" /> {t.assignee ?? "Sin responsable"}
              </span>
              <span className="inline-flex items-center gap-1">
                <CalendarDays className="size-3.5 text-muted-foreground" /> <DueLabel task={t} />
              </span>
              {showActa && (
                <Link
                  href={`/${tenant.tenant_slug}/minutes/${t.document_id}`}
                  className="inline-flex items-center gap-1 text-primary hover:underline"
                >
                  <FileText className="size-3.5" /> {t.document_title}
                </Link>
              )}
            </p>
          </div>
          <Select value={t.status} onValueChange={(v) => onStatus(t, v as TaskStatus)}>
            <SelectTrigger className="h-8 w-32" aria-label={`Estado de: ${t.description}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(TASK_STATUS) as TaskStatus[]).map((s) => (
                <SelectItem key={s} value={s}>
                  {TASK_STATUS[s]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </li>
      ))}
    </ul>
  );
}
