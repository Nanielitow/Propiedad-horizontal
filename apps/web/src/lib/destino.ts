import type { Me } from "./types";

/** Copropiedades donde la persona es administradora. */
export function administradas(me: Pick<Me, "memberships">): number {
  return me.memberships.filter((m) => m.role === "ADMIN").length;
}

/** A dónde va alguien al entrar: la ruta pedida, el resumen (si administra varias), su copropiedad o la plataforma.
 *  null = la cuenta no tiene a dónde ir (sin copropiedades y sin permiso de plataforma). */
export function destinoInicial(me: Me, next?: string | null): string | null {
  if (next?.startsWith("/") && !next.startsWith("//")) return next;
  if (administradas(me) >= 2) return "/mis-copropiedades";
  const primera = me.memberships[0];
  if (primera) return `/${primera.tenant_slug}`;
  if (me.user.is_platform_admin) return "/plataforma";
  return null;
}
