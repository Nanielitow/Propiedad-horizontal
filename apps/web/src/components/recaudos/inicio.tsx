"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useTenant } from "@/components/layout/tenant-context";
import { puede } from "@/lib/recaudos";

import { SinAcceso } from "./comunes";
import { DashboardView } from "./dashboard-view";

/** Entrada del módulo: el resumen para quien lo ve; recepción va directo a registrar. */
export function RecaudosInicio() {
  const { tenant } = useTenant();
  const router = useRouter();
  const verResumen = puede(tenant.role, "resumen");
  const registra = puede(tenant.role, "registrar");

  useEffect(() => {
    if (!verResumen && registra) router.replace(`/${tenant.tenant_slug}/recaudos/nuevo`);
  }, [verResumen, registra, router, tenant.tenant_slug]);

  if (verResumen) return <DashboardView />;
  return registra ? null : <SinAcceso />;
}
