import type { Metadata } from "next";

import { AsambleasView } from "@/components/asambleas/lista-view";

export const metadata: Metadata = { title: "Asambleas" };

export default function Page() {
  return <AsambleasView />;
}
