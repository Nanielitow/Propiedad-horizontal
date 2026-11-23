import type { Metadata } from "next";

import { ConfiguracionView } from "@/components/recaudos/configuracion-view";

export const metadata: Metadata = { title: "Configuración de recaudos" };

export default function Page() {
  return <ConfiguracionView />;
}
