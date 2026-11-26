import type { Metadata } from "next";

import { UsuariosView } from "@/components/usuarios/usuarios-view";

export const metadata: Metadata = { title: "Usuarios y accesos" };

export default function Page() {
  return <UsuariosView />;
}
