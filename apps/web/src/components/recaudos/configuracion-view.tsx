"use client";

import { Loader2, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, fetcher } from "@/lib/api";
import { base, type Concepto, pesos, puede, type TipoCobro, type Zona } from "@/lib/recaudos";

import { campoClase, Etiqueta, mensajeError, Seccion, SinAcceso } from "./comunes";

const TIPO: Record<TipoCobro, string> = { FIJO: "Tarifa fija", POR_HORA: "Por tiempo", VARIABLE: "Valor libre" };
const num = (v: string | null) => (v ? String(Number(v)) : "");

function ConceptoDialog({ concepto, abierto, onCambio, onGuardado }: { concepto: Concepto | null; abierto: boolean; onCambio: (v: boolean) => void; onGuardado: () => void }) {
  const { tenant } = useTenant();
  const nuevo = concepto === null;
  const [codigo, setCodigo] = useState("");
  const [nombre, setNombre] = useState(concepto?.nombre ?? "");
  const [tipo, setTipo] = useState<TipoCobro>(concepto?.tipo_cobro ?? "FIJO");
  const [tarifa, setTarifa] = useState(num(concepto?.tarifa_base ?? null));
  const [fraccion, setFraccion] = useState(concepto?.fraccion_minutos ? String(concepto.fraccion_minutos) : "60");
  const [activo, setActivo] = useState(concepto?.activo ?? true);
  const [enviando, setEnviando] = useState(false);

  async function guardar() {
    setEnviando(true);
    const cuerpo = {
      nombre: nombre.trim(),
      tipo_cobro: tipo,
      tarifa_base: tarifa || null,
      fraccion_minutos: tipo === "POR_HORA" ? Number(fraccion) : null,
    };
    try {
      if (nuevo) {
        await api(`${base(tenant.tenant_id)}/conceptos`, { method: "POST", json: { ...cuerpo, codigo: codigo.trim().toUpperCase() } });
      } else {
        await api(`${base(tenant.tenant_id)}/conceptos/${concepto.id}`, { method: "PATCH", json: { ...cuerpo, activo } });
      }
      toast.success(nuevo ? "Concepto creado" : "Concepto actualizado");
      onGuardado();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{nuevo ? "Nuevo concepto de recaudo" : `Editar «${concepto.nombre}»`}</DialogTitle>
          <DialogDescription>Los cambios de tarifa aplican a los recaudos nuevos; los registrados conservan su valor.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          {nuevo && (
            <div className="space-y-1.5">
              <Label htmlFor="codigo">Código</Label>
              <Input id="codigo" value={codigo} onChange={(e) => setCodigo(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ""))} placeholder="GIMNASIO" />
            </div>
          )}
          <div className={nuevo ? "space-y-1.5" : "space-y-1.5 sm:col-span-2"}>
            <Label htmlFor="nombre">Nombre</Label>
            <Input id="nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tipo">Tipo de cobro</Label>
            <select id="tipo" value={tipo} onChange={(e) => setTipo(e.target.value as TipoCobro)} className={campoClase()}>
              {(Object.keys(TIPO) as TipoCobro[]).map((t) => (
                <option key={t} value={t}>
                  {TIPO[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tarifa">{tipo === "POR_HORA" ? "Tarifa por fracción" : "Tarifa"}</Label>
            <Input id="tarifa" inputMode="numeric" value={tarifa} onChange={(e) => setTarifa(e.target.value.replace(/\D/g, ""))} placeholder={tipo === "VARIABLE" ? "Opcional" : ""} />
          </div>
          {tipo === "POR_HORA" && (
            <div className="space-y-1.5">
              <Label htmlFor="fraccion">Fracción (minutos)</Label>
              <Input id="fraccion" inputMode="numeric" value={fraccion} onChange={(e) => setFraccion(e.target.value.replace(/\D/g, ""))} />
            </div>
          )}
          {!nuevo && (
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo (visible al registrar)
            </label>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={nombre.trim().length < 2 || (nuevo && codigo.length < 2) || (tipo !== "VARIABLE" && !tarifa) || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ZonaDialog({ zona, abierto, onCambio, onGuardado }: { zona: Zona | null; abierto: boolean; onCambio: (v: boolean) => void; onGuardado: () => void }) {
  const { tenant } = useTenant();
  const [nombre, setNombre] = useState(zona?.nombre ?? "");
  const [alquiler, setAlquiler] = useState(num(zona?.tarifa_alquiler ?? null));
  const [aseo, setAseo] = useState(num(zona?.tarifa_aseo ?? null));
  const [activo, setActivo] = useState(zona?.activo ?? true);
  const [enviando, setEnviando] = useState(false);

  async function guardar() {
    setEnviando(true);
    const cuerpo = { nombre: nombre.trim(), tarifa_alquiler: alquiler || null, tarifa_aseo: aseo || null };
    try {
      if (zona) await api(`${base(tenant.tenant_id)}/zonas/${zona.id}`, { method: "PATCH", json: { ...cuerpo, activo } });
      else await api(`${base(tenant.tenant_id)}/zonas`, { method: "POST", json: cuerpo });
      toast.success(zona ? "Zona actualizada" : "Zona creada");
      onGuardado();
      onCambio(false);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={onCambio}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{zona ? `Editar «${zona.nombre}»` : "Nueva zona social"}</DialogTitle>
          <DialogDescription>Las tarifas se sugieren al cobrar un alquiler, separadas en alquiler y aseo.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="z-nombre">Nombre</Label>
            <Input id="z-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Salón social" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="z-alq">Tarifa de alquiler</Label>
            <Input id="z-alq" inputMode="numeric" value={alquiler} onChange={(e) => setAlquiler(e.target.value.replace(/\D/g, ""))} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="z-aseo">Tarifa de aseo</Label>
            <Input id="z-aseo" inputMode="numeric" value={aseo} onChange={(e) => setAseo(e.target.value.replace(/\D/g, ""))} />
          </div>
          {zona && (
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activa (se puede reservar)
            </label>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onCambio(false)}>
            Cancelar
          </Button>
          <Button disabled={nombre.trim().length < 2 || enviando} onClick={guardar}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ConfiguracionView() {
  const { tenant } = useTenant();
  const b = base(tenant.tenant_id);
  const permitido = puede(tenant.role, "configurar");
  const { data: conceptos, mutate: refrescarConceptos } = useSWR<Concepto[]>(permitido ? `${b}/conceptos?incluir_inactivos=true` : null, fetcher);
  const { data: zonas, mutate: refrescarZonas } = useSWR<Zona[]>(permitido ? `${b}/zonas?incluir_inactivas=true` : null, fetcher);
  const [concepto, setConcepto] = useState<Concepto | null | undefined>(undefined);
  const [zona, setZona] = useState<Zona | null | undefined>(undefined);

  if (!permitido) return <SinAcceso texto="Solo la administración configura conceptos y tarifas" />;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Configuración de recaudos" description="Conceptos de cobro, tarifas y zonas sociales reservables." />
      <div className="space-y-6 p-4 sm:p-6">
        <Seccion
          titulo="Conceptos de recaudo"
          descripcion="Agregar un cobro nuevo no requiere cambios en el sistema."
          acciones={
            <Button size="sm" variant="outline" onClick={() => setConcepto(null)}>
              <Plus className="size-4" /> Nuevo concepto
            </Button>
          }
        >
          {!conceptos ? (
            <Skeleton className="m-4 h-24" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Concepto</TableHead>
                  <TableHead>Cobro</TableHead>
                  <TableHead className="text-right">Tarifa</TableHead>
                  <TableHead className="hidden md:table-cell">Requiere</TableHead>
                  <TableHead className="w-24 pr-4 text-right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {conceptos.map((c) => (
                  <TableRow key={c.id} className={c.activo ? "" : "text-muted-foreground"}>
                    <TableCell className="pl-4">
                      <span className="block font-medium">{c.nombre}</span>
                      <span className="font-mono text-xs text-muted-foreground">{c.codigo}</span>
                    </TableCell>
                    <TableCell>{TIPO[c.tipo_cobro]}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {c.tarifa_base ? pesos(c.tarifa_base) : "—"}
                      {c.tipo_cobro === "POR_HORA" && <span className="block text-xs text-muted-foreground">cada {c.fraccion_minutos} min</span>}
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <span className="flex gap-1">
                        {c.requiere_vehiculo && <Etiqueta tono="neutral">Placa</Etiqueta>}
                        {c.requiere_reserva && <Etiqueta tono="neutral">Reserva</Etiqueta>}
                        {!c.activo && <Etiqueta tono="danger">Inactivo</Etiqueta>}
                      </span>
                    </TableCell>
                    <TableCell className="pr-4 text-right">
                      <Button size="sm" variant="ghost" onClick={() => setConcepto(c)} aria-label={`Editar ${c.nombre}`}>
                        <Pencil className="size-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Seccion>

        <Seccion
          titulo="Zonas sociales"
          acciones={
            <Button size="sm" variant="outline" onClick={() => setZona(null)}>
              <Plus className="size-4" /> Nueva zona
            </Button>
          }
        >
          {!zonas ? (
            <Skeleton className="m-4 h-20" />
          ) : !zonas.length ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">Cree las zonas que se pueden alquilar (salón social, BBQ…).</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Zona</TableHead>
                  <TableHead className="text-right">Alquiler</TableHead>
                  <TableHead className="text-right">Aseo</TableHead>
                  <TableHead className="w-24 pr-4" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {zonas.map((z) => (
                  <TableRow key={z.id} className={z.activo ? "" : "text-muted-foreground"}>
                    <TableCell className="pl-4 font-medium">
                      {z.nombre} {!z.activo && <Etiqueta tono="danger">Inactiva</Etiqueta>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{pesos(z.tarifa_alquiler)}</TableCell>
                    <TableCell className="text-right tabular-nums">{pesos(z.tarifa_aseo)}</TableCell>
                    <TableCell className="pr-4 text-right">
                      <Button size="sm" variant="ghost" onClick={() => setZona(z)} aria-label={`Editar ${z.nombre}`}>
                        <Pencil className="size-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Seccion>
      </div>

      {concepto !== undefined && (
        <ConceptoDialog key={concepto?.id ?? "nuevo"} concepto={concepto} abierto onCambio={(v) => !v && setConcepto(undefined)} onGuardado={() => void refrescarConceptos()} />
      )}
      {zona !== undefined && (
        <ZonaDialog key={zona?.id ?? "nueva"} zona={zona} abierto onCambio={(v) => !v && setZona(undefined)} onGuardado={() => void refrescarZonas()} />
      )}
    </div>
  );
}
