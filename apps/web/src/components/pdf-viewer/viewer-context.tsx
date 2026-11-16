"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

export interface ViewerTarget {
  documentId: string;
  title: string;
  page: number;
  /** Texto del fragmento citado: se resalta en la página */
  highlight?: string;
}

interface ViewerContextValue {
  target: (ViewerTarget & { nonce: number }) | null;
  open: (target: ViewerTarget) => void;
  close: () => void;
}

const ViewerContext = createContext<ViewerContextValue | null>(null);

export function PdfViewerProvider({ children }: { children: React.ReactNode }) {
  const [target, setTarget] = useState<ViewerContextValue["target"]>(null);
  // nonce: abrir dos veces la misma cita vuelve a saltar a su página
  const open = useCallback((t: ViewerTarget) => setTarget({ ...t, nonce: Date.now() }), []);
  const close = useCallback(() => setTarget(null), []);
  const value = useMemo(() => ({ target, open, close }), [target, open, close]);
  return <ViewerContext.Provider value={value}>{children}</ViewerContext.Provider>;
}

export function usePdfViewer(): ViewerContextValue {
  const ctx = useContext(ViewerContext);
  if (!ctx) throw new Error("usePdfViewer debe usarse dentro de PdfViewerProvider");
  return ctx;
}
