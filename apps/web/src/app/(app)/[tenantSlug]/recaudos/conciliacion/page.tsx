import type { Metadata } from "next";

import { ConciliacionView } from "@/components/recaudos/conciliacion-view";

export const metadata: Metadata = { title: "Conciliación bancaria" };

export default function Page() {
  return <ConciliacionView />;
}
