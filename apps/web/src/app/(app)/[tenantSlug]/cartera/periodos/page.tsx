import type { Metadata } from "next";

import { PeriodosView } from "@/components/cartera/periodos-view";

export const metadata: Metadata = { title: "Facturación" };

export default function Page() {
  return <PeriodosView />;
}
