import type { Metadata } from "next";

import { FichaUnidadView } from "@/components/unidades/ficha-unidad-view";

export const metadata: Metadata = { title: "Unidad" };

export default async function Page({ params }: { params: Promise<{ unidadId: string }> }) {
  const { unidadId } = await params;
  return <FichaUnidadView unidadId={unidadId} />;
}
