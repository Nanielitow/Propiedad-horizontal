import type { Metadata } from "next";

import { InicioView } from "@/components/portal/inicio-view";

export const metadata: Metadata = { title: "Inicio" };

export default function Page() {
  return <InicioView />;
}
