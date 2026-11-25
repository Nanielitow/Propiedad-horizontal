import type { Metadata } from "next";
import { Suspense } from "react";

import { PagosView } from "@/components/cartera/pagos-view";

export const metadata: Metadata = { title: "Pagos de cuotas" };

export default function Page() {
  // Los filtros viven en la URL (useSearchParams): requiere un límite de Suspense
  return (
    <Suspense>
      <PagosView />
    </Suspense>
  );
}
