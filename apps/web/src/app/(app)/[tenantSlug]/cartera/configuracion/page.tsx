import type { Metadata } from "next";

import { ConfiguracionCarteraView } from "@/components/cartera/configuracion-view";

export const metadata: Metadata = { title: "Configuración de la cartera" };

export default function Page() {
  return <ConfiguracionCarteraView />;
}
