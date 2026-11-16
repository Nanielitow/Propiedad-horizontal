import type { Metadata } from "next";

import { DeadlinesView } from "@/components/deadlines/deadlines-view";

export const metadata: Metadata = { title: "Vencimientos" };

export default function DeadlinesPage() {
  return <DeadlinesView />;
}
