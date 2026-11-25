import type { Metadata } from "next";

import { MiUnidadView } from "@/components/unidades/mi-unidad-view";

export const metadata: Metadata = { title: "Mi unidad" };

export default function Page() {
  return <MiUnidadView />;
}
