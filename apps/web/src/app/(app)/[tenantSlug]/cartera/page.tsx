import type { Metadata } from "next";

import { PanelCarteraView } from "@/components/cartera/panel-view";

export const metadata: Metadata = { title: "Cartera" };

export default function Page() {
  return <PanelCarteraView />;
}
