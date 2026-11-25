"use client";

import { Download, Wallet } from "lucide-react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { baseCartera, type ConfigCartera, type EstadoCuenta, puedeCartera } from "@/lib/cartera";

import { PazYSalvoBoton } from "./comunes";
import { EstadoCuentaContenido } from "./estado-cuenta";

export function MiCarteraView() {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const permitido = puedeCartera(tenant.role, "miCartera");
  const { data, isLoading, mutate } = useSWR<EstadoCuenta[]>(permitido ? `${b}/mi-cartera` : null, fetcher);
  const { data: cfg } = useSWR<ConfigCartera | null>(permitido ? `${b}/config` : null, fetcher);

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Mi cuenta" description="Su estado de cuenta con la copropiedad: cuotas, pagos y saldo." />
      <div className="mx-auto w-full max-w-4xl space-y-8 p-4 sm:p-6">
        {isLoading ? (
          <Skeleton className="h-96" />
        ) : !data?.length ? (
          <div className="rounded-lg border bg-card">
            <Vacio icono={Wallet} titulo="Aún no hay cuenta para mostrar" texto="Su cuenta no está asociada a una unidad, o la copropiedad aún no factura por la plataforma." />
          </div>
        ) : (
          data.map((e) => (
            <section key={e.unidad_id} className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">Unidad {e.unidad}</h2>
                <div className="flex gap-2">
                  <Button variant="outline" asChild>
                    <a href={`/api/proxy${b}/unidades/${e.unidad_id}/estado-cuenta?formato=pdf`} download>
                      <Download className="size-4" /> PDF
                    </a>
                  </Button>
                  <PazYSalvoBoton tenantId={tenant.tenant_id} unidadId={e.unidad_id} alDia={e.al_dia} variante="default" />
                </div>
              </div>
              {cfg?.nota_cuenta_cobro && <p className="rounded-md border bg-card px-3 py-2 text-sm">{cfg.nota_cuenta_cobro}</p>}
              <EstadoCuentaContenido e={e} onCambio={() => void mutate()} />
            </section>
          ))
        )}
      </div>
    </div>
  );
}
