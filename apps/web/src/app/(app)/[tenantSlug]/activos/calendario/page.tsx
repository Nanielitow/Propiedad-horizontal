import type { Metadata } from "next";
import { Suspense } from "react";

import { CalendarioView } from "@/components/activos/calendario-view";

export const metadata: Metadata = { title: "Calendario de mantenimiento" };

export default function Page() {
  // Los filtros viven en la URL (useSearchParams): requiere un límite de Suspense
  return (
    <Suspense>
      <CalendarioView />
    </Suspense>
  );
}
