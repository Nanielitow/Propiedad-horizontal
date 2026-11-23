import type { Metadata } from "next";

import { RegistrarView } from "@/components/recaudos/registrar-view";

export const metadata: Metadata = { title: "Registrar recaudo" };

export default function Page() {
  return <RegistrarView />;
}
