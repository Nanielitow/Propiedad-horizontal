"use client";

import { FileText } from "lucide-react";

import { usePdfViewer } from "@/components/pdf-viewer/viewer-context";
import type { Deadline } from "@/lib/types";

/** Frase literal del documento + enlace que abre el visor en la página, resaltada. */
export function SourceQuote({ deadline }: { deadline: Deadline }) {
  const { open } = usePdfViewer();
  if (!deadline.source_quote) return null;
  return (
    <div className="rounded-md border-l-2 border-primary/30 bg-muted/60 px-3 py-2">
      <p className="text-sm leading-relaxed text-muted-foreground italic">«{deadline.source_quote}»</p>
      <button
        type="button"
        onClick={() =>
          open({
            documentId: deadline.document_id,
            title: deadline.document_title,
            page: deadline.source_page ?? 1,
            highlight: deadline.source_quote ?? undefined,
          })
        }
        className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
      >
        <FileText className="size-3.5" />
        {deadline.document_title}
        {deadline.source_page ? ` · pág. ${deadline.source_page}` : ""} — ver en el documento
      </button>
    </div>
  );
}
