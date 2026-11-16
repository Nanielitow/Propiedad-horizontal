"use client";

import { AlertCircle, BookOpenText, Check, ChevronDown, Copy, FileText, Loader2, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { usePdfViewer } from "@/components/pdf-viewer/viewer-context";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { pageLabel } from "@/lib/labels";
import type { ChatMessage, Source } from "@/lib/types";
import { cn } from "@/lib/utils";

// "[1]" o "[1, 3]" -> enlaces "#cite-n" que el renderizador convierte en botones
const CITATION = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g;
const withCitationLinks = (text: string) =>
  text.replace(CITATION, (_, group: string) =>
    group
      .split(",")
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join(""),
  );

function useOpenSource() {
  const { open } = usePdfViewer();
  return (s: Source) =>
    open({ documentId: s.document_id, title: s.document_name, page: s.page_number, highlight: s.content ?? s.snippet });
}

function CitationChip({ n, source }: { n: number; source?: Source }) {
  const openSource = useOpenSource();
  if (!source) return <span className="text-muted-foreground">[{n}]</span>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => openSource(source)}
          className="mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded bg-accent px-1 align-[1px] text-[11px] font-semibold text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
          aria-label={`Ver fuente ${n}: ${source.document_name}, ${pageLabel(source.page_number, source.page_end)}`}
        >
          {n}
        </button>
      </TooltipTrigger>
      <TooltipContent>
        {source.document_name} · {pageLabel(source.page_number, source.page_end)}
      </TooltipContent>
    </Tooltip>
  );
}

function SourceCard({ source, cited }: { source: Source; cited: boolean }) {
  const openSource = useOpenSource();
  return (
    <button
      type="button"
      onClick={() => openSource(source)}
      className={cn(
        "group flex w-full min-w-0 gap-3 rounded-md border bg-card p-3 text-left transition-colors hover:border-primary/40 hover:bg-accent/50",
        !cited && "bg-muted/40",
      )}
    >
      <span
        className={cn(
          "flex size-6 shrink-0 items-center justify-center rounded text-xs font-semibold",
          cited ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground",
        )}
      >
        {source.n}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <FileText className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{source.document_name}</span>
        </span>
        <span className="mt-0.5 block truncate text-xs text-muted-foreground">
          {pageLabel(source.page_number, source.page_end)}
          {source.section_title && ` · ${source.section_title}`}
        </span>
        {source.snippet && (
          <span className="mt-1.5 line-clamp-2 block text-xs leading-relaxed text-muted-foreground">{source.snippet}</span>
        )}
      </span>
      <span className="self-center text-xs font-medium whitespace-nowrap text-primary opacity-0 transition-opacity group-hover:opacity-100">
        Ver página
      </span>
    </button>
  );
}

export function AssistantMessage({ message, onRetry }: { message: ChatMessage; onRetry: () => void }) {
  const [copied, setCopied] = useState(false);
  const [showOthers, setShowOthers] = useState(false);
  const byNumber = useMemo(() => new Map(message.sources.map((s) => [s.n, s])), [message.sources]);
  const cited = message.citations.map((n) => byNumber.get(n)).filter((s): s is Source => Boolean(s));
  const others = message.sources.filter((s) => !message.citations.includes(s.n));
  const streaming = message.status === "streaming";

  async function copy() {
    await navigator.clipboard.writeText(message.content.replace(CITATION, "").replace(/\s+\./g, "."));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="flex gap-3">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
        <BookOpenText className="size-4" />
      </div>

      <div className="min-w-0 flex-1 pt-0.5">
        <p className="mb-1 text-xs font-medium text-muted-foreground">Asistente documental</p>

        {streaming && !message.content ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            {message.sources.length
              ? `Leyendo ${message.sources.length} fragmentos relevantes…`
              : "Buscando en los documentos…"}
          </p>
        ) : (
          <div className={cn("answer text-[0.94rem]", streaming && "typing-caret")}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  const match = href?.match(/^#cite-(\d+)$/);
                  if (match) {
                    const n = Number(match[1]);
                    return <CitationChip n={n} source={byNumber.get(n)} />;
                  }
                  return (
                    <a href={href} target="_blank" rel="noreferrer" className="text-primary underline">
                      {children}
                    </a>
                  );
                },
              }}
            >
              {withCitationLinks(message.content)}
            </ReactMarkdown>
          </div>
        )}

        {message.status === "error" && (
          <div className="mt-3 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span className="flex-1">{message.error}</span>
            {message.retryable && (
              <Button size="sm" variant="outline" onClick={onRetry} className="h-7">
                <RotateCcw className="size-3.5" /> Reintentar
              </Button>
            )}
          </div>
        )}

        {message.status === "done" && cited.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Fuentes citadas ({cited.length})
            </p>
            <div className="grid gap-2">
              {cited.map((s) => (
                <SourceCard key={s.n} source={s} cited />
              ))}
            </div>
          </div>
        )}

        {message.status === "done" && others.length > 0 && (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setShowOthers((v) => !v)}
              className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
              aria-expanded={showOthers}
            >
              <ChevronDown className={cn("size-3.5 transition-transform", showOthers && "rotate-180")} />
              {showOthers ? "Ocultar" : "Ver"} {others.length} fragmento{others.length === 1 ? "" : "s"} revisado
              {others.length === 1 ? "" : "s"} sin citar
            </button>
            {showOthers && (
              <div className="mt-2 grid gap-2">
                {others.map((s) => (
                  <SourceCard key={s.n} source={s} cited={false} />
                ))}
              </div>
            )}
          </div>
        )}

        {message.status === "done" && message.content && (
          <div className="mt-3 flex">
            <Button variant="ghost" size="xs" onClick={copy} className="text-muted-foreground">
              {copied ? <Check /> : <Copy />}
              {copied ? "Copiado" : "Copiar respuesta"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
