import type { Metadata } from "next";

import { ConciliarView } from "@/components/cartera/conciliar-view";

export const metadata: Metadata = { title: "Conciliar extracto" };

export default function Page() {
  return <ConciliarView />;
}
