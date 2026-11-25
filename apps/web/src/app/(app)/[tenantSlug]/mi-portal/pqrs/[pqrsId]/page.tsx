import type { Metadata } from "next";

import { PqrsDetalleView } from "@/components/portal/pqrs-detalle-view";

export const metadata: Metadata = { title: "PQRS" };

export default async function Page({ params }: { params: Promise<{ pqrsId: string }> }) {
  const { pqrsId } = await params;
  return <PqrsDetalleView pqrsId={pqrsId} />;
}
