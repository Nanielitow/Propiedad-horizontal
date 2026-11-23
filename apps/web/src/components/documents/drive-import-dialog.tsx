"use client";

import { CheckCircle2, CircleAlert, Copy, Loader2, Lock, Users } from "lucide-react";
import { useEffect, useState } from "react";
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
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import { cambiarCuenta, elegirDeDrive, type GoogleConfig, prepararGoogle } from "@/lib/google-drive";
import { ACCESS, CATEGORIES, CATEGORY_ORDER } from "@/lib/labels";
import type { AccessLevel, Category } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Resultado {
  file_id: string;
  nombre: string | null;
  estado: "IMPORTADO" | "DUPLICADO" | "ERROR";
  document_id: string | null;
  mensaje: string | null;
}

const ESTADO = {
  IMPORTADO: { icono: CheckCircle2, clase: "text-success", texto: "Importado: se está procesando" },
  DUPLICADO: { icono: Copy, clase: "text-muted-foreground", texto: "Ya estaba en la plataforma" },
  ERROR: { icono: CircleAlert, clase: "text-destructive", texto: "No se pudo importar" },
} as const;

/** Logo de Google Drive (marca registrada de Google; se usa para identificar la integración). */
function DriveLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 87.3 78" className={className} aria-hidden="true">
      <path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H0c0 1.55.4 3.1 1.2 4.5z" fill="#0066da" />
      <path d="M43.65 25 29.9 1.2c-1.35.8-2.5 1.9-3.3 3.3L1.2 48.5A9.06 9.06 0 0 0 0 53h27.5z" fill="#00ac47" />
      <path d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5H59.8l5.85 11.5z" fill="#ea4335" />
      <path d="M43.65 25 57.4 1.2C56.05.4 54.5 0 52.9 0H34.4c-1.6 0-3.15.45-4.5 1.2z" fill="#00832d" />
      <path d="M59.8 53H27.5L13.75 76.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z" fill="#2684fc" />
      <path d="M73.4 26.5 60.7 4.5c-.8-1.4-1.95-2.5-3.3-3.3L43.65 25 59.8 53h27.45c0-1.55-.4-3.1-1.2-4.5z" fill="#ffba00" />
    </svg>
  );
}

export function DriveImportDialog({ onImported }: { onImported: () => void }) {
  const { tenant } = useTenant();
  const { data: config } = useSWR<GoogleConfig | { enabled: false }>("/api/config/google", (u: string) =>
    fetch(u).then((r) => r.json()),
  );
  const [abierto, setAbierto] = useState(false);
  const [listo, setListo] = useState(false);
  const [category, setCategory] = useState<Category | undefined>();
  const [access, setAccess] = useState<AccessLevel>("ADMIN");
  const [trabajando, setTrabajando] = useState<"eligiendo" | "importando" | null>(null);
  const [resultados, setResultados] = useState<Resultado[] | null>(null);

  // Precarga los scripts de Google al abrir: la ventana de permisos debe abrirse en el mismo clic
  useEffect(() => {
    if (!abierto || !config?.enabled) return;
    prepararGoogle()
      .then(() => setListo(true))
      .catch((e: Error) => toast.error(e.message));
  }, [abierto, config?.enabled]);

  if (!config?.enabled) return null; // integración no configurada en este servidor

  async function importar() {
    if (!config?.enabled || !category) return;
    setResultados(null);
    setTrabajando("eligiendo");
    try {
      const elegido = await elegirDeDrive(config);
      if (!elegido?.archivos.length) return;
      setTrabajando("importando");
      const r = await api<{ resultados: Resultado[] }>(`/tenants/${tenant.tenant_id}/documents/import/google-drive`, {
        method: "POST",
        json: { access_token: elegido.token, files: elegido.archivos.map((a) => ({ id: a.id })), category, access_level: access },
      });
      const nombres = new Map(elegido.archivos.map((a) => [a.id, a.name]));
      setResultados(r.resultados.map((x) => ({ ...x, nombre: x.nombre ?? nombres.get(x.file_id) ?? x.file_id })));
      const n = r.resultados.filter((x) => x.estado === "IMPORTADO").length;
      if (n) {
        toast.success(`${n} ${n === 1 ? "documento importado" : "documentos importados"} desde Google Drive`);
        onImported();
      }
    } catch (e) {
      toast.error(e instanceof ApiError || e instanceof Error ? e.message : "No se pudo importar");
    } finally {
      setTrabajando(null);
    }
  }

  return (
    <Dialog
      open={abierto}
      onOpenChange={(v) => {
        setAbierto(v);
        if (!v) setResultados(null);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <DriveLogo className="size-4" /> Desde Google Drive
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Importar desde Google Drive</DialogTitle>
          <DialogDescription>
            Elija PDF o documentos de Google (se convierten a PDF). La app solo accede a los archivos que usted seleccione,
            nunca al resto de su Drive.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Categoría</Label>
            <Select
              value={category}
              onValueChange={(v) => {
                setCategory(v as Category);
                setAccess(CATEGORIES[v as Category].defaultAccess);
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
            <Label>¿Quién puede consultarlos?</Label>
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
                    <span className="font-medium">{ACCESS[level].label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {resultados && (
            <ul className="max-h-56 divide-y overflow-y-auto rounded-md border text-sm">
              {resultados.map((r) => {
                const e = ESTADO[r.estado];
                return (
                  <li key={r.file_id} className="flex items-start gap-2.5 px-3 py-2">
                    <e.icono className={cn("mt-0.5 size-4 shrink-0", e.clase)} />
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{r.nombre}</span>
                      <span className="block text-xs text-muted-foreground">{r.mensaje ?? e.texto}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <DialogFooter className="sm:justify-between">
          <button
            type="button"
            disabled={!category || !listo || trabajando !== null}
            onClick={() => {
              cambiarCuenta(); // olvida la cuenta actual y abre el selector de cuentas en este mismo clic
              void importar();
            }}
            className="self-center text-sm text-muted-foreground underline-offset-2 hover:text-foreground hover:underline disabled:pointer-events-none disabled:opacity-50"
          >
            Usar otra cuenta de Google
          </button>
          <div className="flex flex-col-reverse gap-2 sm:flex-row">
          <Button variant="outline" onClick={() => setAbierto(false)}>
            {resultados ? "Cerrar" : "Cancelar"}
          </Button>
          <Button disabled={!category || !listo || trabajando !== null} onClick={importar}>
            {trabajando ? <Loader2 className="size-4 animate-spin" /> : <DriveLogo className="size-4" />}
            {trabajando === "importando" ? "Importando…" : trabajando === "eligiendo" ? "Esperando a Google…" : resultados ? "Importar más" : "Elegir archivos en Drive"}
          </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
