"use client";

import { ChevronLeft, ChevronRight, Contact, Pencil, Power, Search, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Fila } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, MotivoDialog, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher } from "@/lib/api";
import { fechaCorta } from "@/lib/recaudos";
import {
  baseTenant,
  type PersonaDetalle,
  type PersonasPagina,
  puedeUnidades,
  type Relacion,
  RELACION,
  TIPO_DOCUMENTO,
  TIPO_VEHICULO,
} from "@/lib/unidades";
import { cn } from "@/lib/utils";

import { MarcasVinculo, RelacionBadge, Telefono, useRefrescarUnidades } from "./comunes";
import { PersonaFormDialog } from "./formularios";

const PAGE_SIZE = 50;

export function DirectorioView() {
  const { tenant } = useTenant();
  const b = `${baseTenant(tenant.tenant_id)}/personas`;
  const permitido = puedeUnidades(tenant.role, "directorio");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [busqueda, setBusqueda] = useState(params.get("texto") ?? "");
  const page = Number(params.get("page") ?? 1);
  const abierta = params.get("persona");

  function setParam(cambios: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    if (!("page" in cambios) && !("persona" in cambios)) p.delete("page");
    router.replace(`${pathname}?${p}`, { scroll: false });
  }

  const consulta = useMemo(() => {
    const q = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    for (const k of ["texto", "relacion"]) {
      const v = params.get(k);
      if (v) q.set(k, v);
    }
    if (params.get("sin_unidad")) q.set("sin_unidad", "true");
    if (params.get("inactivas")) q.set("incluir_inactivas", "true");
    return q.toString();
  }, [params, page]);

  const { data, isLoading } = useSWR<PersonasPagina>(permitido ? `${b}?${consulta}` : null, fetcher, { keepPreviousData: true });
  const hayFiltros = ["texto", "relacion", "sin_unidad"].some((k) => params.get(k));
  const paginas = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const sensibles = tenant.role === "ADMIN" || tenant.role === "CONTABILIDAD";

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Directorio" description="Propietarios, arrendatarios, residentes y autorizados de la copropiedad." />

      <div className="space-y-4 p-4 sm:p-6">
        <div className="flex flex-wrap items-end gap-2">
          <form
            className="relative min-w-56 flex-1"
            onSubmit={(e) => {
              e.preventDefault();
              setParam({ texto: busqueda.trim() || null });
            }}
          >
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              onBlur={() => setParam({ texto: busqueda.trim() || null })}
              placeholder={sensibles ? "Nombre, cédula, celular o correo" : "Nombre o celular"}
              className="pl-8"
              aria-label="Buscar personas"
            />
          </form>
          <select aria-label="Relación" value={params.get("relacion") ?? ""} onChange={(e) => setParam({ relacion: e.target.value || null })} className={cn(campoClase(), "w-44")}>
            <option value="">Toda relación</option>
            {(Object.keys(RELACION) as Relacion[]).map((r) => (
              <option key={r} value={r}>
                {RELACION[r].label}s
              </option>
            ))}
          </select>
          {hayFiltros && (
            <Button
              variant="ghost"
              onClick={() => {
                setBusqueda("");
                router.replace(pathname, { scroll: false });
              }}
            >
              <X className="size-4" /> Limpiar
            </Button>
          )}
        </div>

        <div className="rounded-lg border bg-card">
          {isLoading && !data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : !data?.items.length ? (
            <Vacio
              icono={Contact}
              titulo={hayFiltros ? "Nadie coincide con la búsqueda" : "El directorio está vacío"}
              texto={hayFiltros ? undefined : "Las personas se agregan desde la ficha de cada unidad o importando un Excel."}
            />
          ) : (
            <>
              <Table className="hidden md:table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Nombre</TableHead>
                    <TableHead>Unidades</TableHead>
                    <TableHead>Relación</TableHead>
                    <TableHead>Celular</TableHead>
                    {sensibles && <TableHead>Documento</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((p) => (
                    <TableRow key={p.id} className={cn("cursor-pointer", !p.activa && "opacity-60")} onClick={() => setParam({ persona: p.id })}>
                      <TableCell>
                        <span className="font-medium">{p.nombre_completo}</span>
                        {p.tiene_cuenta && (
                          <span className="ml-2 align-middle">
                            <Etiqueta tono="info">Cuenta</Etiqueta>
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-sm">{p.unidades.map((u) => u.etiqueta).join(", ") || <span className="text-muted-foreground">Sin unidad vigente</span>}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {p.relaciones.map((r) => (
                            <RelacionBadge key={r} relacion={r} />
                          ))}
                        </div>
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Telefono numero={p.telefono} />
                      </TableCell>
                      {sensibles && (
                        <TableCell className="text-sm text-muted-foreground tabular-nums">{p.numero_documento ? `${p.tipo_documento} ${p.numero_documento}` : "—"}</TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <ul className="divide-y md:hidden">
                {data.items.map((p) => (
                  <li key={p.id}>
                    <button type="button" onClick={() => setParam({ persona: p.id })} className="w-full px-4 py-3 text-left active:bg-accent">
                      <p className="font-medium">{p.nombre_completo}</p>
                      <p className="text-sm text-muted-foreground">
                        {p.unidades.map((u) => u.etiqueta).join(", ") || "Sin unidad vigente"} · {p.relaciones.map((r) => RELACION[r].label).join(", ")}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="flex items-center justify-between border-t px-4 py-2 text-sm text-muted-foreground">
                <span>
                  {data.total} {data.total === 1 ? "persona" : "personas"}
                  {paginas > 1 && ` · página ${page} de ${paginas}`}
                </span>
                {paginas > 1 && (
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" disabled={page <= 1} onClick={() => setParam({ page: String(page - 1) })} aria-label="Página anterior">
                      <ChevronLeft className="size-4" />
                    </Button>
                    <Button variant="ghost" size="icon" disabled={page >= paginas} onClick={() => setParam({ page: String(page + 1) })} aria-label="Página siguiente">
                      <ChevronRight className="size-4" />
                    </Button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={!!params.get("sin_unidad")} onChange={(e) => setParam({ sin_unidad: e.target.checked ? "1" : null })} className="size-3.5" />
            Solo personas sin unidad vigente (exarrendatarios, vendedores)
          </label>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={!!params.get("inactivas")} onChange={(e) => setParam({ inactivas: e.target.checked ? "1" : null })} className="size-3.5" />
            Incluir desactivadas
          </label>
        </div>
      </div>

      <PersonaSheet personaId={abierta} onCerrar={() => setParam({ persona: null })} />
    </div>
  );
}

function PersonaSheet({ personaId, onCerrar }: { personaId: string | null; onCerrar: () => void }) {
  const { tenant } = useTenant();
  const clave = personaId ? `${baseTenant(tenant.tenant_id)}/personas/${personaId}` : null;
  const { data: p, mutate } = useSWR<PersonaDetalle>(clave, fetcher);
  const refrescar = useRefrescarUnidades();
  const gestionar = puedeUnidades(tenant.role, "gestionar");
  const [editar, setEditar] = useState(false);
  const [desactivar, setDesactivar] = useState(false);
  const vigentes = p?.vinculos.filter((v) => !v.fecha_fin) ?? [];
  const anteriores = p?.vinculos.filter((v) => v.fecha_fin) ?? [];

  return (
    <Sheet open={!!personaId} onOpenChange={(v) => !v && onCerrar()}>
      <SheetContent className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-lg">
        {!p ? (
          <div className="space-y-3 p-4">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-32" />
          </div>
        ) : (
          <>
            <SheetHeader>
              <SheetTitle className="flex flex-wrap items-center gap-2">
                {p.nombre_completo}
                {!p.activa && <Etiqueta tono="danger">Desactivada</Etiqueta>}
              </SheetTitle>
              <SheetDescription>{vigentes.length ? vigentes.map((v) => `${RELACION[v.relacion].label} de ${v.unidad.etiqueta}`).join(" · ") : "Sin unidad vigente"}</SheetDescription>
            </SheetHeader>
            <div className="space-y-5 px-4 pb-6">
              {gestionar && p.activa && (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setEditar(true)}>
                    <Pencil className="size-4" /> Editar datos
                  </Button>
                  {!vigentes.length && (
                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setDesactivar(true)}>
                      <Power className="size-4" /> Desactivar
                    </Button>
                  )}
                </div>
              )}
              <dl className="divide-y rounded-lg border px-3">
                <Fila k="Celular" v={p.telefono ? <Telefono numero={p.telefono} /> : "—"} />
                {p.telefono_alterno && <Fila k="Teléfono alterno" v={<Telefono numero={p.telefono_alterno} />} />}
                {p.email !== null && <Fila k="Correo" v={p.email || "—"} />}
                {p.numero_documento !== null && <Fila k={p.tipo_documento ? TIPO_DOCUMENTO[p.tipo_documento] : "Documento"} v={p.numero_documento} />}
                {p.autoriza_datos_at !== null ? (
                  <Fila
                    k="Datos personales"
                    v={
                      <span className="inline-flex items-center gap-1 text-success">
                        <ShieldCheck className="size-4" /> Autorizó el {fechaCorta(p.autoriza_datos_at)}
                      </span>
                    }
                  />
                ) : (
                  (tenant.role === "ADMIN" || tenant.role === "CONTABILIDAD") && <Fila k="Datos personales" v={<span className="text-warning">Sin autorización registrada</span>} />
                )}
                {p.tiene_cuenta && <Fila k="Cuenta en la plataforma" v="Sí" />}
                {p.notas && <Fila k="Notas" v={p.notas} />}
              </dl>

              <section>
                <h3 className="mb-2 text-sm font-semibold">Unidades</h3>
                {!vigentes.length ? (
                  <p className="text-sm text-muted-foreground">No figura en ninguna unidad actualmente.</p>
                ) : (
                  <ul className="space-y-2">
                    {vigentes.map((v) => (
                      <li key={v.id} className="rounded-lg border p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <Link href={`/${tenant.tenant_slug}/unidades/${v.unidad.id}`} className="font-medium text-primary hover:underline">
                            {v.unidad.etiqueta}
                          </Link>
                          <RelacionBadge relacion={v.relacion} />
                        </div>
                        <div className="mt-1 flex flex-wrap gap-2 text-xs">
                          <MarcasVinculo v={v} />
                          <span className="text-muted-foreground">Desde {fechaCorta(v.fecha_inicio)}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {p.vehiculos.length > 0 && (
                <section>
                  <h3 className="mb-2 text-sm font-semibold">Vehículos</h3>
                  <ul className="space-y-1 text-sm">
                    {p.vehiculos.map((v) => (
                      <li key={v.id} className={cn(!v.activo && "text-muted-foreground line-through")}>
                        <span className="font-mono font-medium">{v.placa}</span> · {TIPO_VEHICULO[v.tipo]}
                        {v.marca && ` · ${v.marca}`} · {v.unidad.etiqueta}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {anteriores.length > 0 && (
                <section>
                  <h3 className="mb-2 text-sm font-semibold">Historial</h3>
                  <ul className="space-y-1 text-sm text-muted-foreground">
                    {anteriores.map((v) => (
                      <li key={v.id}>
                        {RELACION[v.relacion].label} de {v.unidad.etiqueta} · {fechaCorta(v.fecha_inicio)} → {v.fecha_fin && fechaCorta(v.fecha_fin)}
                        {v.motivo_cierre && ` · ${v.motivo_cierre}`}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>

            {gestionar && (
              <>
                <PersonaFormDialog
                  tenantId={tenant.tenant_id}
                  abierto={editar}
                  onCambio={setEditar}
                  persona={p}
                  onGuardado={(nueva) => {
                    void mutate(nueva, { revalidate: false });
                    void refrescar(tenant.tenant_id);
                  }}
                />
                <MotivoDialog
                  abierto={desactivar}
                  onCambio={setDesactivar}
                  titulo={`Desactivar a ${p.nombre_completo}`}
                  descripcion="Deja de aparecer en el directorio. No se borra: su historial se conserva."
                  boton="Desactivar"
                  minimo={5}
                  onConfirmar={async (motivo) => {
                    const r = await api<PersonaDetalle>(`${baseTenant(tenant.tenant_id)}/personas/${p.id}/desactivar`, { method: "POST", json: { motivo } });
                    void mutate(r, { revalidate: false });
                    void refrescar(tenant.tenant_id);
                    toast.success("Persona desactivada");
                  }}
                />
              </>
            )}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
