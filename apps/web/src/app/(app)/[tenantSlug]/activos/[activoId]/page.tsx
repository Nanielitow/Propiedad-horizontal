import type { Metadata } from "next";

import { HojaDeVidaView } from "@/components/activos/hoja-vida-view";

export const metadata: Metadata = { title: "Hoja de vida" };

export default async function Page({ params }: { params: Promise<{ activoId: string }> }) {
  const { activoId } = await params;
  return <HojaDeVidaView activoId={activoId} />;
}
