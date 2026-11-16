import type { Metadata } from "next";

import { ComparisonDetail } from "@/components/quotes/comparison-detail";

export const metadata: Metadata = { title: "Comparación de cotizaciones" };

export default async function ComparisonPage({ params }: { params: Promise<{ comparisonId: string }> }) {
  const { comparisonId } = await params;
  return <ComparisonDetail id={comparisonId} />;
}
