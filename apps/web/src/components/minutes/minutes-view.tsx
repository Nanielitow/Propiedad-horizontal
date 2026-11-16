"use client";

import { AlertCircle, ChevronRight, ClipboardList, Loader2, Lock, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { UploadDialog } from "@/components/documents/upload-dialog";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import { formatShortDay } from "@/lib/deadlines";
import type { Acta, MinutesTask, TaskStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

import { TaskList } from "./task-list";

export const ASSEMBLY_TYPE: Record<string, string> = {
  ORDINARIA: "Asamblea ordinaria",
  EXTRAORDINARIA: "Asamblea extraordinaria",
  CONSEJO: "Consejo de administración",
  OTRA: "Reunión",
};

export function useTasks(tenantId: string, enabled: boolean) {
  const swr = useSWR<MinutesTask[]>(enabled ? `/tenants/${tenantId}/minutes/tasks` : null, fetcher);
  async function setStatus(task: MinutesTask, status: TaskStatus) {
    try {
      await api(`/tenants/${tenantId}/minutes/tasks/${task.id}`, { method: "PATCH", json: { status } });
      await swr.mutate();
      if (status === "DONE") toast.success("Tarea marcada como hecha.");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  return { ...swr, setStatus };
}

export function MinutesView() {
  const { tenant, isAdmin } = useTenant();
  const base = `/tenants/${tenant.tenant_id}/minutes`;
  const { data: actas, isLoading, mutate } = useSWR<Acta[]>(isAdmin ? base : null, fetcher, {
    refreshInterval: (items) => (items?.some((a) => a.status === "PROCESSING") ? 3000 : 0),
  });
  const tasks = useTasks(tenant.tenant_id, isAdmin);
  const [showDone, setShowDone] = useState(false);

  if (!isAdmin) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
        <Lock className="size-6 text-muted-foreground" />
        <p className="mt-3 font-medium">Sección exclusiva de la administración</p>
      </div>
    );
  }

  async function summarize(a: Acta) {
    try {
      await api(`${base}/${a.document_id}/summarize`, { method: "POST" });
      void mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const allTasks = tasks.data ?? [];
  const pending = allTasks.filter((t) => t.status !== "DONE");
  const done = allTasks.filter((t) => t.status === "DONE");

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Actas"
        description="Acuerdos, votaciones y compromisos de asambleas y del consejo, extraídos de cada acta."
        actions={
          <UploadDialog
            onUploaded={() => {
              void mutate();
              void tasks.mutate();
            }}
            defaultCategory="ACTAS"
            triggerLabel="Subir acta"
          />
        }
      />

      <div className="space-y-8 p-6">
        <section>
          <div className="mb-3 flex items-end justify-between gap-2">
            <div>
              <h2 className="font-semibold">Compromisos pendientes ({pending.length})</h2>
              <p className="text-sm text-muted-foreground">Tareas asignadas en las actas, para hacerles seguimiento.</p>
            </div>
            {done.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => setShowDone((v) => !v)}>
                {showDone ? "Ocultar" : "Ver"} hechas ({done.length})
              </Button>
            )}
          </div>
          {tasks.isLoading ? (
            <Skeleton className="h-24" />
          ) : (
            <TaskList tasks={showDone ? allTasks : pending} onStatus={(t, s) => void tasks.setStatus(t, s)} />
          )}
        </section>

        <section>
          <h2 className="mb-3 font-semibold">Actas ({actas?.length ?? 0})</h2>
          {isLoading ? (
            <Skeleton className="h-40" />
          ) : !actas?.length ? (
            <div className="rounded-lg border border-dashed bg-card px-6 py-10 text-center">
              <ClipboardList className="mx-auto size-6 text-muted-foreground" />
              <p className="mt-3 font-medium">Aún no hay actas</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Suba un acta (también escaneada) y el sistema extraerá automáticamente sus acuerdos, votaciones y tareas.
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {actas.map((a) => {
                const ready = a.status === "READY";
                const content = (
                  <>
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                      <ClipboardList className="size-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{a.title}</p>
                      <p className="mt-0.5 truncate text-sm text-muted-foreground">
                        {ready
                          ? [
                              a.assembly_type ? ASSEMBLY_TYPE[a.assembly_type] : null,
                              a.assembly_date ? formatShortDay(a.assembly_date) : null,
                              a.quorum_pct !== null ? `quórum ${a.quorum_pct.toLocaleString("es-CO")} %` : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")
                          : "Sin resumir"}
                      </p>
                    </div>
                    {ready && (
                      <div className="hidden gap-4 text-center text-xs text-muted-foreground sm:flex">
                        <span><span className="block text-base font-semibold text-foreground">{a.agreements}</span>acuerdos</span>
                        <span><span className="block text-base font-semibold text-foreground">{a.votes}</span>votaciones</span>
                        <span>
                          <span className={cn("block text-base font-semibold", a.open_tasks ? "text-warning" : "text-foreground")}>
                            {a.open_tasks}
                          </span>
                          pendientes
                        </span>
                      </div>
                    )}
                  </>
                );
                return (
                  <li key={a.document_id}>
                    {ready ? (
                      <Link
                        href={`/${tenant.tenant_slug}/minutes/${a.document_id}`}
                        className="group flex items-center gap-4 rounded-lg border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-accent/40"
                      >
                        {content}
                        <ChevronRight className="size-4 text-muted-foreground" />
                      </Link>
                    ) : (
                      <div className="flex items-center gap-4 rounded-lg border bg-card p-4">
                        {content}
                        {a.status === "PROCESSING" ? (
                          <span className="inline-flex items-center gap-1.5 text-sm text-primary">
                            <Loader2 className="size-4 animate-spin" /> Resumiendo…
                          </span>
                        ) : (
                          <div className="flex items-center gap-2">
                            {a.status === "FAILED" && (
                              <AlertCircle className="size-4 text-destructive" aria-label={a.error ?? "Error"} />
                            )}
                            <Button size="sm" onClick={() => void summarize(a)}>
                              <Sparkles /> {a.status === "FAILED" ? "Reintentar" : "Resumir"}
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
