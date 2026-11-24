import type { Metadata } from "next";

import { PlanesView } from "@/components/activos/planes-view";

export const metadata: Metadata = { title: "Planes de mantenimiento" };

export default function Page() {
  return <PlanesView />;
}
