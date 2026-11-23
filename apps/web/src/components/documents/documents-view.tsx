"use client";

import {
  Eye,
  FileText,
  FolderOpen,
  Lock,
  MoreHorizontal,
  RotateCcw,
  ScanText,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { usePdfViewer } from "@/components/pdf-viewer/viewer-context";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher } from "@/lib/api";
import { ACCESS, CATEGORIES, CATEGORY_ORDER, formatBytes, formatDate, isProcessing } from "@/lib/labels";
import type { Category, DocumentItem } from "@/lib/types";
import { cn } from "@/lib/utils";

import { StatusCell } from "./status-cell";
import { DriveImportDialog } from "./drive-import-dialog";
import { UploadDialog } from "./upload-dialog";

const normalize = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

export function DocumentsView() {
  const { tenant, isAdmin } = useTenant();
  const viewer = usePdfViewer();
  const base = `/tenants/${tenant.tenant_id}/documents`;
  const { data, isLoading, mutate } = useSWR<DocumentItem[]>(`${base}?limit=200`, fetcher, {
    // Mientras haya documentos procesándose se consulta cada 2 s para mostrar el avance
    refreshInterval: (docs) => (docs?.some((d) => isProcessing(d.status)) ? 2000 : 0),
  });
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<Category | "ALL">("ALL");
  const [toDelete, setToDelete] = useState<DocumentItem | null>(null);

  const docs = useMemo(() => {
    const q = normalize(query.trim());
    return (data ?? []).filter(
      (d) =>
        (category === "ALL" || d.category === category) &&
        (!q || normalize(d.title).includes(q) || normalize(d.original_filename).includes(q)),
    );
  }, [data, query, category]);

  const counts = useMemo(() => {
    const all = data ?? [];
    return {
      ready: all.filter((d) => d.status === "READY").length,
      processing: all.filter((d) => isProcessing(d.status)).length,
      failed: all.filter((d) => d.status === "FAILED").length,
    };
  }, [data]);

  const openDoc = (d: DocumentItem) => viewer.open({ documentId: d.id, title: d.title, page: 1 });

  async function reprocess(d: DocumentItem) {
    try {
      await api(`${base}/${d.id}/reprocess`, { method: "POST" });
      toast.success("El documento se volverá a procesar.");
      void mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function remove(d: DocumentItem) {
    try {
      await api(`${base}/${d.id}`, { method: "DELETE" });
      toast.success(`"${d.title}" fue eliminado.`);
      if (viewer.target?.documentId === d.id) viewer.close();
      void mutate();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setToDelete(null);
    }
  }

  const hasFilters = query.trim() !== "" || category !== "ALL";

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Documentos"
        description={
          isAdmin
            ? "Archivo documental de la copropiedad. Lo que suba aquí queda disponible en el buscador."
            : "Documentos publicados por la administración para los residentes."
        }
        actions={
          isAdmin && (
            <>
              <DriveImportDialog onImported={() => void mutate()} />
              <UploadDialog onUploaded={() => void mutate()} />
            </>
          )
        }
      />

      <div className="space-y-4 p-6">
        {/* Resumen (administración) */}
        {isAdmin && data && data.length > 0 && (
          <div className="flex flex-wrap gap-2 text-sm">
            <span className="rounded-md border bg-card px-3 py-1.5">
              <span className="font-semibold">{counts.ready}</span> <span className="text-muted-foreground">disponibles</span>
            </span>
            {counts.processing > 0 && (
              <span className="rounded-md border border-primary/20 bg-info-soft px-3 py-1.5 text-primary">
                <span className="font-semibold">{counts.processing}</span> procesándose
              </span>
            )}
            {counts.failed > 0 && (
              <span className="rounded-md border border-destructive/20 bg-destructive/5 px-3 py-1.5 text-destructive">
                <span className="font-semibold">{counts.failed}</span> con error
              </span>
            )}
          </div>
        )}

        {/* Filtros */}
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1 sm:max-w-sm">
            <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar por nombre…"
              className="h-9 bg-card pl-8"
              aria-label="Buscar documentos por nombre"
            />
          </div>
          <Select value={category} onValueChange={(v) => setCategory(v as Category | "ALL")}>
            <SelectTrigger className="h-9 w-full bg-card sm:w-56" aria-label="Filtrar por categoría">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">Todas las categorías</SelectItem>
              {CATEGORY_ORDER.map((key) => (
                <SelectItem key={key} value={key}>
                  {CATEGORIES[key].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Tabla */}
        <div className="overflow-hidden rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/50 hover:bg-muted/50">
                <TableHead className="pl-4">Documento</TableHead>
                <TableHead>Categoría</TableHead>
                {isAdmin && <TableHead>Visible para</TableHead>}
                {isAdmin && <TableHead>Estado</TableHead>}
                <TableHead className="hidden md:table-cell">Fecha</TableHead>
                <TableHead className="w-24 pr-4 text-right">
                  <span className="sr-only">Acciones</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 4 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell className="pl-4" colSpan={isAdmin ? 6 : 4}>
                      <Skeleton className="h-9 w-full" />
                    </TableCell>
                  </TableRow>
                ))}

              {docs.map((d) => {
                const ready = d.status === "READY";
                return (
                  <TableRow
                    key={d.id}
                    className={cn(ready && "cursor-pointer", viewer.target?.documentId === d.id && "bg-accent/60")}
                    onClick={() => ready && openDoc(d)}
                  >
                    <TableCell className="max-w-0 pl-4 sm:max-w-none">
                      <div className="flex items-center gap-3">
                        <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                          <FileText className="size-4" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate font-medium">{d.title}</p>
                          <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                            {formatBytes(d.size_bytes)}
                            {d.page_count ? ` · ${d.page_count} pág.` : ""}
                            {d.is_scanned && (
                              <span className="inline-flex items-center gap-0.5" title="Documento escaneado: el texto se obtuvo con OCR">
                                · <ScanText className="size-3" /> Escaneado
                              </span>
                            )}
                            {d.source === "GOOGLE_DRIVE" && (
                              <span title="Importado desde Google Drive">
                                ·{" "}
                                {d.source_url ? (
                                  <a
                                    href={d.source_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    onClick={(e) => e.stopPropagation()}
                                    className="underline-offset-2 hover:text-foreground hover:underline"
                                  >
                                    Drive
                                  </a>
                                ) : (
                                  "Drive"
                                )}
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-normal">
                        {CATEGORIES[d.category].label}
                      </Badge>
                    </TableCell>
                    {isAdmin && (
                      <TableCell>
                        <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
                          {d.access_level === "PUBLIC" ? <Users className="size-3.5" /> : <Lock className="size-3.5" />}
                          {ACCESS[d.access_level].short}
                        </span>
                      </TableCell>
                    )}
                    {isAdmin && (
                      <TableCell>
                        <StatusCell doc={d} />
                      </TableCell>
                    )}
                    <TableCell className="hidden text-sm text-muted-foreground md:table-cell">{formatDate(d.created_at)}</TableCell>
                    <TableCell className="pr-4 text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        {ready && (
                          <Button variant="ghost" size="sm" onClick={() => openDoc(d)}>
                            <Eye /> Ver
                          </Button>
                        )}
                        {isAdmin && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon-sm" aria-label={`Más acciones para ${d.title}`}>
                                <MoreHorizontal />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                disabled={!(d.status === "READY" || d.status === "FAILED")}
                                onSelect={() => void reprocess(d)}
                              >
                                <RotateCcw /> {d.status === "FAILED" ? "Reintentar procesamiento" : "Volver a procesar"}
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem variant="destructive" onSelect={() => setToDelete(d)}>
                                <Trash2 /> Eliminar
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>

          {/* Estados vacíos */}
          {!isLoading && docs.length === 0 && (
            <div className="flex flex-col items-center px-6 py-14 text-center">
              <div className="flex size-11 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                {hasFilters ? <Search className="size-5" /> : <FolderOpen className="size-5" />}
              </div>
              <p className="mt-3 font-medium">
                {hasFilters ? "Ningún documento coincide con la búsqueda" : "Todavía no hay documentos"}
              </p>
              <p className="mt-1 max-w-sm text-sm text-muted-foreground">
                {hasFilters
                  ? "Pruebe con otro nombre o quite el filtro de categoría."
                  : isAdmin
                    ? "Suba el manual de convivencia, actas o contratos para empezar a consultarlos con el buscador."
                    : "Cuando la administración publique documentos para residentes, aparecerán aquí."}
              </p>
              {hasFilters ? (
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => {
                    setQuery("");
                    setCategory("ALL");
                  }}
                >
                  Limpiar filtros
                </Button>
              ) : (
                isAdmin && (
                  <div className="mt-4">
                    <UploadDialog onUploaded={() => void mutate()} />
                  </div>
                )
              )}
            </div>
          )}
        </div>
      </div>

      <AlertDialog open={Boolean(toDelete)} onOpenChange={(open) => !open && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar este documento?</AlertDialogTitle>
            <AlertDialogDescription>
              &quot;{toDelete?.title}&quot; dejará de aparecer en la lista y en las respuestas del buscador para todos los
              usuarios.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={() => toDelete && void remove(toDelete)}
            >
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
