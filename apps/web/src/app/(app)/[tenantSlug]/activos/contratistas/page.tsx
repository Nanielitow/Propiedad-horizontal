import type { Metadata } from "next";

import { ContratistasView } from "@/components/activos/planes-view";

export const metadata: Metadata = { title: "Contratistas" };

export default function Page() {
  return <ContratistasView />;
}
