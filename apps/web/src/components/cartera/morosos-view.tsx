"use client";

import { Download, FileSpreadsheet, PartyPopper, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
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
import { baseCartera, type Morosos, puedeCartera, RANGO, RANGOS_VENCIDOS } from "@/lib/cartera";
import { fechaCorta, pesos } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { Telefono } from "../unidades/comunes";
import { MoraBadge } from "./comunes";

const FILTROS_DIAS = [
  { v: 1, label: "Toda la mora" },
  { v: 31, label: "Más de 30 días" },
  { v: 61, label: "Más de 60 días" },
  { v: 91, label: "Más de 90 días (cobro jurídico)" },
];

export function MorososView() {
  const { tenant } = useTenant();
  const b = baseCartera(tenant.tenant_id);
  const router = useRouter();
  const [dias, setDias] = useState(1);
  const [texto, setTexto] = useState("");
  const permitido = puedeCartera(tenant.role, "ver");
  const { data, isLoading } = useSWR<Morosos>(permitido ? `${b}/morosos?dias_minimos=${dias}` : null, fetcher, { keepPreviousData: true });

  if (!permitido) return <SinAcceso />;
  const t = texto.trim().toLowerCase();
  const items = (data?.items ?? []).filter((m) => !t || `${m.unidad} ${m.responsable ?? ""}`.toLowerCase().includes(t));

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title="Morosos"
        description="Unidades con saldo vencido, por antigüedad de la deuda. Uso interno: no se publican en áreas comunes."
        actions={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <Download className="size-4" /> Exportar
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem asChild>
                <a href={`/api/proxy${b}/morosos?dias_minimos=${dias}&formato=xlsx`} download>
                  <FileSpreadsheet className="size-4" /> Excel
                </a>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <a href={`/api/proxy${b}/morosos?dias_minimos=${dias}&formato=pdf`} download>
                  <Download className="size-4" /> PDF
                </a>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
          <Kpi titulo="Total vencido" valor={data ? pesos(data.total_vencido) : "—"} destacado={!!data && Number(data.total_vencido) > 0} detalle={data ? `${data.items.length} unidades` : undefined} />
          {RANGOS_VENCIDOS.map((k) => (
            <Kpi key={k} titulo={RANGO[k].label} valor={data ? pesos(data.edades[k]) : "—"} />
          ))}
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Unidad o responsable" className="pl-8" aria-label="Buscar morosos" />
          </div>
          <select aria-label="Antigüedad" value={dias} onChange={(e) => setDias(Number(e.target.value))} className={cn(campoClase(), "w-64")}>
            {FILTROS_DIAS.map((f) => (
              <option key={f.v} value={f.v}>
                {f.label}
              </option>
            ))}
          </select>
        </div>

        <div className="rounded-lg border bg-card">
          {isLoading && !data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : !items.length ? (
            <Vacio icono={PartyPopper} titulo={data?.items.length ? "Nadie coincide con la búsqueda" : "No hay unidades en mora"} texto={data?.items.length ? undefined : "Todas las unidades están al día con lo vencido."} />
          ) : (
            <>
              <Table className="hidden md:table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Unidad</TableHead>
                    <TableHead>Responsable</TableHead>
                    <TableHead className="text-right">Vencido</TableHead>
                    <TableHead>Mora</TableHead>
                    <TableHead className="text-right">Más de 90 días</TableHead>
                    <TableHead>Último pago</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((m) => {
                    const href = `/${tenant.tenant_slug}/cartera/unidades/${m.unidad_id}`;
                    return (
                      <TableRow key={m.unidad_id} className="cursor-pointer" onClick={() => router.push(href)}>
                        <TableCell>
                          <Link href={href} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                            {m.unidad}
                          </Link>
                          <p className="text-xs text-muted-foreground">{m.cuotas_vencidas} cargos vencidos</p>
                        </TableCell>
                        <TableCell>
                          <p className="text-sm">{m.responsable ?? "—"}</p>
                          <span onClick={(e) => e.stopPropagation()}>
                            <Telefono numero={m.telefono} />
                          </span>
                        </TableCell>
                        <TableCell className="text-right font-medium tabular-nums">{pesos(m.saldo_vencido)}</TableCell>
                        <TableCell>
                          <MoraBadge dias={m.dias_mora} />
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{Number(m.edades.mas_90) ? pesos(m.edades.mas_90) : "—"}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">{m.ultimo_pago ? fechaCorta(m.ultimo_pago) : "Nunca"}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              <ul className="divide-y md:hidden">
                {items.map((m) => (
                  <li key={m.unidad_id}>
                    <Link href={`/${tenant.tenant_slug}/cartera/unidades/${m.unidad_id}`} className="flex items-start gap-3 px-4 py-3 active:bg-accent">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">{m.unidad}</p>
                        <p className="truncate text-sm text-muted-foreground">{m.responsable ?? "—"}</p>
                        <div className="mt-1">
                          <MoraBadge dias={m.dias_mora} />
                        </div>
                      </div>
                      <span className="font-medium tabular-nums">{pesos(m.saldo_vencido)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
