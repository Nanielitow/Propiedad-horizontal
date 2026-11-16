"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { DeadlinePatch } from "@/hooks/use-deadlines";
import { DEADLINE_TYPE, RECURRENCE_OPTIONS, REMINDER_OPTIONS } from "@/lib/deadlines";
import type { Deadline, DeadlineType } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  deadline: Deadline | null;
  onClose: () => void;
  onSave: (patch: DeadlinePatch, confirm: boolean) => Promise<boolean>;
}

export function EditDeadlineDialog({ deadline, onClose, onSave }: Props) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState<DeadlineType>("OTHER");
  const [dueDate, setDueDate] = useState("");
  const [provider, setProvider] = useState("");
  const [recurrence, setRecurrence] = useState("none");
  const [reminders, setReminders] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!deadline) return;
    setTitle(deadline.title);
    setType(deadline.type);
    setDueDate(deadline.due_date);
    setProvider(deadline.provider_name ?? "");
    setRecurrence(deadline.recurrence_months ? String(deadline.recurrence_months) : "none");
    setReminders(deadline.reminder_days);
  }, [deadline]);

  const pending = deadline?.status === "PENDING_REVIEW";

  async function save(confirm: boolean) {
    setSaving(true);
    const ok = await onSave(
      {
        title: title.trim(),
        type,
        due_date: dueDate,
        provider_name: provider.trim() || null,
        recurrence_months: recurrence === "none" ? null : Number(recurrence),
        reminder_days: reminders,
        ...(confirm ? { status: "ACTIVE" as const } : {}),
      },
      confirm,
    );
    setSaving(false);
    if (ok) onClose();
  }

  return (
    <Dialog open={Boolean(deadline)} onOpenChange={(open) => !open && !saving && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Editar vencimiento</DialogTitle>
          <DialogDescription>Corrija cualquier dato que la detección automática haya interpretado mal.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="dl-title">Nombre</Label>
            <Input id="dl-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Tipo</Label>
              <Select value={type} onValueChange={(v) => setType(v as DeadlineType)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(DEADLINE_TYPE) as DeadlineType[]).map((t) => (
                    <SelectItem key={t} value={t}>
                      {DEADLINE_TYPE[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dl-date">Fecha</Label>
              <Input id="dl-date" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dl-provider">
              Proveedor <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Input
              id="dl-provider"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              placeholder="Aseguradora, contratista…"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Repetición</Label>
            <Select value={recurrence} onValueChange={setRecurrence}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RECURRENCE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Al marcarlo como realizado, se programa automáticamente la siguiente fecha.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>Avisar con anticipación</Label>
            <div className="flex flex-wrap gap-1.5">
              {REMINDER_OPTIONS.map((days) => {
                const active = reminders.includes(days);
                return (
                  <button
                    key={days}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setReminders((r) => (active ? r.filter((x) => x !== days) : [...r, days]))}
                    className={cn(
                      "rounded-md border px-2.5 py-1 text-xs transition-colors",
                      active ? "border-primary bg-accent font-medium text-primary" : "text-muted-foreground hover:bg-muted",
                    )}
                  >
                    {days === 1 ? "1 día" : `${days} días`}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            variant={pending ? "outline" : "default"}
            onClick={() => void save(false)}
            disabled={saving || !title.trim() || !dueDate}
          >
            Guardar
          </Button>
          {pending && (
            <Button onClick={() => void save(true)} disabled={saving || !title.trim() || !dueDate}>
              {saving && <Loader2 className="animate-spin" />}
              Guardar y confirmar
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
