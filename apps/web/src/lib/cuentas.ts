import type { Role } from "./types";

export interface UsuarioCopropiedad {
  user_id: string;
  nombre: string;
  email: string;
  rol: Role;
  rol_etiqueta: string;
  estado: "ACTIVO" | "INVITADO" | "DESACTIVADO";
  ultimo_ingreso: string | null;
  agregado_en: string;
  es_usted: boolean;
}

export interface InvitacionOut {
  usuario: UsuarioCopropiedad;
  nuevo: boolean;
  correo_enviado: boolean;
}

export interface Copropiedad {
  id: string;
  nombre: string;
  slug: string;
  nit: string | null;
  ciudad: string | null;
  direccion: string | null;
  is_demo: boolean;
  creada_en: string;
  unidades: number;
  usuarios: number;
  administradores: number;
  invitaciones_pendientes: number;
}

export interface CopropiedadCreada {
  copropiedad: Copropiedad;
  administrador_nuevo: boolean;
  correo_enviado: boolean;
  enlace_invitacion: string | null;
}

export interface EnlaceInvitacion {
  nombre: string;
  email: string;
  enlace: string;
}

export const baseUsuarios = (tenantId: string) => `/tenants/${tenantId}/usuarios`;

/** Qué puede hacer cada rol, en palabras de la administración (para elegir al invitar). */
export const ROLES_INVITABLES: { rol: Role; etiqueta: string; descripcion: string }[] = [
  { rol: "ADMIN", etiqueta: "Administrador", descripcion: "Todo: configuración, cartera, documentos y usuarios." },
  { rol: "AUXILIAR", etiqueta: "Recepción", descripcion: "Registra recaudos, cierra su caja y atiende PQRS y reservas." },
  { rol: "CONTABILIDAD", etiqueta: "Contabilidad", descripcion: "Verifica y concilia recaudos, pagos y consignaciones." },
  { rol: "CONSEJO", etiqueta: "Consejo de administración", descripcion: "Consulta tableros, cortes y asambleas, sin modificar." },
  { rol: "MANTENIMIENTO", etiqueta: "Mantenimiento", descripcion: "Ve y registra su trabajo de mantenimiento." },
  { rol: "RESIDENTE", etiqueta: "Residente", descripcion: "Portal: estado de cuenta, PQRS, reservas y circulares." },
];

export const ESTADO_USUARIO: Record<UsuarioCopropiedad["estado"], { etiqueta: string; tono: "success" | "warning" | "neutral" }> = {
  ACTIVO: { etiqueta: "Activo", tono: "success" },
  INVITADO: { etiqueta: "Invitación pendiente", tono: "warning" },
  DESACTIVADO: { etiqueta: "Desactivado", tono: "neutral" },
};
