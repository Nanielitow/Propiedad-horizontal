"use client";

import { ArrowRight, Building2, FlaskConical, Link2, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { BotonSalir } from "@/components/auth/boton-salir";
import { campoClase, Etiqueta, Vacio } from "@/components/recaudos/comunes";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, fetcher } from "@/lib/api";
import type { Copropiedad, CopropiedadCreada, EnlaceInvitacion } from "@/lib/cuentas";
import type { Me } from "@/lib/types";

import { EnlacesDialog } from "./enlaces-dialog";
import { RespaldosSeccion } from "./respaldos";

const URL = "/plataforma/copropiedades";

export function PlataformaView({ me }: { me: Me }) {
  const { data, mutate, isLoading } = useSWR<Copropiedad[]>(URL, fetcher);
  const [nueva, setNueva] = useState(false);
  const [editar, setEditar] = useState<Copropiedad | null>(null);
  const [enlaces, setEnlaces] = useState<{ lista: EnlaceInvitacion[]; copropiedad: string; reemplazo: boolean } | null>(null);
  const [generar, setGenerar] = useState<Copropiedad | null>(null);
  const [eliminar, setEliminar] = useState<Copropiedad | null>(null);

  async function generarEnlace() {
    if (!generar) return;
    const c = generar;
    setGenerar(null);
    try {
      const lista = await api<EnlaceInvitacion[]>(`${URL}/${c.id}/enlaces`, { method: "POST" });
      setEnlaces({ lista, copropiedad: c.nombre, reemplazo: true });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo generar el enlace.");
    }
  }
  const mias = new Set(me.memberships.map((m) => m.tenant_id));
  const reales = data?.filter((c) => !c.is_demo) ?? [];

  return (
    <div className="min-h-dvh bg-background">
      <header className="flex items-center gap-3 bg-sidebar px-4 py-3 text-sidebar-foreground sm:px-6">
        <div className="flex size-8 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
          <Building2 className="size-4.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold tracking-tight text-white">PH Gestión · Plataforma</p>
          <p className="truncate text-xs text-sidebar-muted">{me.user.email}</p>
        </div>
        {me.memberships[0] && (
          <Button asChild variant="ghost" className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-white">
            <Link href={`/${me.memberships[0].tenant_slug}`}>Ir a la app</Link>
          </Button>
        )}
        <BotonSalir variant="ghost" className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-white" />
      </header>

      <main className="mx-auto max-w-6xl p-4 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Copropiedades</h1>
            <p className="text-sm text-muted-foreground">
              {reales.length} real{reales.length === 1 ? "" : "es"}
              {data && data.length > reales.length && ` · ${data.length - reales.length} de demostración`}
            </p>
          </div>
          <Button onClick={() => setNueva(true)}>
            <Plus className="size-4" />
            Nueva copropiedad
          </Button>
        </div>

        <div className="mt-4 overflow-x-auto rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Copropiedad</TableHead>
                <TableHead className="hidden sm:table-cell">Ciudad</TableHead>
                <TableHead className="text-right">Unidades</TableHead>
                <TableHead className="text-right">Usuarios</TableHead>
                <TableHead>Administración</TableHead>
                <TableHead className="w-0" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 3 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={6}>
                      <Skeleton className="h-8 w-full" />
                    </TableCell>
                  </TableRow>
                ))}
              {data?.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{c.nombre}</p>
                      {c.is_demo && (
                        <Etiqueta tono="warning">
                          <FlaskConical className="mr-1 size-3" />
                          Demostración
                        </Etiqueta>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">{c.nit ? `NIT ${c.nit}` : "Sin NIT"}</p>
                  </TableCell>
                  <TableCell className="hidden text-sm sm:table-cell">{c.ciudad ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{c.unidades}</TableCell>
                  <TableCell className="text-right tabular-nums">{c.usuarios}</TableCell>
                  <TableCell>
                    {c.administradores > 0 && c.invitaciones_pendientes === c.administradores ? (
                      <Etiqueta tono="warning">Invitación sin activar</Etiqueta>
                    ) : c.administradores > 0 ? (
                      <Etiqueta tono="success">
                        {c.administradores} administrador{c.administradores === 1 ? "" : "es"}
                      </Etiqueta>
                    ) : (
                      <Etiqueta tono="danger">Sin administrador</Etiqueta>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      {c.invitaciones_pendientes > 0 && !c.is_demo && (
                        <Button variant="ghost" size="sm" onClick={() => setGenerar(c)}>
                          <Link2 className="size-4" />
                          Enlace
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" onClick={() => setEditar(c)} aria-label={`Editar ${c.nombre}`}>
                        <Pencil className="size-4" />
                      </Button>
                      {mias.has(c.id) && (
                        <Button asChild variant="ghost" size="sm">
                          <Link href={`/${c.slug}`}>
                            Entrar <ArrowRight className="size-4" />
                          </Link>
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {data?.length === 0 && <Vacio icono={Building2} titulo="Aún no hay copropiedades" />}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Como dueño de la plataforma usted crea las copropiedades y su primer administrador, pero no ve sus datos: para
          entrar a una, su administrador debe invitarlo desde «Usuarios y accesos».
        </p>
        <RespaldosSeccion />
      </main>

      <NuevaDialog
        open={nueva}
        onOpenChange={setNueva}
        onCreada={(r, admin) => {
          void mutate();
          if (r.enlace_invitacion)
            setEnlaces({ lista: [{ ...admin, enlace: r.enlace_invitacion }], copropiedad: r.copropiedad.nombre, reemplazo: false });
        }}
      />
      <EnlacesDialog
        enlaces={enlaces?.lista ?? null}
        copropiedad={enlaces?.copropiedad ?? ""}
        reemplazo={enlaces?.reemplazo ?? false}
        onOpenChange={(o) => !o && setEnlaces(null)}
      />
      <AlertDialog open={!!generar} onOpenChange={(o) => !o && setGenerar(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Generar un enlace nuevo?</AlertDialogTitle>
            <AlertDialogDescription>
              Para la administración de {generar?.nombre} que aún no activa su cuenta. El enlace que se envió por correo
              dejará de funcionar; envíe el nuevo por WhatsApp o chat.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={() => void generarEnlace()}>Generar enlace</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <EditarDialog
        copropiedad={editar}
        onOpenChange={(o) => !o && setEditar(null)}
        onGuardada={() => void mutate()}
        onEliminar={() => {
          setEliminar(editar);
          setEditar(null);
        }}
      />
      <EliminarDialog copropiedad={eliminar} onOpenChange={(o) => !o && setEliminar(null)} onEliminada={() => void mutate()} />
    </div>
  );
}

function NuevaDialog({
  open,
  onOpenChange,
  onCreada,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onCreada: (r: CopropiedadCreada, admin: { nombre: string; email: string }) => void;
}) {
  const vacio = { nombre: "", nit: "", ciudad: "", direccion: "", admin_nombre: "", admin_email: "" };
  const [f, setF] = useState(vacio);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setF({ nombre: "", nit: "", ciudad: "", direccion: "", admin_nombre: "", admin_email: "" });
    setError(null);
  }, [open]);

  const campo = (k: keyof typeof vacio) => ({
    value: f[k],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setF((x) => ({ ...x, [k]: e.target.value })),
    className: campoClase(),
  });

  async function crear() {
    setEnviando(true);
    setError(null);
    try {
      const vacioANull = (v: string) => (v.trim() ? v.trim() : null);
      const r = await api<CopropiedadCreada>(URL, {
        method: "POST",
        json: {
          nombre: f.nombre.trim(),
          nit: vacioANull(f.nit),
          ciudad: vacioANull(f.ciudad),
          direccion: vacioANull(f.direccion),
          admin_nombre: f.admin_nombre.trim(),
          admin_email: f.admin_email.trim(),
        },
      });
      toast.success(
        r.administrador_nuevo
          ? `${r.copropiedad.nombre} creada. ${f.admin_nombre.split(" ")[0]} recibirá un correo para activar su cuenta.`
          : `${r.copropiedad.nombre} creada. ${f.admin_nombre.split(" ")[0]} ya tenía cuenta: la verá en su selector de copropiedades.`,
      );
      if (!r.correo_enviado) toast.warning("El correo no está configurado en este servidor: el aviso no saldrá.");
      onOpenChange(false);
      onCreada(r, { nombre: f.admin_nombre.trim(), email: f.admin_email.trim().toLowerCase() });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo crear la copropiedad.");
    } finally {
      setEnviando(false);
    }
  }

  const listo = f.nombre.trim().length >= 3 && f.admin_nombre.trim().length >= 2 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.admin_email.trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Nueva copropiedad</DialogTitle>
          <DialogDescription>
            Se crea con sus catálogos base (conceptos de recaudo y cartera, categorías de mantenimiento) y se invita a su
            administrador por correo.
          </DialogDescription>
        </DialogHeader>
        <form
          id="nueva-copropiedad"
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (listo) void crear();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="c-nombre">Nombre</Label>
            <input id="c-nombre" placeholder="Conjunto Residencial …" required autoFocus {...campo("nombre")} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="c-nit">NIT</Label>
              <input id="c-nit" placeholder="900123456-1" {...campo("nit")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="c-ciudad">Ciudad</Label>
              <input id="c-ciudad" {...campo("ciudad")} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="c-direccion">Dirección</Label>
            <input id="c-direccion" {...campo("direccion")} />
          </div>
          <fieldset className="space-y-3 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">Administrador(a)</legend>
            <div className="space-y-1.5">
              <Label htmlFor="c-admin-nombre">Nombre completo</Label>
              <input id="c-admin-nombre" required {...campo("admin_nombre")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="c-admin-email">Correo electrónico</Label>
              <input id="c-admin-email" type="email" required placeholder="nombre@correo.com" {...campo("admin_email")} />
              <p className="text-xs text-muted-foreground">
                Si ya administra otras copropiedades en PH Gestión, use el mismo correo: entrará con una sola cuenta.
              </p>
            </div>
          </fieldset>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="submit" form="nueva-copropiedad" disabled={!listo || enviando}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Crear e invitar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditarDialog({
  copropiedad,
  onOpenChange,
  onGuardada,
  onEliminar,
}: {
  copropiedad: Copropiedad | null;
  onOpenChange: (o: boolean) => void;
  onGuardada: () => void;
  onEliminar: () => void;
}) {
  const [f, setF] = useState({ nombre: "", nit: "", ciudad: "", direccion: "", is_demo: false });
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!copropiedad) return;
    setF({
      nombre: copropiedad.nombre,
      nit: copropiedad.nit ?? "",
      ciudad: copropiedad.ciudad ?? "",
      direccion: copropiedad.direccion ?? "",
      is_demo: copropiedad.is_demo,
    });
    setError(null);
  }, [copropiedad]);

  async function guardar() {
    if (!copropiedad) return;
    setEnviando(true);
    setError(null);
    try {
      const n = (v: string) => (v.trim() ? v.trim() : null);
      await api(`${URL}/${copropiedad.id}`, {
        method: "PATCH",
        json: { nombre: f.nombre.trim(), nit: n(f.nit), ciudad: n(f.ciudad), direccion: n(f.direccion), is_demo: f.is_demo },
      });
      toast.success("Copropiedad actualizada");
      onOpenChange(false);
      onGuardada();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo guardar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={!!copropiedad} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Editar copropiedad</DialogTitle>
          <DialogDescription>Datos generales. Los usuarios los gestiona su administración.</DialogDescription>
        </DialogHeader>
        <form
          id="editar-copropiedad"
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (f.nombre.trim().length >= 3) void guardar();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="e-nombre">Nombre</Label>
            <input id="e-nombre" className={campoClase()} value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} required />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="e-nit">NIT</Label>
              <input id="e-nit" className={campoClase()} value={f.nit} onChange={(e) => setF({ ...f, nit: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="e-ciudad">Ciudad</Label>
              <input id="e-ciudad" className={campoClase()} value={f.ciudad} onChange={(e) => setF({ ...f, ciudad: e.target.value })} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="e-direccion">Dirección</Label>
            <input id="e-direccion" className={campoClase()} value={f.direccion} onChange={(e) => setF({ ...f, direccion: e.target.value })} />
          </div>
          <label className="flex items-start gap-2.5 rounded-md border p-3 text-sm">
            <input
              type="checkbox"
              checked={f.is_demo}
              onChange={(e) => setF({ ...f, is_demo: e.target.checked })}
              className="mt-0.5 size-4 shrink-0 accent-primary"
            />
            <span>
              <span className="font-medium">Conjunto de demostración.</span>{" "}
              <span className="text-muted-foreground">
                Datos ficticios: no se pueden invitar usuarios y los correos solo salen a las direcciones autorizadas.
              </span>
            </span>
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </form>
        <div className="flex items-center justify-between gap-3 rounded-md border border-destructive/25 px-3 py-2.5">
          <div className="min-w-0 text-sm">
            <p className="font-medium">Eliminar copropiedad</p>
            <p className="text-xs text-muted-foreground">Por ejemplo, si la creó por error.</p>
          </div>
          <Button variant="outline" size="sm" className="text-destructive hover:text-destructive" onClick={onEliminar}>
            <Trash2 className="size-4" />
            Eliminar…
          </Button>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="submit" form="editar-copropiedad" disabled={enviando}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EliminarDialog({
  copropiedad,
  onOpenChange,
  onEliminada,
}: {
  copropiedad: Copropiedad | null;
  onOpenChange: (o: boolean) => void;
  onEliminada: () => void;
}) {
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!copropiedad) return;
    setTexto("");
    setError(null);
  }, [copropiedad]);

  const coincide = !!copropiedad && texto.trim() === copropiedad.nombre.trim();

  async function eliminar() {
    if (!copropiedad) return;
    setEnviando(true);
    setError(null);
    try {
      await api(`${URL}/${copropiedad.id}/eliminar`, { method: "POST", json: { confirmacion: texto.trim() } });
      toast.success(`${copropiedad.nombre} eliminada`);
      onOpenChange(false);
      onEliminada();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo eliminar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialog open={!!copropiedad} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Eliminar {copropiedad?.nombre}</DialogTitle>
          <DialogDescription>
            Desaparece de su panel y del selector de todos sus usuarios, y nadie podrá entrar a ella. Las invitaciones
            pendientes dejan de servir. Los datos se conservan en la base por seguridad.
          </DialogDescription>
        </DialogHeader>
        {copropiedad && (copropiedad.unidades > 0 || copropiedad.usuarios - copropiedad.invitaciones_pendientes > 0) && (
          <p className="rounded-md border border-destructive/25 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            Esta copropiedad ya tiene {copropiedad.unidades} unidad(es) y {copropiedad.usuarios} usuario(s): quienes entran
            a ella perderán el acceso.
          </p>
        )}
        <form
          id="eliminar-copropiedad"
          className="space-y-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (coincide) void eliminar();
          }}
        >
          <Label htmlFor="confirmar-nombre">
            Escriba <span className="font-semibold">{copropiedad?.nombre}</span> para confirmar
          </Label>
          <input
            id="confirmar-nombre"
            className={campoClase()}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            autoComplete="off"
            autoFocus
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="submit" form="eliminar-copropiedad" variant="destructive" disabled={!coincide || enviando}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Eliminar copropiedad
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
