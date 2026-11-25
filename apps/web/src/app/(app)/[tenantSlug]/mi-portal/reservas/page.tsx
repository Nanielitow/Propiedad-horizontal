import type { Metadata } from "next";

import { ReservarView } from "@/components/portal/reservar-view";

export const metadata: Metadata = { title: "Reservar" };

export default function Page() {
  return <ReservarView />;
}
