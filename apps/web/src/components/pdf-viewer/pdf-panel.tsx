"use client";

import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Highlighter,
  Minus,
  Plus,
  X,
} from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useMediaQuery } from "@/hooks/use-media-query";

import { usePdfViewer } from "./viewer-context";

const PdfCanvas = dynamic(() => import("./pdf-canvas"), {
  ssr: false,
  loading: () => <Skeleton className="aspect-[1/1.414] w-full" />,
});

// Las URLs firmadas duran 5 min; se reutilizan durante 4 para no pedir una por clic
const URL_TTL_MS = 4 * 60 * 1000;
const urlCache = new Map<string, { url: string; at: number }>();

const ZOOM_STEPS = [0.75, 1, 1.25, 1.5, 2] as const;
const MIN_ZOOM = ZOOM_STEPS[0];
const MAX_ZOOM = ZOOM_STEPS[4];

function stepZoom(current: number, direction: 1 | -1): number {
  const i = ZOOM_STEPS.findIndex((z) => z === current);
  return ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, Math.max(0, i + direction))] ?? current;
}

function useSignedUrl(tenantId: string, documentId: string | undefined) {
  const [state, setState] = useState<{ url: string | null; error: string | null }>({ url: null, error: null });
  useEffect(() => {
    if (!documentId) return;
    const cached = urlCache.get(documentId);
    if (cached && Date.now() - cached.at < URL_TTL_MS) {
      setState({ url: cached.url, error: null });
      return;
    }
    let cancelled = false;
    setState({ url: null, error: null });
    api<{ url: string }>(`/tenants/${tenantId}/documents/${documentId}/file-url`)
      .then(({ url }) => {
        urlCache.set(documentId, { url, at: Date.now() });
        if (!cancelled) setState({ url, error: null });
      })
      .catch((e: Error) => !cancelled && setState({ url: null, error: e.message }));
    return () => {
      cancelled = true;
    };
  }, [tenantId, documentId]);
  return state;
}

function ViewerBody() {
  const { tenant } = useTenant();
  const { target, close } = usePdfViewer();
  const { url, error } = useSignedUrl(tenant.tenant_id, target?.documentId);
  const [page, setPage] = useState(1);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const [loadError, setLoadError] = useState(false);
  const [width, setWidth] = useState(560);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Nueva cita (aunque sea del mismo documento) -> ir a su página
  useEffect(() => {
    if (target) setPage(target.page);
  }, [target]);

  useEffect(() => {
    setNumPages(null);
    setLoadError(false);
  }, [target?.documentId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(280, entry.contentRect.width - 48));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (!target) return null;
  const showHighlight = Boolean(target.highlight) && page === target.page;

  return (
    <div className="flex h-full min-h-0 flex-col bg-muted/60">
      {/* Encabezado */}
      <div className="flex items-center gap-2 border-b bg-card px-3 py-2.5">
        <FileText className="size-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={target.title}>
            {target.title}
          </p>
          <p className="text-xs text-muted-foreground">
            Página {page}
            {numPages ? ` de ${numPages}` : ""}
          </p>
        </div>
        {url && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" asChild>
                <a href={url} target="_blank" rel="noreferrer" aria-label="Abrir en una pestaña nueva">
                  <ExternalLink />
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Abrir en una pestaña nueva</TooltipContent>
          </Tooltip>
        )}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" onClick={close} aria-label="Cerrar visor">
              <X />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Cerrar visor</TooltipContent>
        </Tooltip>
      </div>

      {/* Barra de herramientas */}
      <div className="flex items-center justify-between border-b bg-card px-3 py-1.5">
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Página anterior">
            <ChevronLeft />
          </Button>
          <span className="min-w-16 text-center text-xs tabular-nums text-muted-foreground">
            {page} / {numPages ?? "…"}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={!numPages || page >= numPages}
            onClick={() => setPage((p) => p + 1)}
            aria-label="Página siguiente"
          >
            <ChevronRight />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={zoom <= MIN_ZOOM}
            onClick={() => setZoom((z) => stepZoom(z, -1))}
            aria-label="Reducir"
          >
            <Minus />
          </Button>
          <span className="w-11 text-center text-xs tabular-nums text-muted-foreground">{Math.round(zoom * 100)}%</span>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={zoom >= MAX_ZOOM}
            onClick={() => setZoom((z) => stepZoom(z, 1))}
            aria-label="Ampliar"
          >
            <Plus />
          </Button>
        </div>
      </div>

      {showHighlight && (
        <div className="flex items-center gap-2 border-b bg-warning-soft px-3 py-1.5 text-xs text-warning">
          <Highlighter className="size-3.5" />
          El fragmento citado aparece resaltado en la página.
        </div>
      )}

      {/* Documento */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto p-6">
        {error || loadError ? (
          <div className="mx-auto mt-10 flex max-w-xs flex-col items-center text-center text-sm text-muted-foreground">
            <AlertCircle className="mb-2 size-6 text-destructive" />
            {error ?? "No se pudo cargar el documento. Intente abrirlo de nuevo."}
          </div>
        ) : url ? (
          <div className="mx-auto w-fit">
            <PdfCanvas
              url={url}
              page={page}
              width={Math.round(width * zoom)}
              highlight={showHighlight ? target.highlight : undefined}
              onLoad={setNumPages}
              onError={() => setLoadError(true)}
            />
          </div>
        ) : (
          <Skeleton className="mx-auto aspect-[1/1.414]" style={{ width }} />
        )}
      </div>
    </div>
  );
}

/** Panel lateral en escritorio; hoja a pantalla completa en móvil. */
export function PdfPanel() {
  const { target, close } = usePdfViewer();
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  if (isDesktop) {
    if (!target) return null;
    return (
      <aside className="w-[min(46vw,760px)] shrink-0 border-l animate-in fade-in slide-in-from-right-4 duration-200">
        <ViewerBody />
      </aside>
    );
  }
  return (
    <Sheet open={Boolean(target)} onOpenChange={(open) => !open && close()}>
      <SheetContent side="right" showCloseButton={false} className="w-full p-0 sm:max-w-full">
        <SheetTitle className="sr-only">Visor de documento</SheetTitle>
        <ViewerBody />
      </SheetContent>
    </Sheet>
  );
}
