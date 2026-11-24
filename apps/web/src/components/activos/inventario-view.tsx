"use client";

import { ChevronLeft, ChevronRight, MessageSquareWarning, Plus, Printer, Search, Wrench, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher } from "@/lib/api";
import {
  type ActivosPagina,
  baseActivos,
  type Categoria,
  type Color,
  CRITICIDAD,
  type Criticidad,
  ESTADO_ACTIVO,
  type EstadoActivo,
  puedeActivos,
  SEMAFORO,
} from "@/lib/activos";
import { fechaCorta } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { CriticidadBadge, EstadoActivoBadge, SemaforoBadge, SemaforoPunto, useRefrescarActivos } from "./comunes";
import { ActivoFormDialog } from "./formularios-activo";

const PAGE_SIZE = 25;
const FILTROS = ["texto", "categoria_id", "estado", "criticidad", "semaforo"] as const;

export function InventarioView() {
  const { tenant } = useTenant();
  const b = baseActivos(tenant.tenant_id);
  const permitido = puedeActivos(tenant.role, "ver");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const refrescar = useRefrescarActivos();
  const [busqueda, setBusqueda] = useState(params.get("texto") ?? "");
  const [nuevo, setNuevo] = useState(false);
  const page = Number(params.get("page") ?? 1);

  const { data: categorias } = useSWR<Categoria[]>(permitido ? `${b}/categorias` : null, fetcher);

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
    if (params.get("bajas")) q.set("incluir_bajas", "true");
    return q.toString();
  }, [params, page]);

  const { data, isLoading } = useSWR<ActivosPagina>(permitido ? `${b}?${consulta}` : null, fetcher, { keepPreviousData: true });
  const hayFiltros = FILTROS.some((k) => params.get(k));
  const paginas = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const semaforo = params.get("semaforo") as Color | null;
  const urlEtiquetas = `/api/proxy${b}/etiquetas.pdf`;

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Activos"
        description="Equipos e infraestructura con su hoja de vida y el semáforo de mantenimiento."
        actions={
          <>
            <Button variant="outline" asChild className="hidden sm:inline-flex">
              <a href={urlEtiquetas} download>
                <Printer className="size-4" /> Etiquetas QR
              </a>
            </Button>
            {puedeActivos(tenant.role, "crearActivo") && (
              <Button onClick={() => setNuevo(true)}>
                <Plus className="size-4" /> Nuevo activo
              </Button>
            )}
          </>
        }
      />

      <div className="space-y-4 p-4 sm:p-6">
        {/* Resumen del semáforo: cada tarjeta filtra */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {(["ROJO", "AMARILLO", "VERDE"] as Color[]).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setParam({ semaforo: semaforo === c ? null : c })}
              aria-pressed={semaforo === c}
              className={cn(
                "rounded-lg border bg-card p-3 text-left transition-colors hover:bg-accent/50",
                semaforo === c && "border-primary ring-2 ring-primary/20",
              )}
            >
              <span className="flex items-center gap-2 text-sm text-muted-foreground">
                <SemaforoPunto color={c} /> {c === "ROJO" ? "Con mantenimiento vencido" : c === "AMARILLO" ? "Vencen en 15 días" : "Al día"}
              </span>
              <span className="mt-1 block text-2xl font-semibold tabular-nums">{data?.por_semaforo[c] ?? "—"}</span>
            </button>
          ))}
          <div className="rounded-lg border bg-card p-3">
            <span className="flex items-center gap-2 text-sm text-muted-foreground">
              <Wrench className="size-3.5" /> Fuera de servicio
            </span>
            <span className={cn("mt-1 block text-2xl font-semibold tabular-nums", (data?.por_estado.FUERA_DE_SERVICIO ?? 0) > 0 && "text-destructive")}>
              {data ? (data.por_estado.FUERA_DE_SERVICIO ?? 0) : "—"}
            </span>
          </div>
        </div>

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
              placeholder="Nombre, código, marca, modelo o serie"
              className="pl-8"
              aria-label="Buscar activos"
            />
          </form>
          <select aria-label="Categoría" value={params.get("categoria_id") ?? ""} onChange={(e) => setParam({ categoria_id: e.target.value || null })} className={cn(campoClase(), "w-52")}>
            <option value="">Todas las categorías</option>
            {categorias?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
          </select>
          <select aria-label="Estado" value={params.get("estado") ?? ""} onChange={(e) => setParam({ estado: e.target.value || null })} className={cn(campoClase(), "w-44")}>
            <option value="">Todo estado</option>
            {(Object.keys(ESTADO_ACTIVO) as EstadoActivo[]).map((e) => (
              <option key={e} value={e}>
                {ESTADO_ACTIVO[e].label}
              </option>
            ))}
          </select>
          <select aria-label="Criticidad" value={params.get("criticidad") ?? ""} onChange={(e) => setParam({ criticidad: e.target.value || null })} className={cn(campoClase(), "w-40")}>
            <option value="">Toda criticidad</option>
            {(Object.keys(CRITICIDAD) as Criticidad[]).map((c) => (
              <option key={c} value={c}>
                {CRITICIDAD[c].label}
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
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : !data?.items.length ? (
            <Vacio
              icono={Wrench}
              titulo={hayFiltros ? "Ningún activo coincide con los filtros" : "Aún no hay activos registrados"}
              texto={hayFiltros ? undefined : "Registre los equipos e infraestructura para llevar su hoja de vida y su plan de mantenimiento."}
            />
          ) : (
            <>
              {/* Escritorio: tabla */}
              <Table className="hidden md:table">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-24">Código</TableHead>
                    <TableHead>Activo</TableHead>
                    <TableHead>Ubicación</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Mantenimiento</TableHead>
                    <TableHead className="text-right">Novedades</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((a) => (
                    <TableRow key={a.id} className="cursor-pointer" onClick={() => router.push(`/${tenant.tenant_slug}/activos/${a.id}`)}>
                      <TableCell className="font-mono text-xs text-muted-foreground">{a.codigo_interno}</TableCell>
                      <TableCell>
                        <Link href={`/${tenant.tenant_slug}/activos/${a.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                          {a.nombre}
                        </Link>
                        <p className="text-xs text-muted-foreground">
                          {a.subtipo ?? a.categoria.nombre}
                          {a.criticidad === "ALTA" && " · criticidad alta"}
                        </p>
                      </TableCell>
                      <TableCell className="max-w-56 truncate text-sm text-muted-foreground">{a.ubicacion}</TableCell>
                      <TableCell>
                        <EstadoActivoBadge estado={a.estado} />
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col items-start gap-0.5">
                          <SemaforoBadge color={a.semaforo} />
                          {a.proxima_fecha && <span className="text-xs text-muted-foreground">{fechaCorta(a.proxima_fecha)}</span>}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        {a.novedades_abiertas > 0 ? (
                          <span className="inline-flex items-center gap-1 text-sm font-medium text-warning">
                            <MessageSquareWarning className="size-4" /> {a.novedades_abiertas}
                          </span>
                        ) : (
                          <span className="text-sm text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Celular: tarjetas */}
              <ul className="divide-y md:hidden">
                {data.items.map((a) => (
                  <li key={a.id}>
                    <Link href={`/${tenant.tenant_slug}/activos/${a.id}`} className="flex items-start gap-3 px-4 py-3 active:bg-accent">
                      <SemaforoPunto color={a.semaforo} className="mt-1.5" />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">{a.nombre}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {a.codigo_interno} · {a.ubicacion}
                        </p>
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {a.estado !== "OPERATIVO" && <EstadoActivoBadge estado={a.estado} />}
                          {a.semaforo && a.semaforo !== "VERDE" && <SemaforoBadge color={a.semaforo} texto={`${SEMAFORO[a.semaforo].label}${a.proxima_fecha ? ` · ${fechaCorta(a.proxima_fecha)}` : ""}`} />}
                          {a.criticidad === "ALTA" && <CriticidadBadge criticidad="ALTA" />}
                          {a.novedades_abiertas > 0 && (
                            <span className="inline-flex items-center gap-1 text-xs font-medium text-warning">
                              <MessageSquareWarning className="size-3.5" /> {a.novedades_abiertas}
                            </span>
                          )}
                        </div>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>

              {paginas > 1 && (
                <div className="flex items-center justify-between border-t px-4 py-2 text-sm text-muted-foreground">
                  <span>
                    {data.total} activos · página {page} de {paginas}
                  </span>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" disabled={page <= 1} onClick={() => setParam({ page: String(page - 1) })} aria-label="Página anterior">
                      <ChevronLeft className="size-4" />
                    </Button>
                    <Button variant="ghost" size="icon" disabled={page >= paginas} onClick={() => setParam({ page: String(page + 1) })} aria-label="Página siguiente">
                      <ChevronRight className="size-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={!!params.get("bajas")} onChange={(e) => setParam({ bajas: e.target.checked ? "1" : null })} className="size-3.5" />
          Incluir activos dados de baja
        </label>
      </div>

      <ActivoFormDialog
        tenantId={tenant.tenant_id}
        abierto={nuevo}
        onCambio={setNuevo}
        onGuardado={(a) => {
          void refrescar(tenant.tenant_id);
          router.push(`/${tenant.tenant_slug}/activos/${a.id}`);
        }}
      />
    </div>
  );
}
