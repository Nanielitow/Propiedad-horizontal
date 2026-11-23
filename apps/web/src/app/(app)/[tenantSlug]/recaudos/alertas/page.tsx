import type { Metadata } from "next";

import { AlertasView } from "@/components/recaudos/alertas-view";

export const metadata: Metadata = { title: "Alertas de recaudos" };

export default function Page() {
  return <AlertasView />;
}
