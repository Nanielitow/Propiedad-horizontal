"use client";

import { toast } from "sonner";
import useSWR from "swr";

import { api, fetcher } from "@/lib/api";
import { formatShortDay } from "@/lib/deadlines";
import type { Deadline, DeadlinesResponse } from "@/lib/types";

export type DeadlinePatch = Partial<
  Pick<Deadline, "title" | "type" | "due_date" | "provider_name" | "recurrence_months" | "reminder_days" | "status">
>;

export const deadlinesKey = (tenantId: string) => `/tenants/${tenantId}/deadlines`;

/** Misma clave SWR que la barra lateral: confirmar aquí actualiza el contador allá. */
export function useDeadlines(tenantId: string, enabled = true) {
  const key = deadlinesKey(tenantId);
  const swr = useSWR<DeadlinesResponse>(enabled ? key : null, fetcher, {
    // Mientras el detector analiza documentos se consulta cada 3 s
    refreshInterval: (data) => (data?.analyzing.length ? 3000 : 60_000),
  });

  async function update(id: string, patch: DeadlinePatch, success: string | null) {
    try {
      await api(`${key}/${id}`, { method: "PATCH", json: patch });
      if (success) toast.success(success);
      await swr.mutate();
      return true;
    } catch (e) {
      toast.error((e as Error).message);
      return false;
    }
  }

  async function complete(d: Deadline) {
    try {
      const res = await api<{ next: Deadline | null }>(`${key}/${d.id}/complete`, { method: "POST" });
      toast.success(
        res.next ? `Registrado. Próxima fecha programada: ${formatShortDay(res.next.due_date)}` : "Marcado como realizado.",
      );
      await swr.mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return { ...swr, update, complete };
}
