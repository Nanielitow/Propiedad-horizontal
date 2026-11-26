import { reenviarCuenta } from "@/lib/auth-bff";

export async function POST(request: Request) {
  return reenviarCuenta(request, "recuperar", false);
}
