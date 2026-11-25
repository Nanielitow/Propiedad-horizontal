import type { Metadata } from "next";

import { EstadoCuentaView } from "@/components/cartera/estado-cuenta";

export const metadata: Metadata = { title: "Estado de cuenta" };

export default async function Page({ params }: { params: Promise<{ unidadId: string }> }) {
  const { unidadId } = await params;
  return <EstadoCuentaView unidadId={unidadId} />;
}
