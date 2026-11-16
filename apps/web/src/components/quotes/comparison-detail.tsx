"use client";

import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Award,
  Check,
  ChevronDown,
  FileText,
  Lightbulb,
  Loader2,
  Minus,
  MoreHorizontal,
  RotateCcw,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { usePdfViewer } from "@/components/pdf-viewer/viewer-context";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, fetcher } from "@/lib/api";
import { formatDate } from "@/lib/labels";
import { formatCOP, isRunning, PROGRESS_STEPS } from "@/lib/quotes";
import type { Comparison, QuoteRecord, Sourced } from "@/lib/types";
import { cn } from "@/lib/utils";

type Doc = Comparison["documents"][number] & { extracted: QuoteRecord };

// -- Celda con trazabilidad -----------------------------------------------------
function SourceLink({ doc, field }: { doc: Doc; field: Sourced }) {
  const { open } = usePdfViewer();
  if (!field.page) return null;
  return (
    <button
      type="button"
      onClick={() =>
        open({
          documentId: doc.document_id,
          title: doc.document_title,
          page: field.page ?? 1,
          highlight: field.quote ?? undefined,
        })
      }
      className="inline-flex items-center gap-0.5 rounded px-1 text-[11px] font-medium text-primary hover:bg-accent"
      aria-label={`Ver en ${doc.document_title}, página ${field.page}`}
    >
      <FileText className="size-3" />
      pág. {field.page}
    </button>
  );
}

function Flags({ field }: { field: Sourced }) {
  if (field.value === null || field.value === "") return null;
  if (field.computed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="cursor-help rounded bg-secondary px-1 text-[11px] text-muted-foreground">calculado</span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          {field.rate
            ? `El documento indica "IVA del ${field.rate}%" sin escribir la cifra; se calculó y se comprobó.`
            : "El documento no escribe el total: se calculó como subtotal + IVA y se comprobó la suma."}
        </TooltipContent>
      </Tooltip>
    );
  }
  if (!field.verified) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex cursor-help items-center gap-0.5 rounded bg-warning-soft px-1 text-[11px] font-medium text-warning">
            <AlertTriangle className="size-3" /> verificar
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          Este dato no se encontró escrito literalmente en la cotización. Revíselo en el documento antes de decidir.
        </TooltipContent>
      </Tooltip>
    );
  }
  return null;
}

function TextCell({ doc, field, extra }: { doc: Doc; field: Sourced; extra?: string | null }) {
  if (!field.value) return <span className="text-muted-foreground">No indicado</span>;
  return (
    <div>
      <p className="leading-snug">{String(field.value)}</p>
      {extra && <p className="mt-0.5 text-xs text-muted-foreground">{extra}</p>}
      <div className="mt-1 flex flex-wrap items-center gap-1">
        <SourceLink doc={doc} field={field} />
        <Flags field={field} />
      </div>
    </div>
  );
}

function MoneyCell({ doc, field, big }: { doc: Doc; field: Sourced; big?: boolean }) {
  if (field.value === null) return <span className="text-muted-foreground">No indicado</span>;
  return (
    <div>
      <p className={cn("tabular-nums", big ? "text-lg font-semibold tracking-tight" : "")}>{formatCOP(field.value)}</p>
      <div className="mt-1 flex flex-wrap items-center gap-1">
        <SourceLink doc={doc} field={field} />
        <Flags field={field} />
      </div>
    </div>
  );
}

function BestBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-success/25 bg-success-soft px-2 py-0.5 text-[11px] font-medium text-success">
      <Award className="size-3" />
      {children}
    </span>
  );
}

// -- Progreso -----------------------------------------------------------------------
function Progress({ progress }: { progress: string | null }) {
  const current = PROGRESS_STEPS.findIndex((s) => s.key === progress);
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <Loader2 className="mx-auto size-8 animate-spin text-primary" />
      <h2 className="mt-4 font-semibold">Analizando las cotizaciones…</h2>
      <p className="mt-1 text-sm text-muted-foreground">Suele tardar menos de un minuto. Puede salir de esta página.</p>
      <ol className="mt-8 space-y-2 text-left">
        {PROGRESS_STEPS.map((step, i) => (
          <li key={step.key} className="flex items-center gap-3 text-sm">
            <span
              className={cn(
                "flex size-6 items-center justify-center rounded-full border text-xs",
                i < current && "border-success bg-success-soft text-success",
                i === current && "border-primary text-primary",
                i > current && "text-muted-foreground",
              )}
            >
              {i < current ? <Check className="size-3.5" /> : i === current ? <Loader2 className="size-3.5 animate-spin" /> : i + 1}
            </span>
            <span className={i > current ? "text-muted-foreground" : ""}>{step.label}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

// -- Vista principal -----------------------------------------------------------------
export function ComparisonDetail({ id }: { id: string }) {
  const { tenant } = useTenant();
  const router = useRouter();
  const viewer = usePdfViewer();
  const key = `/tenants/${tenant.tenant_id}/quote-comparisons/${id}`;
  const { data, error, mutate } = useSWR<Comparison>(key, fetcher, {
    refreshInterval: (c) => (c && isRunning(c.status) ? 2500 : 0),
  });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showItems, setShowItems] = useState(false);
  const back = `/${tenant.tenant_slug}/quotes`;

  async function retry() {
    try {
      await api(`${key}/retry`, { method: "POST" });
      void mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  async function remove() {
    try {
      await api(key, { method: "DELETE" });
      toast.success("Comparación eliminada.");
      router.push(back);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const header = (
    <PageHeader
      title={data?.title ?? "Comparación"}
      description={data ? `${data.documents.length} cotizaciones · creada el ${formatDate(data.created_at)}` : undefined}
      actions={
        <>
          <Button variant="outline" asChild>
            <Link href={back}>
              <ArrowLeft /> <span className="hidden sm:inline">Todas</span>
            </Link>
          </Button>
          {data && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Más acciones">
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem disabled={isRunning(data.status)} onSelect={() => void retry()}>
                  <RotateCcw /> Volver a analizar
                </DropdownMenuItem>
                <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
                  <Trash2 /> Eliminar comparación
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </>
      }
    />
  );

  const deleteDialog = (
    <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Eliminar esta comparación?</AlertDialogTitle>
          <AlertDialogDescription>
            Se borra el análisis. Las cotizaciones siguen disponibles en Documentos.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction className="bg-destructive text-white hover:bg-destructive/90" onClick={() => void remove()}>
            Eliminar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  if (error) {
    return (
      <div className="flex flex-1 flex-col">
        {header}
        <p className="p-6 text-sm text-destructive">{(error as Error).message}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex flex-1 flex-col">
        {header}
        <div className="space-y-4 p-6">
          <Skeleton className="h-32" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }
  if (isRunning(data.status)) {
    return (
      <div className="flex flex-1 flex-col">
        {header}
        <Progress progress={data.progress} />
        {deleteDialog}
      </div>
    );
  }
  if (data.status === "FAILED" || !data.analysis) {
    return (
      <div className="flex flex-1 flex-col">
        {header}
        <div className="mx-auto mt-12 max-w-md rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
          <AlertCircle className="mx-auto size-6 text-destructive" />
          <p className="mt-3 font-medium">No se pudo completar el análisis</p>
          <p className="mt-1 text-sm text-muted-foreground">{data.error ?? "Error desconocido"}</p>
          <Button className="mt-4" onClick={() => void retry()}>
            <RotateCcw /> Volver a intentar
          </Button>
        </div>
        {deleteDialog}
      </div>
    );
  }

  const docs = data.documents.filter((d): d is Doc => Boolean(d.extracted));
  const best = data.best;
  const analysis = data.analysis;
  const assessmentFor = (name: string) =>
    analysis.assessments.find((a) => a.provider_name.toLowerCase() === name.toLowerCase()) ??
    analysis.assessments.find((a) => name.toLowerCase().includes(a.provider_name.toLowerCase().slice(0, 8)));

  const rows: { label: string; hint?: string; render: (d: Doc) => React.ReactNode; highlight?: (d: Doc) => boolean }[] = [
    {
      label: "Valor total",
      hint: "Con IVA",
      highlight: (d) => best?.total === d.document_id,
      render: (d) => {
        const total = Number(d.extracted.total.value);
        const diff = best?.min_total && total ? total - best.min_total : 0;
        return (
          <div>
            <MoneyCell doc={d} field={d.extracted.total} big />
            {diff > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                +{formatCOP(diff)} ({Math.round((diff / best!.min_total!) * 100)} %) sobre la más económica
              </p>
            )}
          </div>
        );
      },
    },
    { label: "Valor antes de IVA", render: (d) => <MoneyCell doc={d} field={d.extracted.subtotal} /> },
    { label: "IVA", render: (d) => <MoneyCell doc={d} field={d.extracted.tax} /> },
    {
      label: "Garantía",
      highlight: (d) => best?.warranty === d.document_id,
      render: (d) => <TextCell doc={d} field={d.extracted.warranty} />,
    },
    {
      label: "Plazo de ejecución",
      highlight: (d) => best?.delivery === d.document_id,
      render: (d) => (
        <TextCell
          doc={d}
          field={d.extracted.delivery}
          extra={
            d.extracted.delivery_business_days && d.extracted.delivery_days
              ? `≈ ${Math.round((d.extracted.delivery_days * 7) / 5)} días calendario`
              : null
          }
        />
      ),
    },
    { label: "Forma de pago", render: (d) => <TextCell doc={d} field={d.extracted.payment_terms} /> },
    { label: "Validez de la oferta", render: (d) => <TextCell doc={d} field={d.extracted.valid_until} /> },
    {
      label: "Incluye",
      render: (d) =>
        d.extracted.includes.length ? (
          <ul className="space-y-0.5">
            {d.extracted.includes.map((s) => (
              <li key={s} className="flex gap-1.5 text-sm">
                <Check className="mt-0.5 size-3.5 shrink-0 text-success" /> {s}
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-muted-foreground">No detallado</span>
        ),
    },
    {
      label: "No incluye",
      render: (d) =>
        d.extracted.excludes.length ? (
          <ul className="space-y-0.5">
            {d.extracted.excludes.map((s) => (
              <li key={s} className="flex gap-1.5 text-sm text-destructive">
                <Minus className="mt-0.5 size-3.5 shrink-0" /> {s}
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-muted-foreground">Sin exclusiones indicadas</span>
        ),
    },
  ];

  return (
    <div className="flex flex-1 flex-col">
      {header}
      <div className="space-y-6 p-6">
        {/* Conclusión primero: es lo que el consejo necesita */}
        <section className="rounded-lg border bg-card p-5">
          <h2 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Conclusión</h2>
          <p className="mt-2 leading-relaxed">{analysis.summary}</p>
          <div className="mt-4 flex gap-3 rounded-md border border-primary/15 bg-info-soft p-4">
            <Lightbulb className="mt-0.5 size-5 shrink-0 text-primary" />
            <div>
              <p className="text-sm font-medium text-primary">Sugerencia para el consejo</p>
              <p className="mt-1 text-sm leading-relaxed">{analysis.recommendation}</p>
            </div>
          </div>
          {analysis.comparability_warnings.length > 0 && (
            <div className="mt-3 rounded-md border border-warning/25 bg-warning-soft p-4">
              <p className="flex items-center gap-2 text-sm font-medium text-warning">
                <AlertTriangle className="size-4" /> Antes de comparar solo por precio
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                {analysis.comparability_warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* Tabla comparativa */}
        <section className="overflow-hidden rounded-lg border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="sticky left-0 z-10 w-44 bg-muted/50 p-4 text-left text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Criterio
                  </th>
                  {docs.map((d) => (
                    <th key={d.document_id} className="min-w-56 p-4 text-left align-top font-normal">
                      <p className="font-semibold">{d.extracted.provider_name}</p>
                      {d.extracted.provider_tax_id && (
                        <p className="text-xs text-muted-foreground">NIT {d.extracted.provider_tax_id}</p>
                      )}
                      <div className="mt-2 flex flex-wrap gap-1">
                        {best?.total === d.document_id && <BestBadge>Mejor precio</BestBadge>}
                        {best?.warranty === d.document_id && <BestBadge>Mayor garantía</BestBadge>}
                        {best?.delivery === d.document_id && <BestBadge>Más rápida</BestBadge>}
                      </div>
                      <button
                        type="button"
                        onClick={() => viewer.open({ documentId: d.document_id, title: d.document_title, page: 1 })}
                        className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                      >
                        <FileText className="size-3.5" /> Ver cotización
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.label} className="border-b last:border-b-0">
                    <th className="sticky left-0 z-10 bg-card p-4 text-left align-top font-medium">
                      {row.label}
                      {row.hint && <span className="block text-xs font-normal text-muted-foreground">{row.hint}</span>}
                    </th>
                    {docs.map((d) => (
                      <td
                        key={d.document_id}
                        className={cn("p-4 align-top", row.highlight?.(d) && "bg-success-soft/60")}
                      >
                        {row.render(d)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Fortalezas y debilidades */}
        <section>
          <h2 className="font-semibold">Evaluación por proveedor</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {docs.map((d) => {
              const a = assessmentFor(d.extracted.provider_name);
              return (
                <div key={d.document_id} className="rounded-lg border bg-card p-4">
                  <p className="font-medium">{d.extracted.provider_name}</p>
                  <p className="text-sm text-muted-foreground tabular-nums">{formatCOP(d.extracted.total.value)}</p>
                  {a ? (
                    <div className="mt-3 space-y-3 text-sm">
                      <ul className="space-y-1">
                        {a.strengths.map((s) => (
                          <li key={s} className="flex gap-2">
                            <Check className="mt-0.5 size-4 shrink-0 text-success" /> {s}
                          </li>
                        ))}
                      </ul>
                      <ul className="space-y-1">
                        {a.weaknesses.map((s) => (
                          <li key={s} className="flex gap-2 text-muted-foreground">
                            <Minus className="mt-0.5 size-4 shrink-0 text-warning" /> {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-muted-foreground">Sin evaluación.</p>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* Ítems */}
        {docs.some((d) => d.extracted.items.length > 1) && (
          <section>
            <button
              type="button"
              onClick={() => setShowItems((v) => !v)}
              className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
              aria-expanded={showItems}
            >
              <ChevronDown className={cn("size-4 transition-transform", showItems && "rotate-180")} />
              Detalle de ítems cotizados
            </button>
            {showItems && (
              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {docs.map((d) => (
                  <div key={d.document_id} className="rounded-lg border bg-card p-4">
                    <p className="font-medium">{d.extracted.provider_name}</p>
                    <ul className="mt-2 divide-y text-sm">
                      {d.extracted.items.map((item, i) => (
                        <li key={i} className="flex justify-between gap-3 py-1.5">
                          <span>{item.description}</span>
                          <span className="shrink-0 tabular-nums">{formatCOP(item.total)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        <p className="border-t pt-4 text-xs text-muted-foreground">
          Análisis generado automáticamente a partir de las cotizaciones. Cada dato enlaza a la página de donde se tomó; los
          marcados como «verificar» deben revisarse en el documento. La decisión final corresponde al consejo de
          administración.
        </p>
      </div>
      {deleteDialog}
    </div>
  );
}
