"use client";

import { BellOff, CheckCircle2, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, fetcher } from "@/lib/api";
import { type Alerta, base, fechaHora, pesos, puede, SEVERIDAD, TIPO_ALERTA } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { Etiqueta, MotivoDialog, SinAcceso, Vacio } from "./comunes";

export function AlertasView() {
  const { tenant } = useTenant();
  const b = base(tenant.tenant_id);
  const permitido = puede(tenant.role, "alertas");
  const atiende = puede(tenant.role, "atender");
  const [vista, setVista] = useState<"abiertas" | "todas">("abiertas");
  const { data, mutate } = useSWR<Alerta[]>(permitido ? `${b}/alertas${vista === "todas" ? "?todas=true" : ""}` : null, fetcher);
  const [atendiendo, setAtendiendo] = useState<Alerta | null>(null);

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Alertas de auditoría"
        description="Diferencias de caja, descuadres, transferencias sin verificar y anulaciones de dinero ya consignado."
        actions={
          <div className="inline-flex rounded-md border bg-secondary/50 p-0.5" role="tablist">
            {(["abiertas", "todas"] as const).map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={vista === v}
                onClick={() => setVista(v)}
                className={cn("rounded px-3 py-1 text-sm capitalize", vista === v ? "bg-card font-medium shadow-sm" : "text-muted-foreground")}
              >
                {v}
              </button>
            ))}
          </div>
        }
      />

      <div className="p-4 sm:p-6">
        {!data ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : !data.length ? (
          <div className="rounded-lg border bg-card">
            <Vacio icono={BellOff} titulo={vista === "abiertas" ? "No hay alertas abiertas" : "Aún no se han generado alertas"} texto="Las alertas se crean solas cuando algo no cuadra." />
          </div>
        ) : (
          <ul className="space-y-2">
            {data.map((a) => (
              <li key={a.id} className={cn("rounded-lg border bg-card p-4", a.estado === "ATENDIDA" && "opacity-75")}>
                <div className="flex flex-wrap items-start gap-3">
                  <ShieldAlert className={cn("mt-0.5 size-5 shrink-0", a.severidad === "CRITICA" ? "text-destructive" : a.severidad === "ADVERTENCIA" ? "text-warning" : "text-muted-foreground")} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{TIPO_ALERTA[a.tipo]}</p>
                      <Etiqueta tono={SEVERIDAD[a.severidad].tono}>{SEVERIDAD[a.severidad].label}</Etiqueta>
                      {a.monto && <span className="text-sm font-medium tabular-nums">{pesos(a.monto)}</span>}
                    </div>
                    <p className="mt-1 text-sm">{a.mensaje}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{fechaHora(a.created_at)}</p>
                    {a.estado === "ATENDIDA" && (
                      <p className="mt-2 flex items-start gap-1.5 rounded-md bg-success-soft/60 px-2.5 py-1.5 text-xs">
                        <CheckCircle2 className="mt-px size-3.5 shrink-0 text-success" />
                        <span>
                          Atendida {a.atendida_at && fechaHora(a.atendida_at)}: {a.resolucion}
                        </span>
                      </p>
                    )}
                  </div>
                  {atiende && a.estado === "ABIERTA" && (
                    <Button size="sm" variant="outline" onClick={() => setAtendiendo(a)}>
                      Marcar como atendida
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <MotivoDialog
        abierto={atendiendo !== null}
        onCambio={(v) => !v && setAtendiendo(null)}
        titulo="Atender alerta"
        descripcion={atendiendo?.mensaje ?? ""}
        boton="Marcar como atendida"
        minimo={5}
        peligro={false}
        onConfirmar={async (resolucion) => {
          if (!atendiendo) return;
          await api(`${b}/alertas/${atendiendo.id}/atender`, { method: "POST", json: { resolucion } });
          toast.success("Alerta atendida");
          void mutate();
        }}
      />
    </div>
  );
}
