import type { Metadata } from "next";

import { MinutesView } from "@/components/minutes/minutes-view";

export const metadata: Metadata = { title: "Actas" };

export default function MinutesPage() {
  return <MinutesView />;
}
