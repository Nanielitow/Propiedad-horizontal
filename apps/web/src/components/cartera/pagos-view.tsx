"use client";

import { ChevronLeft, ChevronRight, HandCoins, Paperclip, Printer, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher } from "@/lib/api";
import { baseCartera, type PagosPagina, puedeCartera } from "@/lib/cartera";
import { fechaCorta, MEDIO, type MedioPago, pesos } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { RegistrarPagoDialog, useRefrescarCartera } from "./comunes";

const PAGE_SIZE = 50;

export function PagosView() {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const permitido = puedeCartera(tenant.role, "ver");
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const refrescar = useRefrescarCartera();
  const [busqueda, setBusqueda] = useState(params.get("texto") ?? "");
  const [nuevo, setNuevo] = useState(false);
  const page = Number(params.get("page") ?? 1);

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
    for (const k of ["texto", "desde", "hasta", "medio_pago"]) {
      const v = params.get(k);
      if (v) q.set(k, v);
    }
    if (params.get("anulados")) q.set("incluir_anulados", "true");
    return q.toString();
  }, [params, page]);
  const { data, isLoading } = useSWR<PagosPagina>(permitido ? `${b}/pagos?${consulta}` : null, fetcher, { keepPreviousData: true });
  const hayFiltros = ["texto", "desde", "hasta", "medio_pago"].some((k) => params.get(k));
  const paginas = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  if (!permitido) return <SinAcceso />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Pagos de cuotas"
        description="Recibos de caja de la cartera, con su aplicación y el saldo a favor que dejaron."
        actions={
          puedeCartera(tenant.role, "registrarPago") && (
            <Button onClick={() => setNuevo(true)}>
              <HandCoins className="size-4" /> Registrar pago
            </Button>
          )
        }
      />
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
            <Input value={busqueda} onChange={(e) => setBusqueda(e.target.value)} onBlur={() => setParam({ texto: busqueda.trim() || null })} placeholder="N.º de recibo, referencia o quién pagó" className="pl-8" aria-label="Buscar pagos" />
          </form>
          <input type="date" aria-label="Desde" value={params.get("desde") ?? ""} onChange={(e) => setParam({ desde: e.target.value || null })} className={cn(campoClase(), "w-40")} />
          <input type="date" aria-label="Hasta" value={params.get("hasta") ?? ""} onChange={(e) => setParam({ hasta: e.target.value || null })} className={cn(campoClase(), "w-40")} />
          <select aria-label="Medio" value={params.get("medio_pago") ?? ""} onChange={(e) => setParam({ medio_pago: e.target.value || null })} className={cn(campoClase(), "w-40")}>
            <option value="">Todo medio</option>
            {(Object.keys(MEDIO) as MedioPago[]).map((m) => (
              <option key={m} value={m}>
                {MEDIO[m]}
              </option>
            ))}
          </select>
          {hayFiltros && (
            <Button variant="ghost" onClick={() => { setBusqueda(""); router.replace(pathname, { scroll: false }); }}>
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
            <Vacio icono={HandCoins} titulo={hayFiltros ? "Ningún pago coincide" : "Aún no hay pagos registrados"} />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-20">Recibo</TableHead>
                    <TableHead>Unidad</TableHead>
                    <TableHead className="hidden md:table-cell">Fecha</TableHead>
                    <TableHead className="hidden lg:table-cell">Medio</TableHead>
                    <TableHead className="text-right">Valor</TableHead>
                    <TableHead className="hidden text-right md:table-cell">A favor</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((p) => (
                    <TableRow key={p.id} className={cn(p.estado === "ANULADO" && "opacity-60")}>
                      <TableCell className="font-mono text-xs">{p.consecutivo}</TableCell>
                      <TableCell>
                        <Link href={`/${tenant.tenant_slug}/cartera/unidades/${p.unidad_id}`} className="font-medium hover:underline">
                          {p.unidad}
                        </Link>
                        {p.estado === "ANULADO" && (
                          <span className="ml-2">
                            <Etiqueta tono="danger">Anulado</Etiqueta>
                          </span>
                        )}
                        {Number(p.descuentos) > 0 && <p className="text-xs text-success">Con descuento {pesos(p.descuentos)}</p>}
                      </TableCell>
                      <TableCell className="hidden text-sm md:table-cell">{fechaCorta(p.fecha_pago)}</TableCell>
                      <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">
                        {MEDIO[p.medio_pago]}
                        {p.referencia && <span className="block font-mono text-xs">{p.referencia}</span>}
                        {p.tiene_soporte && <Paperclip className="inline size-3.5" />}
                      </TableCell>
                      <TableCell className={cn("text-right font-medium tabular-nums", p.estado === "ANULADO" && "line-through")}>{pesos(p.valor)}</TableCell>
                      <TableCell className="hidden text-right text-sm tabular-nums md:table-cell">{Number(p.a_favor) ? pesos(p.a_favor) : "—"}</TableCell>
                      <TableCell>
                        <a href={`/api/proxy${b}/pagos/${p.id}/recibo.pdf`} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" aria-label={`Recibo ${p.consecutivo} en PDF`}>
                          <Printer className="size-4" />
                        </a>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex items-center justify-between border-t px-4 py-2 text-sm text-muted-foreground">
                <span>
                  {data.total} pagos · {pesos(data.total_valor)}
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
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={!!params.get("anulados")} onChange={(e) => setParam({ anulados: e.target.checked ? "1" : null })} className="size-3.5" />
          Incluir pagos anulados
        </label>
      </div>
      <RegistrarPagoDialog tenantId={tenant.tenant_id} abierto={nuevo} onCambio={setNuevo} onRegistrado={() => refrescar(tenant.tenant_id)} />
    </div>
  );
}
