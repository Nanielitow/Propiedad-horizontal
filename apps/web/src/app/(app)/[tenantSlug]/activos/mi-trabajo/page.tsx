import type { Metadata } from "next";

import { MiTrabajoView } from "@/components/activos/mi-trabajo-view";

export const metadata: Metadata = { title: "Mi trabajo" };

export default function Page() {
  return <MiTrabajoView />;
}
