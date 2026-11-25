import type { Metadata } from "next";

import { PqrsListaView } from "@/components/portal/pqrs-lista-view";

export const metadata: Metadata = { title: "PQRS" };

export default function Page() {
  return <PqrsListaView />;
}
