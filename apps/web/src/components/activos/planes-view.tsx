"use client";

import { CalendarClock, Check, Pencil, Phone, Plus, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Etiqueta, mensajeError, Seccion, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher } from "@/lib/api";
import { baseActivos, type Contratista, type ContratistaDetalle, PERIODICIDAD, type Plan, puedeActivos } from "@/lib/activos";
import { fechaCorta, hoyBogota, pesos } from "@/lib/recaudos";

import { Fila, useRefrescarActivos } from "./comunes";
import { ContratistaFormDialog } from "./formularios-activo";
import { PlanFormDialog } from "./formularios-plan";

function periodicidad(p: Plan) {
  return p.periodicidad === "POR_HORAS_USO" ? `Cada ${p.intervalo_horas} h` : PERIODICIDAD[p.periodicidad];
}

export function PlanesView() {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const permitido = puedeActivos(tenant.role, "crearPlan") || puedeActivos(tenant.role, "ver");
  const refrescar = useRefrescarActivos();
  const { data } = useSWR<Plan[]>(permitido ? `${b}/planes` : null, fetcher);
  const [nuevo, setNuevo] = useState(false);

  if (!permitido) return <SinAcceso />;

  const pendientes = data?.filter((p) => !p.aprobado && p.activo_plan) ?? [];
  const activos = data?.filter((p) => p.aprobado && p.activo_plan) ?? [];
  const pausados = data?.filter((p) => !p.activo_plan) ?? [];
  const costoAnual = activos.reduce((s, p) => {
    const veces: Record<string, number> = { SEMANAL: 52, QUINCENAL: 24, MENSUAL: 12, BIMESTRAL: 6, TRIMESTRAL: 4, SEMESTRAL: 2, ANUAL: 1, POR_HORAS_USO: 4 };
    return s + Number(p.costo_estimado ?? 0) * (veces[p.periodicidad] ?? 1);
  }, 0);

  async function aprobar(p: Plan) {
    try {
      await api(`${b}/planes/${p.id}/aprobar`, { method: "POST" });
      toast.success("Plan aprobado: se programaron los próximos 12 meses");
      await refrescar(tenant.tenant_id);
    } catch (e) {
      toast.error(mensajeError(e));
    }
  }

  const tabla = (lista: Plan[]) => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Activo</TableHead>
          <TableHead>Plan</TableHead>
          <TableHead className="hidden md:table-cell">Periodicidad</TableHead>
          <TableHead className="hidden lg:table-cell">Lo ejecuta</TableHead>
          <TableHead className="hidden sm:table-cell">Próxima</TableHead>
          {tenant.role === "ADMIN" || tenant.role === "CONTABILIDAD" ? <TableHead className="hidden text-right lg:table-cell">Costo por vez</TableHead> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {lista.map((p) => (
          <TableRow key={p.id}>
            <TableCell>
              <Link href={`/${tenant.tenant_slug}/activos/${p.activo.id}`} className="font-medium hover:underline">
                {p.activo.nombre}
              </Link>
              <p className="font-mono text-xs text-muted-foreground">{p.activo_codigo}</p>
            </TableCell>
            <TableCell className="text-sm">{p.nombre}</TableCell>
            <TableCell className="hidden text-sm text-muted-foreground md:table-cell">{periodicidad(p)}</TableCell>
            <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">{p.contratista?.nombre ?? "Personal interno"}</TableCell>
            <TableCell className="hidden text-sm tabular-nums sm:table-cell">{p.proxima_fecha ? fechaCorta(p.proxima_fecha) : "—"}</TableCell>
            {tenant.role === "ADMIN" || tenant.role === "CONTABILIDAD" ? (
              <TableCell className="hidden text-right text-sm tabular-nums lg:table-cell">{pesos(p.costo_estimado)}</TableCell>
            ) : null}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Planes de mantenimiento"
        description="Las reglas de mantenimiento preventivo de todos los activos."
        actions={
          puedeActivos(tenant.role, "crearPlan") && (
            <Button onClick={() => setNuevo(true)}>
              <Plus className="size-4" /> Nuevo plan
            </Button>
          )
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        {!data ? (
          <Skeleton className="h-64" />
        ) : (
          <>
            {pendientes.length > 0 && (
              <Seccion titulo="Pendientes de aprobación" descripcion="Propuestos por recepción; al aprobarlos se programan sus fechas.">
                <ul className="divide-y">
                  {pendientes.map((p) => (
                    <li key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">
                          {p.activo_codigo} {p.activo.nombre} · {p.nombre}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {periodicidad(p)} desde el {fechaCorta(p.fecha_inicio)} · {p.contratista?.nombre ?? "Personal interno"}
                          {p.costo_estimado && ` · ${pesos(p.costo_estimado)} por vez`}
                        </p>
                      </div>
                      {puedeActivos(tenant.role, "aprobarPlan") ? (
                        <Button size="sm" onClick={() => void aprobar(p)}>
                          <Check className="size-4" /> Aprobar
                        </Button>
                      ) : (
                        <Etiqueta tono="warning">Esperando a la administración</Etiqueta>
                      )}
                    </li>
                  ))}
                </ul>
              </Seccion>
            )}
            <Seccion
              titulo={`Planes activos (${activos.length})`}
              acciones={
                (tenant.role === "ADMIN" || tenant.role === "CONTABILIDAD") && costoAnual > 0 ? (
                  <span className="text-xs text-muted-foreground">Costo anual estimado: {pesos(costoAnual)}</span>
                ) : undefined
              }
            >
              {activos.length ? tabla(activos) : <Vacio icono={CalendarClock} titulo="Aún no hay planes activos" />}
            </Seccion>
            {pausados.length > 0 && <Seccion titulo={`Pausados (${pausados.length})`}>{tabla(pausados)}</Seccion>}
          </>
        )}
      </div>
      <PlanFormDialog tenantId={tenant.tenant_id} rol={tenant.role} abierto={nuevo} onCambio={setNuevo} onGuardado={() => void refrescar(tenant.tenant_id)} />
    </div>
  );
}

export function ContratistasView() {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const permitido = puedeActivos(tenant.role, "contratistas");
  const gestiona = puedeActivos(tenant.role, "gestionarContratistas");
  const refrescar = useRefrescarActivos();
  const { data } = useSWR<Contratista[]>(permitido ? `${b}/contratistas?incluir_inactivos=true` : null, fetcher);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [editar, setEditar] = useState<Contratista | null | undefined>(undefined);
  const { data: detalle } = useSWR<ContratistaDetalle>(abierto ? `${b}/contratistas/${abierto}` : null, fetcher);
  const hoy = hoyBogota();

  if (!permitido) return <SinAcceso />;

  const dias = (fin: string | null) => (fin ? Math.round((Date.parse(fin) - Date.parse(hoy)) / 86_400_000) : null);

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Contratistas"
        description="Empresas que mantienen los equipos, con sus contratos e intervenciones."
        actions={
          gestiona && (
            <Button onClick={() => setEditar(null)}>
              <Plus className="size-4" /> Nuevo contratista
            </Button>
          )
        }
      />
      <div className="p-4 sm:p-6">
        <div className="rounded-lg border bg-card">
          {!data ? (
            <Skeleton className="m-4 h-40" />
          ) : data.length === 0 ? (
            <Vacio icono={Users} titulo="Sin contratistas registrados" />
          ) : (
            <ul className="divide-y">
              {data.map((c) => {
                const d = dias(c.vigencia_contrato_fin);
                return (
                  <li key={c.id}>
                    <button type="button" onClick={() => setAbierto(c.id)} className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left hover:bg-accent/40">
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium">{c.razon_social}</span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {c.especialidades.join(", ") || "Sin especialidades"}
                          {c.nit && ` · NIT ${c.nit}`}
                        </span>
                      </span>
                      {!c.activo ? (
                        <Etiqueta tono="neutral">Inactivo</Etiqueta>
                      ) : d === null ? (
                        <Etiqueta tono="neutral">Por servicio</Etiqueta>
                      ) : d < 0 ? (
                        <Etiqueta tono="danger">Contrato vencido</Etiqueta>
                      ) : d <= 60 ? (
                        <Etiqueta tono="warning">Contrato vence en {d} días</Etiqueta>
                      ) : (
                        <Etiqueta tono="success">Vigente hasta {fechaCorta(c.vigencia_contrato_fin!)}</Etiqueta>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      <Sheet open={!!abierto} onOpenChange={(v) => !v && setAbierto(null)}>
        <SheetContent className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-md">
          {detalle ? (
            <>
              <SheetHeader>
                <SheetTitle>{detalle.razon_social}</SheetTitle>
                <SheetDescription>{detalle.especialidades.join(" · ")}</SheetDescription>
              </SheetHeader>
              <div className="space-y-4 px-4 pb-6">
                <dl className="divide-y">
                  <Fila k="NIT" v={detalle.nit} />
                  <Fila k="Contacto" v={detalle.contacto_nombre} />
                  <Fila
                    k="Teléfono"
                    v={
                      detalle.telefono ? (
                        <a href={`tel:${detalle.telefono.replace(/\s/g, "")}`} className="inline-flex items-center gap-1 text-primary hover:underline">
                          <Phone className="size-3.5" /> {detalle.telefono}
                        </a>
                      ) : null
                    }
                  />
                  <Fila k="Correo" v={detalle.email} />
                  <Fila
                    k="Contrato"
                    v={detalle.vigencia_contrato_fin ? `${detalle.vigencia_contrato_inicio ? fechaCorta(detalle.vigencia_contrato_inicio) : "?"} – ${fechaCorta(detalle.vigencia_contrato_fin)}` : "Por servicio"}
                  />
                  <Fila k="Periodicidad pactada" v={detalle.periodicidad_pactada} />
                  {detalle.valor_contrato !== null && <Fila k="Valor anual" v={pesos(detalle.valor_contrato)} />}
                  <Fila k="Intervenciones" v={`${detalle.mantenimientos} (${detalle.correctivos} correctivas)`} />
                  {detalle.costo_total !== null && <Fila k="Facturado en mantenimientos" v={pesos(detalle.costo_total)} />}
                </dl>
                {detalle.alcance_contrato && <p className="text-sm text-muted-foreground">{detalle.alcance_contrato}</p>}
                {detalle.activos.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs font-medium text-muted-foreground">Activos a su cargo</p>
                    <ul className="space-y-1">
                      {detalle.activos.map((a) => (
                        <li key={a.id}>
                          <Link href={`/${tenant.tenant_slug}/activos/${a.id}`} className="text-sm text-primary hover:underline">
                            {a.nombre}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {gestiona && (
                  <Button variant="outline" size="sm" onClick={() => setEditar(detalle)}>
                    <Pencil className="size-4" /> Editar
                  </Button>
                )}
              </div>
            </>
          ) : (
            <Skeleton className="m-4 h-64" />
          )}
        </SheetContent>
      </Sheet>
      <ContratistaFormDialog
        tenantId={tenant.tenant_id}
        abierto={editar !== undefined}
        onCambio={(v) => !v && setEditar(undefined)}
        contratista={editar ?? undefined}
        onGuardado={() => void refrescar(tenant.tenant_id)}
      />
    </div>
  );
}
