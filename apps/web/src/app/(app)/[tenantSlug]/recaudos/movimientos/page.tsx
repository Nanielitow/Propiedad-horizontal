import type { Metadata } from "next";
import { Suspense } from "react";

import { MovimientosView } from "@/components/recaudos/movimientos-view";

export const metadata: Metadata = { title: "Movimientos" };

export default function Page() {
  // Los filtros viven en la URL (useSearchParams): requiere un límite de Suspense
  return (
    <Suspense>
      <MovimientosView />
    </Suspense>
  );
}
