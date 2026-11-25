import type { Metadata } from "next";

import { ReservasAdminView } from "@/components/portal/reservas-admin-view";

export const metadata: Metadata = { title: "Reservas" };

export default function Page() {
  return <ReservasAdminView />;
}
