import type { Metadata } from "next";
import { Suspense } from "react";

import { RecomendacionesView } from "@/components/activos/novedades-view";

export const metadata: Metadata = { title: "Recomendaciones técnicas" };

export default function Page() {
  // Los filtros viven en la URL (useSearchParams): requiere un límite de Suspense
  return (
    <Suspense>
      <RecomendacionesView />
    </Suspense>
  );
}
