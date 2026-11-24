import type { Metadata } from "next";
import { Suspense } from "react";

import { NovedadesView } from "@/components/activos/novedades-view";

export const metadata: Metadata = { title: "Novedades" };

export default function Page() {
  // Los filtros viven en la URL (useSearchParams): requiere un límite de Suspense
  return (
    <Suspense>
      <NovedadesView />
    </Suspense>
  );
}
