"use client";

import {
  AlertTriangle,
  CalendarClock,
  CalendarDays,
  ClipboardCheck,
  List,
  Loader2,
  Lock,
  ScanSearch,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeadlines } from "@/hooks/use-deadlines";
import { daysUntil } from "@/lib/deadlines";
import type { Deadline } from "@/lib/types";
import { cn } from "@/lib/utils";

import { DeadlineCalendar } from "./deadline-calendar";
import { DeadlineList } from "./deadline-list";
import { DeadlineDetailDialog } from "./detail-dialog";
import { EditDeadlineDialog } from "./edit-dialog";
import { ReviewCard } from "./review-card";

function Stat({
  icon: Icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  hint: string;
  tone: "warning" | "danger" | "primary" | "success";
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{label}</p>
        <Icon
          className={cn(
            "size-4",
            tone === "warning" && "text-warning",
            tone === "danger" && "text-destructive",
            tone === "primary" && "text-primary",
            tone === "success" && "text-success",
          )}
        />
      </div>
      <p className={cn("mt-1 text-2xl font-semibold tracking-tight", tone === "danger" && value > 0 && "text-destructive")}>
        {value}
      </p>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

export function DeadlinesView() {
  const { tenant, isAdmin } = useTenant();
  const { data, isLoading, update, complete } = useDeadlines(tenant.tenant_id, isAdmin);
  const [view, setView] = useState<"list" | "calendar">("list");
  const [editing, setEditing] = useState<Deadline | null>(null);
  const [selected, setSelected] = useState<Deadline | null>(null);

  if (!isAdmin) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
        <Lock className="size-6 text-muted-foreground" />
        <p className="mt-3 font-medium">Sección exclusiva de la administración</p>
      </div>
    );
  }

  const all = data?.deadlines ?? [];
  const pending = all.filter((d) => d.status === "PENDING_REVIEW");
  const active = all.filter((d) => d.status === "ACTIVE");
  const done = all.filter((d) => d.status === "DONE").sort((a, b) => b.due_date.localeCompare(a.due_date));
  const overdue = active.filter((d) => daysUntil(d.due_date) < 0).length;
  const next30 = active.filter((d) => {
    const n = daysUntil(d.due_date);
    return n >= 0 && n <= 30;
  }).length;
  const analyzing = data?.analyzing ?? [];

  const confirm = (d: Deadline) => update(d.id, { status: "ACTIVE" }, "Vencimiento confirmado. Recibirá los avisos programados.");
  const dismiss = async (d: Deadline) => {
    const previous = d.status;
    if (await update(d.id, { status: "DISMISSED" }, null)) {
      toast("Vencimiento descartado", {
        action: { label: "Deshacer", onClick: () => void update(d.id, { status: previous }, "Restaurado.") },
      });
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Vencimientos"
        description="Pólizas, contratos y mantenimientos detectados automáticamente en sus documentos."
      />

      {/* @container: el diseño responde al espacio disponible (se reduce al abrir el visor PDF) */}
      <div className="@container space-y-6 p-6">
        {analyzing.length > 0 && (
          <div className="flex items-center gap-3 rounded-lg border border-primary/20 bg-info-soft px-4 py-3 text-sm text-primary">
            <Loader2 className="size-4 shrink-0 animate-spin" />
            <span>
              Buscando fechas en {analyzing.length === 1 ? "el documento" : `${analyzing.length} documentos`}:{" "}
              <span className="font-medium">{analyzing.map((a) => a.title).join(", ")}</span>. Los resultados aparecerán aquí
              en unos segundos.
            </span>
          </div>
        )}

        {isLoading ? (
          <div className="grid grid-cols-2 gap-3 @4xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : all.length === 0 && analyzing.length === 0 ? (
          /* Estado vacío: explica cómo funciona */
          <div className="mx-auto flex max-w-xl flex-col items-center py-12 text-center">
            <div className="flex size-12 items-center justify-center rounded-lg bg-accent text-primary">
              <ScanSearch className="size-6" />
            </div>
            <h2 className="mt-4 text-lg font-semibold">Aún no hay vencimientos</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Al subir pólizas, contratos, actas o certificados de mantenimiento, el sistema detecta automáticamente sus
              fechas de vencimiento y las deja aquí para que las revise.
            </p>
            <Button asChild className="mt-6">
              <Link href={`/${tenant.tenant_slug}/documents`}>Ir a Documentos</Link>
            </Button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 @4xl:grid-cols-4">
              <Stat icon={ClipboardCheck} label="Por revisar" value={pending.length} hint="Detectados, sin confirmar" tone="warning" />
              <Stat icon={AlertTriangle} label="Vencidos" value={overdue} hint="Requieren atención" tone="danger" />
              <Stat icon={CalendarClock} label="Próximos 30 días" value={next30} hint="Confirmados" tone="primary" />
              <Stat icon={ShieldCheck} label="Confirmados" value={active.length} hint="Con avisos activos" tone="success" />
            </div>

            {pending.length > 0 && (
              <section>
                <h2 className="font-semibold">Por revisar ({pending.length})</h2>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  Fechas encontradas automáticamente. Verifique cada una con su frase de origen y confírmela para activar
                  los avisos, o descártela si no aplica.
                </p>
                <div className="mt-3 grid gap-3 @3xl:grid-cols-2 @7xl:grid-cols-3">
                  {pending.map((d) => (
                    <ReviewCard
                      key={d.id}
                      deadline={d}
                      onConfirm={() => void confirm(d)}
                      onEdit={() => setEditing(d)}
                      onDismiss={() => void dismiss(d)}
                    />
                  ))}
                </div>
              </section>
            )}

            <section>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="font-semibold">Agenda de vencimientos</h2>
                  <p className="text-sm text-muted-foreground">Recibirá avisos 30, 15, 7 y 1 día antes de cada fecha confirmada.</p>
                </div>
                <div className="inline-flex rounded-md border bg-card p-0.5" role="tablist" aria-label="Vista">
                  {(
                    [
                      { key: "list", label: "Lista", icon: List },
                      { key: "calendar", label: "Calendario", icon: CalendarDays },
                    ] as const
                  ).map(({ key, label, icon: Icon }) => (
                    <button
                      key={key}
                      role="tab"
                      aria-selected={view === key}
                      onClick={() => setView(key)}
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded px-3 py-1 text-sm transition-colors",
                        view === key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      <Icon className="size-3.5" /> {label}
                    </button>
                  ))}
                </div>
              </div>
              {view === "list" ? (
                <DeadlineList active={active} done={done} onSelect={setSelected} onComplete={(d) => void complete(d)} />
              ) : (
                <DeadlineCalendar deadlines={[...pending, ...active, ...done]} onSelect={setSelected} />
              )}
            </section>
          </>
        )}
      </div>

      <DeadlineDetailDialog
        deadline={selected}
        onClose={() => setSelected(null)}
        onConfirm={(d) => void confirm(d)}
        onComplete={(d) => void complete(d)}
        onEdit={setEditing}
        onDismiss={(d) => void dismiss(d)}
      />
      <EditDeadlineDialog
        deadline={editing}
        onClose={() => setEditing(null)}
        onSave={(patch, andConfirm) =>
          update(editing!.id, patch, andConfirm ? "Guardado y confirmado." : "Cambios guardados.")
        }
      />
    </div>
  );
}
