"use client";

import { Car, ChevronRight, Home, ShieldCheck } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { Fila } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Seccion, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/api";
import { fechaCorta } from "@/lib/recaudos";
import { baseTenant, coeficienteTexto, puedeUnidades, TIPO_UNIDAD, TIPO_VEHICULO, type UnidadDetalle } from "@/lib/unidades";

import { MarcasVinculo, OcupacionBadge, RelacionBadge, Telefono } from "./comunes";

export function MiUnidadView() {
  const { tenant, user } = useTenant();
  const permitido = puedeUnidades(tenant.role, "miUnidad");
  const { data, isLoading } = useSWR<UnidadDetalle[]>(permitido ? `${baseTenant(tenant.tenant_id)}/mi-unidad` : null, fetcher);

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Mi unidad" description="Sus datos en el censo de la copropiedad. Si algo no está bien, avísele a la administración." />
      <div className="mx-auto w-full max-w-4xl space-y-5 p-4 sm:p-6">
        {isLoading ? (
          <Skeleton className="h-64" />
        ) : !data?.length ? (
          <div className="rounded-lg border bg-card">
            <Vacio
              icono={Home}
              titulo="Su cuenta aún no está asociada a una unidad"
              texto="Pídale a la administración que lo registre como propietario, arrendatario o residente de su apartamento."
            />
          </div>
        ) : (
          data.map((u) => {
            const yo = u.vinculos.find((v) => v.persona.tiene_cuenta && v.persona.email?.toLowerCase() === user.email.toLowerCase()) ?? u.vinculos.find((v) => v.persona.numero_documento);
            return (
              <div key={u.id} className="space-y-4">
                <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-card p-4">
                  <div className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                    <Home className="size-5" />
                  </div>
                  {/* En celular el título ocupa su propia línea; la etiqueta y el enlace bajan */}
                  <div className="min-w-0 flex-1 basis-48">
                    <p className="text-lg font-semibold">
                      {TIPO_UNIDAD[u.tipo]} {u.etiqueta}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {[u.coefficient && `Coeficiente ${coeficienteTexto(u.coefficient)}`, u.area_m2 && `${Number(u.area_m2).toLocaleString("es-CO")} m²`, ...u.anexos.map((a) => `${TIPO_UNIDAD[a.tipo]} ${a.etiqueta.split("-").slice(-2).join("-")}`)]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <OcupacionBadge ocupacion={u.ocupacion} />
                  <Link href={`/${tenant.tenant_slug}/mi-cuenta`} className="inline-flex items-center text-sm font-medium text-primary hover:underline">
                    Mi cuenta <ChevronRight className="size-4" />
                  </Link>
                  <Link href={`/${tenant.tenant_slug}/unidades/${u.id}`} className="inline-flex items-center text-sm font-medium text-primary hover:underline">
                    Ver detalle <ChevronRight className="size-4" />
                  </Link>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <Seccion titulo="Quiénes figuran en la unidad">
                    <ul className="divide-y">
                      {u.vinculos.map((v) => (
                        <li key={v.id} className="px-4 py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{v.persona.nombre_completo}</span>
                            <RelacionBadge relacion={v.relacion} />
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                            <MarcasVinculo v={v} />
                            <Telefono numero={v.persona.telefono} />
                          </div>
                        </li>
                      ))}
                    </ul>
                  </Seccion>
                  <div className="space-y-4">
                    {yo && (
                      <Seccion titulo="Mis datos">
                        <dl className="divide-y px-4 py-1">
                          <Fila k="Nombre" v={yo.persona.nombre_completo} />
                          {yo.persona.numero_documento && <Fila k="Documento" v={`${yo.persona.tipo_documento} ${yo.persona.numero_documento}`} />}
                          <Fila k="Celular" v={yo.persona.telefono ?? "—"} />
                          <Fila k="Correo" v={yo.persona.email ?? "—"} />
                          <Fila k="En la unidad desde" v={fechaCorta(yo.fecha_inicio)} />
                          {yo.persona.autoriza_datos_at && (
                            <Fila
                              k="Datos personales"
                              v={
                                <span className="inline-flex items-center gap-1 text-success">
                                  <ShieldCheck className="size-4" /> Autorizado
                                </span>
                              }
                            />
                          )}
                        </dl>
                      </Seccion>
                    )}
                    <Seccion titulo="Vehículos registrados" descripcion="Portería los reconoce como vehículos de residentes.">
                      {!u.vehiculos_lista.length ? (
                        <p className="px-4 py-3 text-sm text-muted-foreground">No tiene vehículos registrados.</p>
                      ) : (
                        <ul className="divide-y">
                          {u.vehiculos_lista.map((v) => (
                            <li key={v.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                              <Car className="size-4 text-muted-foreground" />
                              <span className="font-mono font-semibold tracking-wider">{v.placa}</span>
                              <span className="text-muted-foreground">
                                {TIPO_VEHICULO[v.tipo]}
                                {v.marca && ` · ${v.marca}`}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </Seccion>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
