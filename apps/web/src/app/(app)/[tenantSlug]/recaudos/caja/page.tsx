import type { Metadata } from "next";

import { CajaView } from "@/components/recaudos/caja-view";

export const metadata: Metadata = { title: "Caja" };

export default function Page() {
  return <CajaView />;
}
