"use client";

import { AlertCircle, CheckCircle2, FileText, Loader2, Lock, Upload, UploadCloud, Users, X } from "lucide-react";
import { useRef, useState } from "react";

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
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { ACCESS, CATEGORIES, CATEGORY_ORDER, formatBytes } from "@/lib/labels";
import type { AccessLevel, Category, UploadResponse } from "@/lib/types";
import { putWithProgress, sha256Hex } from "@/lib/upload";
import { cn } from "@/lib/utils";

const MAX_MB = 50;

type ItemState =
  | { phase: "pending" }
  | { phase: "hashing" }
  | { phase: "uploading"; percent: number }
  | { phase: "registering" }
  | { phase: "done" }
  | { phase: "error"; message: string };

interface Item {
  file: File;
  state: ItemState;
  invalid?: string;
}

function validate(file: File): string | undefined {
  if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) return "Solo se admiten archivos PDF";
  if (file.size > MAX_MB * 1024 * 1024) return `Supera el máximo de ${MAX_MB} MB`;
  return undefined;
}

interface UploadDialogProps {
  onUploaded: () => void;
  /** Categoría preseleccionada (p. ej. COTIZACIONES desde el comparador) */
  defaultCategory?: Category;
  triggerLabel?: string;
  triggerVariant?: "default" | "outline";
}

export function UploadDialog({
  onUploaded,
  defaultCategory,
  triggerLabel = "Subir documentos",
  triggerVariant = "default",
}: UploadDialogProps) {
  const { tenant } = useTenant();
  const initialAccess: AccessLevel = defaultCategory ? CATEGORIES[defaultCategory].defaultAccess : "ADMIN";
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Item[]>([]);
  const [category, setCategory] = useState<Category | "">(defaultCategory ?? "");
  const [access, setAccess] = useState<AccessLevel>(initialAccess);
  const [title, setTitle] = useState("");
  const [running, setRunning] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const started = items.some((i) => i.state.phase !== "pending");
  const finished = started && !running;
  const valid = items.filter((i) => !i.invalid);

  function reset() {
    setItems([]);
    setCategory(defaultCategory ?? "");
    setAccess(initialAccess);
    setTitle("");
  }

  function addFiles(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list).map((file) => ({ file, state: { phase: "pending" } as ItemState, invalid: validate(file) }));
    setItems((prev) => [...prev, ...incoming.filter((n) => !prev.some((p) => p.file.name === n.file.name && p.file.size === n.file.size))]);
  }

  const setState = (file: File, state: ItemState) =>
    setItems((prev) => prev.map((i) => (i.file === file ? { ...i, state } : i)));

  async function uploadOne(file: File) {
    const base = `/tenants/${tenant.tenant_id}/documents`;
    try {
      setState(file, { phase: "hashing" });
      const sha256 = await sha256Hex(file);
      const upload = await api<UploadResponse>(`${base}/uploads`, {
        method: "POST",
        json: {
          filename: file.name,
          size_bytes: file.size,
          sha256,
          category,
          access_level: access,
          title: valid.length === 1 && title.trim() ? title.trim() : undefined,
        },
      });
      setState(file, { phase: "uploading", percent: 0 });
      await putWithProgress(upload.upload_url, file, upload.headers, (percent) =>
        setState(file, { phase: "uploading", percent }),
      );
      setState(file, { phase: "registering" });
      await api(`${base}/${upload.document_id}/complete`, { method: "POST" });
      setState(file, { phase: "done" });
      onUploaded();
    } catch (e) {
      setState(file, { phase: "error", message: (e as Error).message });
    }
  }

  async function start() {
    setRunning(true);
    for (const item of valid) await uploadOne(item.file); // en serie: progreso claro y sin saturar la red
    setRunning(false);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (running) return; // no cerrar a mitad de una subida
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant={triggerVariant}>
          <Upload /> {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg" showCloseButton={!running}>
        <DialogHeader>
          <DialogTitle>Subir documentos</DialogTitle>
          <DialogDescription>
            Los archivos se procesan automáticamente (incluido el reconocimiento de texto en documentos escaneados) y
            quedan disponibles en el buscador en unos segundos.
          </DialogDescription>
        </DialogHeader>

        {!started ? (
          <div className="space-y-5">
            {/* Zona de arrastre */}
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                addFiles(e.dataTransfer.files);
              }}
              className={cn(
                "flex w-full flex-col items-center rounded-lg border-2 border-dashed px-4 py-7 text-center transition-colors",
                dragging ? "border-primary bg-accent" : "hover:border-primary/40 hover:bg-muted/50",
              )}
            >
              <UploadCloud className="size-7 text-muted-foreground" />
              <span className="mt-2 text-sm font-medium">Arrastre los PDF aquí o haga clic para elegirlos</span>
              <span className="mt-0.5 text-xs text-muted-foreground">Hasta {MAX_MB} MB por archivo</span>
            </button>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              hidden
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />

            {items.length > 0 && (
              <ul className="max-h-36 space-y-1.5 overflow-y-auto">
                {items.map((item) => (
                  <li key={item.file.name + item.file.size} className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-sm">
                    <FileText className={cn("size-4 shrink-0", item.invalid ? "text-destructive" : "text-muted-foreground")} />
                    <span className="min-w-0 flex-1 truncate">{item.file.name}</span>
                    <span className={cn("text-xs", item.invalid ? "text-destructive" : "text-muted-foreground")}>
                      {item.invalid ?? formatBytes(item.file.size)}
                    </span>
                    <button
                      type="button"
                      onClick={() => setItems((prev) => prev.filter((i) => i !== item))}
                      className="text-muted-foreground hover:text-foreground"
                      aria-label={`Quitar ${item.file.name}`}
                    >
                      <X className="size-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="space-y-1.5">
              <Label>Categoría</Label>
              <Select
                value={category}
                onValueChange={(v) => {
                  setCategory(v as Category);
                  setAccess(CATEGORIES[v as Category].defaultAccess); // sugerencia según la categoría
                }}
              >
                <SelectTrigger className="h-auto min-h-9 w-full">
                  <SelectValue placeholder="Seleccione el tipo de documento" />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORY_ORDER.map((key) => (
                    <SelectItem key={key} value={key}>
                      <span className="flex flex-col items-start">
                        <span>{CATEGORIES[key].label}</span>
                        <span className="text-xs text-muted-foreground">{CATEGORIES[key].hint}</span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>¿Quién puede consultarlo?</Label>
              <div className="grid grid-cols-2 gap-2" role="radiogroup">
                {(["PUBLIC", "ADMIN"] as const).map((level) => {
                  const Icon = level === "PUBLIC" ? Users : Lock;
                  return (
                    <button
                      key={level}
                      type="button"
                      role="radio"
                      aria-checked={access === level}
                      onClick={() => setAccess(level)}
                      className={cn(
                        "flex items-start gap-2.5 rounded-md border p-3 text-left text-sm transition-colors",
                        access === level ? "border-primary bg-accent" : "hover:bg-muted/50",
                      )}
                    >
                      <Icon className={cn("mt-0.5 size-4", access === level ? "text-primary" : "text-muted-foreground")} />
                      <span>
                        <span className="block font-medium">{ACCESS[level].label}</span>
                        <span className="block text-xs text-muted-foreground">
                          {level === "PUBLIC" ? "Visible en el buscador de los residentes" : "Información reservada"}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {valid.length === 1 && (
              <div className="space-y-1.5">
                <Label htmlFor="doc-title">
                  Nombre para mostrar <span className="font-normal text-muted-foreground">(opcional)</span>
                </Label>
                <Input
                  id="doc-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={valid[0]?.file.name.replace(/\.pdf$/i, "")}
                  maxLength={255}
                />
              </div>
            )}
          </div>
        ) : (
          <ul className="space-y-3">
            {valid.map(({ file, state }) => (
              <li key={file.name + file.size} className="rounded-md border p-3">
                <div className="flex items-center gap-2 text-sm">
                  {state.phase === "done" ? (
                    <CheckCircle2 className="size-4 text-success" />
                  ) : state.phase === "error" ? (
                    <AlertCircle className="size-4 text-destructive" />
                  ) : state.phase === "pending" ? (
                    <FileText className="size-4 text-muted-foreground" />
                  ) : (
                    <Loader2 className="size-4 animate-spin text-primary" />
                  )}
                  <span className="min-w-0 flex-1 truncate font-medium">{file.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {
                      {
                        pending: "En espera",
                        hashing: "Preparando…",
                        uploading: `Subiendo ${(state as { percent?: number }).percent ?? 0}%`,
                        registering: "Enviando a procesamiento…",
                        done: "Enviado",
                        error: "",
                      }[state.phase]
                    }
                  </span>
                </div>
                {state.phase === "uploading" && <Progress value={state.percent} className="mt-2 h-1.5" />}
                {state.phase === "error" && <p className="mt-1.5 text-xs text-destructive">{state.message}</p>}
              </li>
            ))}
            {finished && (
              <p className="text-sm text-muted-foreground">
                Puede cerrar esta ventana: el procesamiento continúa y verá el avance en la lista de documentos.
              </p>
            )}
          </ul>
        )}

        <DialogFooter>
          {!started ? (
            <>
              <Button variant="outline" onClick={() => setOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={start} disabled={!valid.length || !category}>
                <Upload />
                Subir {valid.length > 1 ? `${valid.length} documentos` : "documento"}
              </Button>
            </>
          ) : (
            <Button
              disabled={running}
              onClick={() => {
                setOpen(false);
                reset();
              }}
            >
              {running && <Loader2 className="animate-spin" />}
              {running ? "Subiendo…" : "Listo"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
