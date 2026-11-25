import type { Metadata } from "next";

import { MorososView } from "@/components/cartera/morosos-view";

export const metadata: Metadata = { title: "Morosos" };

export default function Page() {
  return <MorososView />;
}
