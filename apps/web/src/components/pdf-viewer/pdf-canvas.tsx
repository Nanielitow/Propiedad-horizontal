"use client";

// Se carga solo en el navegador (dynamic import con ssr: false): pdf.js usa APIs
// del DOM que no existen en el servidor.
import { useCallback, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { Skeleton } from "@/components/ui/skeleton";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

const HIGHLIGHT_CLASS = "pdf-hl";

const normalize = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/\s+/g, " ")
    .trim();

/**
 * Ubica el fragmento citado entre los <span> de la capa de texto (una línea en
 * PDFs nativos, una palabra en PDFs con OCR). Se marcan como "anclas" los spans
 * de 4+ letras que aparecen en el fragmento, se agrupan las anclas cercanas y se
 * toma el grupo más grande: ese bloque continuo es el fragmento. Así se resalta
 * completo (incluidas palabras cortas como "de") sin marcar coincidencias
 * sueltas en otras partes de la página.
 *
 * Se trabaja sobre el DOM ya renderizado y no con customTextRenderer, porque
 * react-pdf empareja items y spans con un contador que se desfasa en las capas
 * de texto generadas por OCR.
 */
function isPartOf(spanText: string, target: string, targetWords: Set<string>): boolean {
  const n = normalize(spanText);
  if (n.length >= 4 && target.includes(n)) return true;
  // Línea que el fragmento cubre solo en parte (p. ej. empieza con "CLÁUSULA
  // CUARTA - RENOVACIÓN." y sigue con la frase citada): cuenta si la mayoría
  // de sus palabras significativas están en el fragmento.
  const words = n.split(/[^a-z0-9]+/).filter((w) => w.length >= 3);
  if (words.length < 4) return false;
  return words.filter((w) => targetWords.has(w)).length / words.length >= 0.6;
}

function highlightFragment(layer: Element, target: string): Element | null {
  const spans = Array.from(layer.querySelectorAll("span")).filter(
    (s) => s.childElementCount === 0 && s.textContent?.trim(),
  );
  const targetWords = new Set(target.split(/[^a-z0-9]+/).filter((w) => w.length >= 3));
  const anchors = spans.flatMap((span, i) => (isPartOf(span.textContent ?? "", target, targetWords) ? [i] : []));
  if (!anchors.length) return null;

  const MAX_GAP = 6; // spans sin coincidencia tolerados dentro del bloque
  let best = { start: anchors[0]!, end: anchors[0]!, count: 1 };
  let start = anchors[0]!;
  let count = 1;
  for (let k = 1; k < anchors.length; k++) {
    if (anchors[k]! - anchors[k - 1]! <= MAX_GAP) count++;
    else {
      start = anchors[k]!;
      count = 1;
    }
    if (count > best.count) best = { start, end: anchors[k]!, count };
  }
  for (let i = best.start; i <= best.end; i++) spans[i]!.classList.add(HIGHLIGHT_CLASS);
  return spans[best.start] ?? null;
}

interface Props {
  url: string;
  page: number;
  width: number;
  highlight?: string;
  onLoad: (numPages: number) => void;
  onError: () => void;
}

export default function PdfCanvas({ url, page, width, highlight, onLoad, onError }: Props) {
  const wrapperRef = useRef<HTMLDivElement>(null);

  const onTextLayerRendered = useCallback(() => {
    const layer = wrapperRef.current?.querySelector(".react-pdf__Page__textContent");
    if (!layer || !highlight) return;
    const first = highlightFragment(layer, normalize(highlight));
    first?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlight]);

  return (
    <div ref={wrapperRef}>
      <Document
        file={url}
        onLoadSuccess={({ numPages }) => onLoad(numPages)}
        onLoadError={onError}
        loading={<Skeleton className="aspect-[1/1.414] w-full" style={{ width }} />}
        error={null}
      >
        <Page
          // highlight en la key: otra cita en la misma página vuelve a dibujar la capa de texto
          key={`${page}-${width}-${highlight?.slice(0, 48) ?? ""}`}
          pageNumber={page}
          width={width}
          onRenderTextLayerSuccess={onTextLayerRendered}
          loading={<Skeleton className="aspect-[1/1.414]" style={{ width }} />}
          className="overflow-hidden rounded-sm shadow-[0_1px_3px_rgba(16,24,40,0.12),0_1px_2px_rgba(16,24,40,0.06)]"
        />
      </Document>
    </div>
  );
}
