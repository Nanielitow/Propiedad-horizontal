"use client";

import { Check, FileText, Loader2, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, fetcher } from "@/lib/api";
import { formatDate, isProcessing } from "@/lib/labels";
import type { Comparison, DocumentItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const MAX = 4;

export function NewComparisonDialog({ onCreated }: { onCreated: () => void }) {
  const { tenant } = useTenant();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const { data } = useSWR<DocumentItem[]>(
    open ? `/tenants/${tenant.tenant_id}/documents?category=COTIZACIONES&limit=200` : null,
    fetcher,
    { refreshInterval: (docs) => (docs?.some((d) => isProcessing(d.status)) ? 2000 : 0) },
  );
  const quotes = (data ?? []).filter((d) => d.status === "READY" || isProcessing(d.status));
  const ready = quotes.filter((d) => d.status === "READY");

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length < MAX ? [...s, id] : s));
  }

  async function create() {
    setCreating(true);
    try {
      const c = await api<Comparison>(`/tenants/${tenant.tenant_id}/quote-comparisons`, {
        method: "POST",
        json: { title: title.trim(), document_ids: selected },
      });
      onCreated();
      setOpen(false);
      router.push(`/${tenant.tenant_slug}/quotes/${c.id}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setTitle("");
          setSelected([]);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus /> Nueva comparación
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Nueva comparación</DialogTitle>
          <DialogDescription>
            Elija entre 2 y {MAX} cotizaciones del mismo servicio. Se extraerán precios, garantías, plazos y condiciones,
            y se preparará un análisis para el consejo.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="cmp-title">¿Qué se está cotizando?</Label>
            <Input
              id="cmp-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej.: Impermeabilización cubierta torre 2"
              maxLength={200}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>Cotizaciones</Label>
              <span className="text-xs text-muted-foreground">
                {selected.length} de {MAX} seleccionadas
              </span>
            </div>
            {!data ? (
              <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Cargando…
              </div>
            ) : quotes.length === 0 ? (
              <p className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
                No hay cotizaciones cargadas. Súbalas con el botón «Subir cotizaciones».
              </p>
            ) : (
              <ul className="max-h-64 space-y-1.5 overflow-y-auto">
                {quotes.map((d) => {
                  const isSelected = selected.includes(d.id);
                  const disabled = d.status !== "READY" || (!isSelected && selected.length >= MAX);
                  return (
                    <li key={d.id}>
                      <button
                        type="button"
                        role="checkbox"
                        aria-checked={isSelected}
                        disabled={disabled}
                        onClick={() => toggle(d.id)}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-md border px-3 py-2.5 text-left text-sm transition-colors",
                          isSelected ? "border-primary bg-accent" : "hover:bg-muted/50",
                          disabled && !isSelected && "opacity-50",
                        )}
                      >
                        <span
                          className={cn(
                            "flex size-4 shrink-0 items-center justify-center rounded border",
                            isSelected ? "border-primary bg-primary text-primary-foreground" : "border-input",
                          )}
                        >
                          {isSelected && <Check className="size-3" />}
                        </span>
                        <FileText className="size-4 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{d.title}</span>
                          <span className="text-xs text-muted-foreground">
                            {d.status === "READY" ? `Subida el ${formatDate(d.created_at)}` : "Procesándose…"}
                          </span>
                        </span>
                        {d.status !== "READY" && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            {data && ready.length < 2 && quotes.length > 0 && (
              <p className="text-xs text-muted-foreground">Se necesitan al menos dos cotizaciones disponibles.</p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancelar
          </Button>
          <Button onClick={create} disabled={creating || title.trim().length < 3 || selected.length < 2}>
            {creating && <Loader2 className="animate-spin" />}
            Comparar {selected.length >= 2 ? `${selected.length} cotizaciones` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
