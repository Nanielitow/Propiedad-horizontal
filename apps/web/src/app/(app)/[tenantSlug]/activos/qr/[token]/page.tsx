import type { Metadata } from "next";

import { QrView } from "@/components/activos/qr-view";

export const metadata: Metadata = { title: "Equipo" };

// Destino del QR pegado en el equipo. Sin sesión, el layout lleva al login y vuelve aquí.
export default async function Page({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <QrView token={token} />;
}
