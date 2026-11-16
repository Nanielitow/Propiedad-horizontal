import type { Metadata } from "next";

import { MinutesDetail } from "@/components/minutes/minutes-detail";

export const metadata: Metadata = { title: "Acta" };

export default async function ActaPage({ params }: { params: Promise<{ documentId: string }> }) {
  const { documentId } = await params;
  return <MinutesDetail documentId={documentId} />;
}
