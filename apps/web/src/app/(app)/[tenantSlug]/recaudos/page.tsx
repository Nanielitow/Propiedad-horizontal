import type { Metadata } from "next";

import { RecaudosInicio } from "@/components/recaudos/inicio";

export const metadata: Metadata = { title: "Recaudos" };

export default function Page() {
  return <RecaudosInicio />;
}
