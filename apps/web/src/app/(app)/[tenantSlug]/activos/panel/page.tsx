import type { Metadata } from "next";
import { Suspense } from "react";

import { PanelView } from "@/components/activos/panel-view";

export const metadata: Metadata = { title: "Panel de mantenimiento" };

export default function Page() {
  // Los filtros viven en la URL (useSearchParams): requiere un límite de Suspense
  return (
    <Suspense>
      <PanelView />
    </Suspense>
  );
}
