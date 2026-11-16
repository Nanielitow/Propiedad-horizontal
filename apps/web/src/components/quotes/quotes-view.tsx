"use client";

import { AlertCircle, ChevronRight, FileUp, ListChecks, Loader2, Lock, Scale, Sparkles } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { UploadDialog } from "@/components/documents/upload-dialog";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { formatDate } from "@/lib/labels";
import { formatCOP, isRunning } from "@/lib/quotes";
import type { ComparisonSummary } from "@/lib/types";

import { NewComparisonDialog } from "./new-comparison-dialog";

const STEPS = [
  { icon: FileUp, title: "Suba las cotizaciones", text: "En PDF, incluso escaneadas. Quedan en la categoría Cotizaciones." },
  { icon: ListChecks, title: "Cree la comparación", text: "Elija de 2 a 4 propuestas del mismo servicio." },
  { icon: Sparkles, title: "Revise el resultado", text: "Tabla de precios, garantías y plazos con la página de cada dato." },
];

export function QuotesView() {
  const { tenant, isAdmin } = useTenant();
  const { data, isLoading, mutate } = useSWR<ComparisonSummary[]>(
    isAdmin ? `/tenants/${tenant.tenant_id}/quote-comparisons` : null,
    fetcher,
    { refreshInterval: (items) => (items?.some((c) => isRunning(c.status)) ? 3000 : 0) },
  );

  if (!isAdmin) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
        <Lock className="size-6 text-muted-foreground" />
        <p className="mt-3 font-medium">Sección exclusiva de la administración</p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Cotizaciones"
        description="Compare propuestas de proveedores de forma objetiva, con cada dato verificado en su documento."
        actions={
          <>
            <UploadDialog
              onUploaded={() => void mutate()}
              defaultCategory="COTIZACIONES"
              triggerLabel="Subir cotizaciones"
              triggerVariant="outline"
            />
            <NewComparisonDialog onCreated={() => void mutate()} />
          </>
        }
      />

      <div className="p-6">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : !data?.length ? (
          <div className="mx-auto max-w-2xl py-10 text-center">
            <div className="mx-auto flex size-12 items-center justify-center rounded-lg bg-accent text-primary">
              <Scale className="size-6" />
            </div>
            <h2 className="mt-4 text-lg font-semibold">Compare cotizaciones en tres pasos</h2>
            <div className="mt-8 grid gap-4 text-left sm:grid-cols-3">
              {STEPS.map(({ icon: Icon, title, text }, i) => (
                <div key={title} className="rounded-lg border bg-card p-4">
                  <div className="flex items-center gap-2">
                    <span className="flex size-6 items-center justify-center rounded-full bg-secondary text-xs font-semibold">
                      {i + 1}
                    </span>
                    <Icon className="size-4 text-muted-foreground" />
                  </div>
                  <p className="mt-3 text-sm font-medium">{title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{text}</p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <ul className="space-y-2">
            {data.map((c) => (
              <li key={c.id}>
                <Link
                  href={`/${tenant.tenant_slug}/quotes/${c.id}`}
                  className="group flex items-center gap-4 rounded-lg border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-accent/40"
                >
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                    <Scale className="size-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{c.title}</p>
                    <p className="mt-0.5 truncate text-sm text-muted-foreground">
                      {c.providers.length} cotizaciones · {c.providers.join(" · ")}
                    </p>
                  </div>
                  <div className="hidden text-right sm:block">
                    {isRunning(c.status) ? (
                      <span className="inline-flex items-center gap-1.5 text-sm text-primary">
                        <Loader2 className="size-4 animate-spin" /> Analizando…
                      </span>
                    ) : c.status === "FAILED" ? (
                      <span className="inline-flex items-center gap-1.5 text-sm text-destructive">
                        <AlertCircle className="size-4" /> Con error
                      </span>
                    ) : (
                      <>
                        <p className="text-sm">
                          Desde <span className="font-semibold">{formatCOP(c.min_total)}</span>
                        </p>
                        <p className="text-xs text-muted-foreground">{formatDate(c.created_at)}</p>
                      </>
                    )}
                  </div>
                  <ChevronRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
