import type { Metadata } from "next";

import { ReportesView } from "@/components/recaudos/reportes-view";

export const metadata: Metadata = { title: "Reportes de recaudos" };

export default function Page() {
  return <ReportesView />;
}
