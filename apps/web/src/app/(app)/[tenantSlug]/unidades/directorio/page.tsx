import type { Metadata } from "next";
import { Suspense } from "react";

import { DirectorioView } from "@/components/unidades/directorio-view";

export const metadata: Metadata = { title: "Directorio" };

export default function Page() {
  return (
    <Suspense>
      <DirectorioView />
    </Suspense>
  );
}
