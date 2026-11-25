import type { Metadata } from "next";
import { Suspense } from "react";

import { UnidadesView } from "@/components/unidades/unidades-view";

export const metadata: Metadata = { title: "Unidades" };

export default function Page() {
  // Los filtros viven en la URL (useSearchParams): requiere un límite de Suspense
  return (
    <Suspense>
      <UnidadesView />
    </Suspense>
  );
}
