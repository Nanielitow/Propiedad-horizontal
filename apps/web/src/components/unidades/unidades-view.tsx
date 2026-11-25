"use client";

import { Building, Car, ChevronLeft, ChevronRight, Download, FileSpreadsheet, Plus, Search, Upload, Users, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Kpi, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher } from "@/lib/api";
import {
  baseUnidades,
  coeficienteTexto,
  type Ocupacion,
  OCUPACION,
  puedeUnidades,
  type ResumenUnidades,
  TIPO_UNIDAD,
  type TipoUnidad,
  type UnidadesPagina,
} from "@/lib/unidades";
import { cn } from "@/lib/utils";

import { OcupacionBadge, Telefono, useRefrescarUnidades } from "./comunes";
import { UnidadFormDialog } from "./formularios";

const PAGE_SIZE = 50;
const FILTROS = ["texto", "torre", "tipo", "ocupacion", "sin_propietario"] as const;

export function UnidadesView() {
  const { tenant } = useTenant();
  const b = baseUnidades(tenant.tenant_id);
  const permitido = puedeUnidades(tenant.role, "verUnidades");
  const directorio = puedeUnidades(tenant.role, "directorio");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const refrescar = useRefrescarUnidades();
  const [busqueda, setBusqueda] = useState(params.get("texto") ?? "");
  const [nueva, setNueva] = useState(false);
  const page = Number(params.get("page") ?? 1);
  const verAnexos = !!params.get("anexos");

  function setParam(cambios: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambios)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    if (!("page" in cambios)) p.delete("page");
    router.replace(`${pathname}?${p}`, { scroll: false });
  }

  const consulta = useMemo(() => {
    const q = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    for (const k of FILTROS) {
      const v = params.get(k);
      if (v) q.set(k, v);
    }
    // Por defecto se ocultan parqueaderos y depósitos anexos (salvo que se filtre por ese tipo)
    if (!verAnexos && !params.get("tipo")) q.set("solo_principales", "true");
    if (params.get("inactivas")) q.set("incluir_inactivas", "true");
    return q.toString();
  }, [params, page, verAnexos]);

  const { data: resumen } = useSWR<ResumenUnidades>(permitido ? `${b}/resumen` : null, fetcher);
  const { data, isLoading } = useSWR<UnidadesPagina>(permitido ? `${b}?${consulta}` : null, fetcher, { keepPreviousData: true });
  const hayFiltros = FILTROS.some((k) => params.get(k));
  const paginas = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const ocupacion = params.get("ocupacion") as Ocupacion | null;
  const principales = resumen ? Object.values(resumen.por_ocupacion).reduce((a, n) => a + (n ?? 0), 0) : 0;

  if (!permitido) return <SinAcceso />;

  const coef = resumen?.coeficientes;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Unidades"
        description="Censo de la copropiedad: unidades, coeficientes, propietarios y residentes."
        actions={
          <>
            {puedeUnidades(tenant.role, "exportar") && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" className="hidden sm:inline-flex">
                    <Download className="size-4" /> Exportar
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem asChild>
                    <a href={`/api/proxy${b}/exportar?formato=xlsx`} download>
                      <FileSpreadsheet className="size-4" /> Censo en Excel
                    </a>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <a href={`/api/proxy${b}/exportar?formato=pdf`} download>
                      <Download className="size-4" /> Censo en PDF
                    </a>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            {puedeUnidades(tenant.role, "importar") && (
              <Button variant="outline" asChild className="hidden sm:inline-flex">
                <Link href={`/${tenant.tenant_slug}/unidades/importar`}>
                  <Upload className="size-4" /> Importar Excel
                </Link>
              </Button>
            )}
            {puedeUnidades(tenant.role, "gestionar") && (
              <Button onClick={() => setNueva(true)}>
                <Plus className="size-4" /> Nueva unidad
              </Button>
            )}
          </>
        }
      />

      <div className="space-y-4 p-4 sm:p-6">
        {/* Indicadores */}
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <Kpi
            titulo="Unidades"
            icono={Building}
            valor={resumen ? String(principales) : "—"}
            detalle={resumen && resumen.total > principales ? `+ ${resumen.total - principales} parqueaderos y depósitos` : undefined}
          />
          {coef ? (
            <Kpi
              titulo="Coeficientes"
              valor={`${Number(coef.suma).toLocaleString("es-CO", { maximumFractionDigits: 4 })} %`}
              destacado={!coef.cuadra}
              detalle={coef.cuadra ? "Suman 100 %, como exige la Ley 675" : coef.mensaje}
            />
          ) : (
            <Kpi titulo="Arrendadas" valor={resumen ? String(resumen.por_ocupacion.ARRENDADA ?? 0) : "—"} />
          )}
          {directorio ? (
            <Kpi
              titulo="Sin propietario registrado"
              valor={resumen ? String(resumen.sin_propietario) : "—"}
              destacado={!!resumen?.sin_propietario}
              detalle={resumen?.sin_propietario ? (
                <button type="button" className="font-medium text-primary hover:underline" onClick={() => setParam({ sin_propietario: "true" })}>
                  Ver cuáles
                </button>
              ) : "Todas tienen propietario"}
            />
          ) : (
            <Kpi titulo="Desocupadas" valor={resumen ? String(resumen.por_ocupacion.DESOCUPADA ?? 0) : "—"} />
          )}
          {directorio ? (
            <Kpi
              titulo="Personas en el directorio"
              icono={Users}
              valor={resumen?.personas != null ? String(resumen.personas) : "—"}
              detalle={resumen?.vehiculos != null ? (
                <span className="inline-flex items-center gap-1">
                  <Car className="size-3.5" /> {resumen.vehiculos} vehículos registrados
                </span>
              ) : undefined}
            />
          ) : (
            <Kpi titulo="Habitadas por propietario" valor={resumen ? String(resumen.por_ocupacion.PROPIETARIO ?? 0) : "—"} />
          )}
        </div>

        {/* Ocupación: chips que filtran */}
        {resumen && (
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por ocupación">
            {(Object.keys(OCUPACION) as Ocupacion[])
              .filter((o) => (resumen.por_ocupacion[o] ?? 0) > 0)
              .map((o) => (
                <button
                  key={o}
                  type="button"
                  onClick={() => setParam({ ocupacion: ocupacion === o ? null : o })}
                  aria-pressed={ocupacion === o}
                  className={cn(
                    "rounded-full border bg-card px-3 py-1 text-sm transition-colors hover:bg-accent",
                    ocupacion === o && "border-primary bg-accent font-medium",
                  )}
                >
                  {OCUPACION[o].label} <span className="ml-1 text-muted-foreground tabular-nums">{resumen.por_ocupacion[o]}</span>
                </button>
              ))}
          </div>
        )}

        {/* Filtros */}
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
              placeholder={directorio ? "Unidad, nombre, cédula, celular o placa" : "Unidad (ej. 2-301)"}
              className="pl-8"
              aria-label="Buscar unidades"
            />
          </form>
          {resumen && resumen.torres.length > 1 && (
            <select aria-label="Torre" value={params.get("torre") ?? ""} onChange={(e) => setParam({ torre: e.target.value || null })} className={cn(campoClase(), "w-36")}>
              <option value="">Todas las torres</option>
              {resumen.torres.map((t) => (
                <option key={t} value={t}>
                  Torre {t}
                </option>
              ))}
            </select>
          )}
          <select aria-label="Tipo" value={params.get("tipo") ?? ""} onChange={(e) => setParam({ tipo: e.target.value || null })} className={cn(campoClase(), "w-40")}>
            <option value="">Todo tipo</option>
            {(Object.keys(TIPO_UNIDAD) as TipoUnidad[])
              .filter((t) => !resumen || (resumen.por_tipo[t] ?? 0) > 0)
              .map((t) => (
                <option key={t} value={t}>
                  {TIPO_UNIDAD[t]}
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

        {/* Listado */}
        <div className="rounded-lg border bg-card">
          {isLoading && !data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : !data?.items.length ? (
            <Vacio
              icono={Building}
              titulo={hayFiltros ? "Ninguna unidad coincide con la búsqueda" : "Aún no hay unidades registradas"}
              texto={hayFiltros ? undefined : "Regístrelas una por una o cárguelas todas desde un Excel con «Importar Excel»."}
            />
          ) : (
            <>
              <Table className="hidden md:table">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-28">Unidad</TableHead>
                    {directorio && <TableHead>Propietario</TableHead>}
                    {directorio && <TableHead>Contacto</TableHead>}
                    <TableHead>Ocupación</TableHead>
                    {coef && <TableHead className="text-right">Coeficiente</TableHead>}
                    <TableHead>Anexos</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((u) => {
                    const href = `/${tenant.tenant_slug}/unidades/${u.id}`;
                    return (
                      <TableRow key={u.id} className={cn("cursor-pointer", !u.activa && "opacity-60")} onClick={() => router.push(href)}>
                        <TableCell>
                          <Link href={href} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                            {u.etiqueta}
                          </Link>
                          <p className="text-xs text-muted-foreground">
                            {TIPO_UNIDAD[u.tipo]}
                            {u.unidad_principal && ` de ${u.unidad_principal.etiqueta}`}
                            {!u.activa && " · desactivada"}
                          </p>
                        </TableCell>
                        {directorio && (
                          <TableCell className="max-w-56">
                            {u.propietarios.length ? (
                              <span className="line-clamp-2 text-sm">{u.propietarios.map((p) => p.nombre).join(", ")}</span>
                            ) : u.unidad_principal ? (
                              <span className="text-sm text-muted-foreground">—</span>
                            ) : (
                              <span className="text-sm text-warning">Sin propietario</span>
                            )}
                          </TableCell>
                        )}
                        {directorio && (
                          <TableCell>
                            {u.contacto ? (
                              <div className="text-sm">
                                <p className="truncate">{u.contacto.nombre}</p>
                                <Telefono numero={u.contacto.telefono} />
                              </div>
                            ) : (
                              <span className="text-sm text-muted-foreground">—</span>
                            )}
                          </TableCell>
                        )}
                        <TableCell>{!u.unidad_principal && <OcupacionBadge ocupacion={u.ocupacion} />}</TableCell>
                        {coef && <TableCell className="text-right text-sm tabular-nums">{u.coefficient ? coeficienteTexto(u.coefficient) : "—"}</TableCell>}
                        <TableCell className="text-sm text-muted-foreground">
                          {u.anexos.map((a) => a.etiqueta.split("-").slice(-2).join("-")).join(", ") || "—"}
                          {!!u.vehiculos && (
                            <span className="ml-2 inline-flex items-center gap-0.5" title={`${u.vehiculos} vehículo(s)`}>
                              <Car className="size-3.5" /> {u.vehiculos}
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>

              {/* Celular: tarjetas */}
              <ul className="divide-y md:hidden">
                {data.items.map((u) => (
                  <li key={u.id}>
                    <Link href={`/${tenant.tenant_slug}/unidades/${u.id}`} className="flex items-start gap-3 px-4 py-3 active:bg-accent">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">
                          {u.etiqueta} <span className="text-xs font-normal text-muted-foreground">· {TIPO_UNIDAD[u.tipo]}</span>
                        </p>
                        {directorio && (
                          <p className="truncate text-sm text-muted-foreground">
                            {u.propietarios.map((p) => p.nombre).join(", ") || (u.unidad_principal ? `Anexo de ${u.unidad_principal.etiqueta}` : "Sin propietario")}
                          </p>
                        )}
                        {!u.unidad_principal && (
                          <div className="mt-1.5">
                            <OcupacionBadge ocupacion={u.ocupacion} />
                          </div>
                        )}
                      </div>
                      {coef && u.coefficient && <span className="text-xs text-muted-foreground tabular-nums">{coeficienteTexto(u.coefficient)}</span>}
                    </Link>
                  </li>
                ))}
              </ul>

              <div className="flex items-center justify-between border-t px-4 py-2 text-sm text-muted-foreground">
                <span>
                  {data.total} {data.total === 1 ? "unidad" : "unidades"}
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
            <input type="checkbox" checked={verAnexos} onChange={(e) => setParam({ anexos: e.target.checked ? "1" : null })} className="size-3.5" />
            Mostrar parqueaderos y depósitos anexos
          </label>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={!!params.get("inactivas")} onChange={(e) => setParam({ inactivas: e.target.checked ? "1" : null })} className="size-3.5" />
            Incluir unidades desactivadas
          </label>
        </div>
      </div>

      <UnidadFormDialog
        tenantId={tenant.tenant_id}
        abierto={nueva}
        onCambio={setNueva}
        onGuardado={(u) => {
          void refrescar(tenant.tenant_id);
          router.push(`/${tenant.tenant_slug}/unidades/${u.id}`);
        }}
      />
    </div>
  );
}
