"use client";

import { ChevronLeft, ChevronRight, Paperclip, Plus, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher } from "@/lib/api";
import {
  base,
  type Concepto,
  ESTADO,
  ESTADOS_ORDEN,
  fechaHora,
  MEDIO,
  type MedioPago,
  pesos,
  puede,
  type RecaudosPagina,
} from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { campoClase, EstadoBadge, SinAcceso, Vacio } from "./comunes";
import { RecaudoDetalleSheet } from "./recaudo-detalle";

const PAGE_SIZE = 25;
const FILTROS = ["desde", "hasta", "concepto_id", "medio_pago", "estado", "q"] as const;

export function MovimientosView() {
  const { tenant } = useTenant();
  const b = base(tenant.tenant_id);
  const permitido = puede(tenant.role, "movimientos");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [busqueda, setBusqueda] = useState(params.get("q") ?? "");

  const { data: conceptos } = useSWR<Concepto[]>(permitido ? `${b}/conceptos?incluir_inactivos=true` : null, fetcher);
  const page = Number(params.get("page") ?? 1);
  const abierto = params.get("id");

  // Los filtros viven en la URL: se pueden compartir y sobreviven a recargar la página
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
    for (const k of ["desde", "hasta", "concepto_id", "medio_pago", "estado"] as const) {
      const v = params.get(k);
      if (v) q.set(k, v);
    }
    const texto = params.get("q")?.trim();
    if (texto) {
      // Un texto corto de letras+números parece una placa; un número, un consecutivo; si no, el pagador
      if (/^\d{1,7}$/.test(texto)) q.set("consecutivo", texto);
      else if (/^[A-Za-z]{3}[\s-]?\d{2}[0-9A-Za-z]?$/.test(texto)) q.set("placa", texto);
      else q.set("pagador", texto);
    }
    return q.toString();
  }, [params, page]);

  const { data, isLoading, mutate } = useSWR<RecaudosPagina>(permitido ? `${b}?${consulta}` : null, fetcher, {
    keepPreviousData: true,
  });
  const hayFiltros = FILTROS.some((k) => params.get(k));
  const paginas = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Movimientos"
        description={tenant.role === "AUXILIAR" ? "Los recaudos que usted ha recibido." : "Todos los recaudos de la copropiedad, con su estado del dinero."}
        actions={
          puede(tenant.role, "registrar") && (
            <Button asChild>
              <Link href={`/${tenant.tenant_slug}/recaudos/nuevo`}>
                <Plus className="size-4" /> Registrar
              </Link>
            </Button>
          )
        }
      />

      <div className="space-y-4 p-4 sm:p-6">
        {/* Filtros: una sola fila, combinables */}
        <div className="flex flex-wrap items-end gap-2">
          <form
            className="relative min-w-56 flex-1"
            onSubmit={(e) => {
              e.preventDefault();
              setParam({ q: busqueda.trim() || null });
            }}
          >
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              onBlur={() => setParam({ q: busqueda.trim() || null })}
              placeholder="Pagador, cédula, placa o n.° de recaudo"
              className="pl-8"
              aria-label="Buscar"
            />
          </form>
          <label className="flex flex-col text-xs text-muted-foreground">
            Desde
            <input type="date" value={params.get("desde") ?? ""} onChange={(e) => setParam({ desde: e.target.value || null })} className={cn(campoClase(), "mt-1 w-36")} />
          </label>
          <label className="flex flex-col text-xs text-muted-foreground">
            Hasta
            <input type="date" value={params.get("hasta") ?? ""} onChange={(e) => setParam({ hasta: e.target.value || null })} className={cn(campoClase(), "mt-1 w-36")} />
          </label>
          <select aria-label="Concepto" value={params.get("concepto_id") ?? ""} onChange={(e) => setParam({ concepto_id: e.target.value || null })} className={cn(campoClase(), "w-48")}>
            <option value="">Todos los conceptos</option>
            {conceptos?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
          </select>
          <select aria-label="Medio de pago" value={params.get("medio_pago") ?? ""} onChange={(e) => setParam({ medio_pago: e.target.value || null })} className={cn(campoClase(), "w-40")}>
            <option value="">Todo medio</option>
            {(Object.keys(MEDIO) as MedioPago[]).map((m) => (
              <option key={m} value={m}>
                {MEDIO[m]}
              </option>
            ))}
          </select>
          <select aria-label="Estado del dinero" value={params.get("estado") ?? ""} onChange={(e) => setParam({ estado: e.target.value || null })} className={cn(campoClase(), "w-44")}>
            <option value="">Todo estado</option>
            {ESTADOS_ORDEN.map((e) => (
              <option key={e} value={e}>
                {ESTADO[e].label}
              </option>
            ))}
          </select>
          {hayFiltros && (
            <Button
              variant="ghost"
              size="sm"
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
          <div className="flex items-center justify-between gap-2 border-b px-4 py-2.5 text-sm">
            <span className="text-muted-foreground">
              {data ? `${data.total.toLocaleString("es-CO")} ${data.total === 1 ? "movimiento" : "movimientos"}` : "Cargando…"}
            </span>
            {data && (
              <span>
                Total (sin anulados): <span className="font-semibold tabular-nums">{pesos(data.suma)}</span>
              </span>
            )}
          </div>

          {isLoading && !data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-9" />
              ))}
            </div>
          ) : !data?.items.length ? (
            <Vacio icono={Search} titulo={hayFiltros ? "Ningún movimiento coincide con los filtros" : "Aún no hay recaudos registrados"} />
          ) : (
            <>
            {/* Celular: lista compacta con lo esencial (valor y estado siempre visibles) */}
            <ul className="divide-y md:hidden">
              {data.items.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => setParam({ id: r.id, page: String(page) })}
                    className={cn("flex w-full items-start justify-between gap-3 px-4 py-3 text-left", r.estado === "ANULADO" && "text-muted-foreground")}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        #{r.consecutivo} · {r.concepto}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {fechaHora(r.fecha_recaudo)} · {r.placa ?? r.nombre_pagador}
                      </span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <span className={cn("text-sm font-semibold tabular-nums", r.estado === "ANULADO" && "line-through")}>{pesos(r.valor_recibido)}</span>
                      <EstadoBadge estado={r.estado} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="hidden md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16 pl-4">N.°</TableHead>
                  <TableHead>Fecha</TableHead>
                  <TableHead>Concepto</TableHead>
                  <TableHead className="hidden md:table-cell">Pagador</TableHead>
                  <TableHead className="hidden lg:table-cell">Medio</TableHead>
                  <TableHead className="text-right">Valor</TableHead>
                  <TableHead className="pr-4">Estado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((r) => (
                  <TableRow
                    key={r.id}
                    className={cn("cursor-pointer", r.estado === "ANULADO" && "text-muted-foreground")}
                    onClick={() => setParam({ id: r.id, page: String(page) })}
                  >
                    <TableCell className="pl-4 tabular-nums">{r.consecutivo}</TableCell>
                    <TableCell className="whitespace-nowrap">{fechaHora(r.fecha_recaudo)}</TableCell>
                    <TableCell>
                      <span className="block">{r.concepto}</span>
                      {r.placa && <span className="font-mono text-xs tracking-wider text-muted-foreground">{r.placa}</span>}
                    </TableCell>
                    <TableCell className="hidden max-w-56 md:table-cell">
                      <span className="block truncate">{r.nombre_pagador}</span>
                      {r.unidad && <span className="text-xs text-muted-foreground">{r.unidad}</span>}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">
                      <span className="inline-flex items-center gap-1">
                        {MEDIO[r.medio_pago]}
                        {r.tiene_soporte && <Paperclip className="size-3.5 text-muted-foreground" aria-label="Con soporte" />}
                      </span>
                    </TableCell>
                    <TableCell className={cn("text-right font-medium tabular-nums", r.estado === "ANULADO" && "line-through")}>
                      {pesos(r.valor_recibido)}
                    </TableCell>
                    <TableCell className="pr-4">
                      <EstadoBadge estado={r.estado} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
            </>
          )}

          {data && data.total > PAGE_SIZE && (
            <div className="flex items-center justify-between border-t px-4 py-2 text-sm">
              <span className="text-muted-foreground">
                Página {page} de {paginas}
              </span>
              <div className="flex gap-1">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setParam({ page: String(page - 1) })} aria-label="Página anterior">
                  <ChevronLeft className="size-4" />
                </Button>
                <Button variant="outline" size="sm" disabled={page >= paginas} onClick={() => setParam({ page: String(page + 1) })} aria-label="Página siguiente">
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      <RecaudoDetalleSheet id={abierto} onClose={() => setParam({ id: null, page: String(page) })} onCambio={() => void mutate()} />
    </div>
  );
}
