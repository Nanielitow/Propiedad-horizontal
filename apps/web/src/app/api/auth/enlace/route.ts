import { reenviarCuenta } from "@/lib/auth-bff";

// Datos del enlace del correo (a quién pertenece). El token llega en el cuerpo, nunca en la dirección.
export async function POST(request: Request) {
  return reenviarCuenta(request, "enlace", false);
}
