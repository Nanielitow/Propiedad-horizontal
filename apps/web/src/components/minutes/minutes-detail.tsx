"use client";

import { AlertTriangle, ArrowLeft, Check, FileText, Loader2, RotateCcw, Users, X } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { usePdfViewer } from "@/components/pdf-viewer/viewer-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, fetcher } from "@/lib/api";
import { formatLongDay } from "@/lib/deadlines";
import type { MinutesDetail as Detail, TaskStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

import { ASSEMBLY_TYPE } from "./minutes-view";
import { TaskList } from "./task-list";
import { VoteBar, VoteLegend } from "./vote-bar";

function Unverified() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help items-center gap-0.5 rounded bg-warning-soft px-1 text-[11px] font-medium text-warning">
          <AlertTriangle className="size-3" /> verificar
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">No se encontró este texto o porcentaje literalmente en el acta.</TooltipContent>
    </Tooltip>
  );
}

function ResultBadge({ approved }: { approved: boolean | null }) {
  if (approved === null) return null;
  return approved ? (
    <span className="inline-flex items-center gap-1 rounded-full border border-success/25 bg-success-soft px-2 py-0.5 text-xs font-medium text-success">
      <Check className="size-3" /> Aprobado
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full border border-destructive/25 bg-destructive/5 px-2 py-0.5 text-xs font-medium text-destructive">
      <X className="size-3" /> Negado
    </span>
  );
}

export function MinutesDetail({ documentId }: { documentId: string }) {
  const { tenant } = useTenant();
  const { open } = usePdfViewer();
  const key = `/tenants/${tenant.tenant_id}/minutes/${documentId}`;
  const { data, mutate } = useSWR<Detail>(key, fetcher, {
    refreshInterval: (d) => (d?.status === "PROCESSING" ? 3000 : 0),
  });
  const back = `/${tenant.tenant_slug}/minutes`;

  const source = (page: number, quote: string) => () =>
    data && open({ documentId: data.document_id, title: data.title, page, highlight: quote });

  async function setStatus(taskId: string, status: TaskStatus) {
    try {
      await api(`/tenants/${tenant.tenant_id}/minutes/tasks/${taskId}`, { method: "PATCH", json: { status } });
      void mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function resummarize() {
    try {
      await api(`${key}/summarize`, { method: "POST" });
      void mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const header = (
    <PageHeader
      title={data?.title ?? "Acta"}
      description={
        data?.assembly_date
          ? `${data.assembly_type ? ASSEMBLY_TYPE[data.assembly_type] : "Reunión"} del ${formatLongDay(data.assembly_date)}`
          : undefined
      }
      actions={
        <>
          <Button variant="outline" asChild>
            <Link href={back}>
              <ArrowLeft /> <span className="hidden sm:inline">Todas las actas</span>
            </Link>
          </Button>
          {data && (
            <Button variant="outline" onClick={() => open({ documentId: data.document_id, title: data.title, page: 1 })}>
              <FileText /> <span className="hidden sm:inline">Ver acta</span>
            </Button>
          )}
        </>
      }
    />
  );

  if (!data) {
    return (
      <div className="flex flex-1 flex-col">
        {header}
        <div className="space-y-4 p-6">
          <Skeleton className="h-28" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (data.status !== "READY") {
    return (
      <div className="flex flex-1 flex-col">
        {header}
        <div className="mx-auto mt-16 max-w-sm text-center">
          {data.status === "PROCESSING" ? (
            <>
              <Loader2 className="mx-auto size-7 animate-spin text-primary" />
              <p className="mt-3 font-medium">Leyendo el acta…</p>
              <p className="mt-1 text-sm text-muted-foreground">Extrayendo acuerdos, votaciones y compromisos.</p>
            </>
          ) : (
            <>
              <p className="font-medium">{data.status === "FAILED" ? "No se pudo resumir el acta" : "Esta acta aún no se ha resumido"}</p>
              {data.error && <p className="mt-1 text-sm text-muted-foreground">{data.error}</p>}
              <Button className="mt-4" onClick={() => void resummarize()}>
                <RotateCcw /> Resumir ahora
              </Button>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      {header}
      <div className="@container space-y-6 p-6">
        {/* Datos clave + resumen */}
        <section className="rounded-lg border bg-card p-5">
          <div className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
            <div>
              <p className="text-xs text-muted-foreground">Tipo</p>
              <p className="font-medium">{data.assembly_type ? ASSEMBLY_TYPE[data.assembly_type] : "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Fecha</p>
              <p className="font-medium">{data.assembly_date ? formatLongDay(data.assembly_date) : "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Quórum</p>
              <p className="flex items-center gap-1.5 font-medium">
                <Users className="size-4 text-muted-foreground" />
                {data.quorum_pct !== null ? `${data.quorum_pct.toLocaleString("es-CO")} % de los coeficientes` : "No indicado"}
              </p>
            </div>
          </div>
          <p className="mt-4 border-t pt-4 leading-relaxed">{data.summary}</p>
        </section>

        <div className="grid gap-6 @4xl:grid-cols-2">
          {/* Votaciones */}
          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">Votaciones ({data.votes.length})</h2>
              {data.votes.length > 0 && <VoteLegend />}
            </div>
            {data.votes.length === 0 ? (
              <p className="rounded-lg border border-dashed bg-card px-4 py-6 text-center text-sm text-muted-foreground">
                El acta no registra votaciones con resultado.
              </p>
            ) : (
              <ul className="space-y-2">
                {data.votes.map((v, i) => (
                  <li key={i} className="rounded-lg border bg-card p-4">
                    <div className="mb-2.5 flex flex-wrap items-start justify-between gap-2">
                      <p className="text-sm font-medium">{v.topic}</p>
                      <div className="flex items-center gap-1.5">
                        {!v.verified && <Unverified />}
                        <ResultBadge approved={v.result === "SIN_DATO" ? null : v.result === "APROBADO"} />
                      </div>
                    </div>
                    <VoteBar vote={v} />
                    <button type="button" onClick={source(v.page, v.quote)} className="mt-2 text-xs font-medium text-primary hover:underline">
                      Ver en el acta · pág. {v.page}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Acuerdos */}
          <section>
            <h2 className="mb-3 font-semibold">Acuerdos ({data.agreements.length})</h2>
            <ul className="divide-y overflow-hidden rounded-lg border bg-card">
              {data.agreements.map((a, i) => (
                <li key={i} className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{a.topic}</p>
                    <ResultBadge approved={a.approved} />
                    {!a.verified && <Unverified />}
                  </div>
                  <p className="mt-1 text-sm">{a.decision}</p>
                  <button type="button" onClick={source(a.page, a.quote)} className="mt-1 text-xs font-medium text-primary hover:underline">
                    Ver en el acta · pág. {a.page}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>

        {/* Compromisos */}
        <section>
          <h2 className="font-semibold">Compromisos ({data.tasks.length})</h2>
          <p className="mb-3 text-sm text-muted-foreground">Actualice su estado a medida que se cumplen.</p>
          <TaskList tasks={data.tasks} showActa={false} onStatus={(t, s) => void setStatus(t.id, s)} />
        </section>

        <p className={cn("border-t pt-4 text-xs text-muted-foreground")}>
          Resumen generado automáticamente a partir del acta{data.model ? ` (${data.model})` : ""}. Cada acuerdo y votación
          enlaza a su página; el acta firmada es el documento oficial.
        </p>
      </div>
    </div>
  );
}
