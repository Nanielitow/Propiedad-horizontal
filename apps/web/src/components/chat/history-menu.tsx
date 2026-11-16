"use client";

import { History, Loader2 } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { fetcher } from "@/lib/api";
import { formatDateTime } from "@/lib/labels";
import type { Conversation } from "@/lib/types";

export function HistoryMenu({
  tenantId,
  activeId,
  onSelect,
}: {
  tenantId: string;
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  // Solo se consulta al abrir el menú
  const { data, isLoading } = useSWR<Conversation[]>(
    open ? `/tenants/${tenantId}/conversations` : null,
    fetcher,
  );

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">
          <History /> <span className="hidden sm:inline">Historial</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel>Consultas recientes</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {isLoading && (
          <div className="flex items-center gap-2 px-2 py-3 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Cargando…
          </div>
        )}
        {data?.length === 0 && <p className="px-2 py-3 text-sm text-muted-foreground">Aún no tiene consultas.</p>}
        <div className="max-h-80 overflow-y-auto">
          {data?.map((c) => (
            <DropdownMenuItem key={c.id} onSelect={() => onSelect(c.id)} className="flex-col items-start gap-0.5">
              <span className={c.id === activeId ? "font-medium text-primary" : ""}>
                {c.title ?? "Consulta sin título"}
              </span>
              <span className="text-xs text-muted-foreground">{formatDateTime(c.created_at)}</span>
            </DropdownMenuItem>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
