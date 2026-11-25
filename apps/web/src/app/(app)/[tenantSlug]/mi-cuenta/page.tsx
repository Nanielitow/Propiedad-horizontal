import type { Metadata } from "next";

import { MiCarteraView } from "@/components/cartera/mi-cartera-view";

export const metadata: Metadata = { title: "Mi cuenta" };

export default function Page() {
  return <MiCarteraView />;
}
