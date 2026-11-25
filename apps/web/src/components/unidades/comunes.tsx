"use client";

import { BadgeCheck, CreditCard, Home, Phone } from "lucide-react";
import { useSWRConfig } from "swr";

import { Etiqueta } from "@/components/recaudos/comunes";
import { baseTenant, type Ocupacion, OCUPACION, type Relacion, RELACION, telefonoTexto, type Vinculo } from "@/lib/unidades";

export function OcupacionBadge({ ocupacion }: { ocupacion: Ocupacion }) {
  const o = OCUPACION[ocupacion];
  return (
    <Etiqueta tono={o.tono} title={o.ayuda}>
      {o.label}
    </Etiqueta>
  );
}

const TONO_RELACION: Record<Relacion, "info" | "neutral" | "success" | "warning"> = {
  PROPIETARIO: "info",
  ARRENDATARIO: "success",
  RESIDENTE: "neutral",
  AUTORIZADO: "warning",
};

export function RelacionBadge({ relacion }: { relacion: Relacion }) {
  return (
    <Etiqueta tono={TONO_RELACION[relacion]} title={RELACION[relacion].ayuda}>
      {RELACION[relacion].label}
    </Etiqueta>
  );
}

/** Íconos compactos: vive allí, contacto principal, responsable de pago. */
export function MarcasVinculo({ v }: { v: Vinculo }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-muted-foreground">
      {v.reside && (
        <span title="Vive en la unidad" className="inline-flex items-center gap-0.5 text-xs">
          <Home className="size-3.5" />
          <span className="sr-only">Vive en la unidad</span>
        </span>
      )}
      {v.es_contacto_principal && (
        <span title="Contacto principal" className="inline-flex items-center gap-0.5 text-xs text-primary">
          <BadgeCheck className="size-3.5" /> Contacto
        </span>
      )}
      {v.responsable_pago && (
        <span title="Responsable del pago de la cuota" className="inline-flex items-center gap-0.5 text-xs text-success">
          <CreditCard className="size-3.5" /> Paga
        </span>
      )}
    </span>
  );
}

export function Telefono({ numero }: { numero: string | null }) {
  if (!numero) return null;
  return (
    <a href={`tel:${numero}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground hover:underline">
      <Phone className="size-3.5" /> {telefonoTexto(numero)}
    </a>
  );
}

/** Revalida todas las consultas del censo (listado, fichas, directorio, resumen) tras un cambio. */
export function useRefrescarUnidades() {
  const { mutate } = useSWRConfig();
  return (tenantId: string) =>
    mutate(
      (clave) =>
        typeof clave === "string" &&
        ["unidades", "personas", "vehiculos", "mi-unidad"].some((p) => clave.startsWith(`${baseTenant(tenantId)}/${p}`)),
      undefined,
      { revalidate: true },
    );
}
