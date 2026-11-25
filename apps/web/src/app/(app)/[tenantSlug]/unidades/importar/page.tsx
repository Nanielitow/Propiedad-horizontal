import type { Metadata } from "next";

import { ImportarView } from "@/components/unidades/importar-view";

export const metadata: Metadata = { title: "Importar censo" };

export default function Page() {
  return <ImportarView />;
}
