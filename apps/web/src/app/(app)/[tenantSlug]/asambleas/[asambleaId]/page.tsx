import type { Metadata } from "next";

import { AsambleaDetalleView } from "@/components/asambleas/detalle-view";

export const metadata: Metadata = { title: "Asamblea" };

export default async function Page({ params }: { params: Promise<{ asambleaId: string }> }) {
  const { asambleaId } = await params;
  return <AsambleaDetalleView asambleaId={asambleaId} />;
}
