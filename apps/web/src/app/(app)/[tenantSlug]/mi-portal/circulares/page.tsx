import type { Metadata } from "next";

import { CircularesView } from "@/components/portal/circulares-view";

export const metadata: Metadata = { title: "Circulares" };

export default function Page() {
  return <CircularesView />;
}
