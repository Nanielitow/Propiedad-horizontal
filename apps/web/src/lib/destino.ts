import type { Me } from "./types";

/** A dónde va alguien al entrar: la ruta pedida, su primera copropiedad o el panel de la plataforma.
 *  null = la cuenta no tiene a dónde ir (sin copropiedades y sin permiso de plataforma). */
export function destinoInicial(me: Me, next?: string | null): string | null {
  if (next?.startsWith("/") && !next.startsWith("//")) return next;
  const primera = me.memberships[0];
  if (primera) return `/${primera.tenant_slug}`;
  if (me.user.is_platform_admin) return "/plataforma";
  return null;
}
