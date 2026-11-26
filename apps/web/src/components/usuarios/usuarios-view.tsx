"use client";

import { FlaskConical, MailPlus, RotateCw, UserMinus, UsersRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { campoClase, Etiqueta, SinAcceso, Vacio } from "@/components/recaudos/comunes";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, fetcher } from "@/lib/api";
import { baseUsuarios, ESTADO_USUARIO, ROLES_INVITABLES, type UsuarioCopropiedad } from "@/lib/cuentas";
import type { Role } from "@/lib/types";

import { InvitarDialog } from "./invitar-dialog";

function fecha(iso: string | null): string {
  if (!iso) return "Nunca";
  return new Date(iso).toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });
}

export function UsuariosView() {
  const { tenant, isAdmin } = useTenant();
  const url = baseUsuarios(tenant.tenant_id);
  const { data, mutate, isLoading } = useSWR<UsuarioCopropiedad[]>(isAdmin ? url : null, fetcher);
  const [invitar, setInvitar] = useState(false);
  const [retirar, setRetirar] = useState<UsuarioCopropiedad | null>(null);
  const demo = !!tenant.is_demo;

  if (!isAdmin) return <SinAcceso texto="Solo la administración gestiona los usuarios" />;

  async function cambiarRol(u: UsuarioCopropiedad, rol: Role) {
    try {
      await api(`${url}/${u.user_id}`, { method: "PATCH", json: { rol } });
      toast.success(`${u.nombre} ahora es ${ROLES_INVITABLES.find((r) => r.rol === rol)?.etiqueta}.`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo cambiar el rol.");
    }
    void mutate();
  }

  async function reenviar(u: UsuarioCopropiedad) {
    try {
      await api(`${url}/${u.user_id}/reenviar`, { method: "POST" });
      toast.success(`Se envió un enlace nuevo a ${u.email}.`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo reenviar la invitación.");
    }
  }

  async function confirmarRetiro() {
    if (!retirar) return;
    try {
      await api(`${url}/${retirar.user_id}`, { method: "DELETE" });
      toast.success(`${retirar.nombre} ya no tiene acceso a ${tenant.tenant_name}.`);
      void mutate();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo retirar el acceso.");
    } finally {
      setRetirar(null);
    }
  }

  const pendientes = data?.filter((u) => u.estado === "INVITADO").length ?? 0;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <PageHeader
        title="Usuarios y accesos"
        description="Quién entra a esta copropiedad y con qué rol"
        actions={
          <Button onClick={() => setInvitar(true)} disabled={demo}>
            <MailPlus className="size-4" />
            Invitar usuario
          </Button>
        }
      />
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {demo && (
          <div className="mb-4 flex gap-2 rounded-md border border-warning/25 bg-warning-soft px-3 py-2.5 text-sm text-warning">
            <FlaskConical className="mt-0.5 size-4 shrink-0" />
            En los conjuntos de demostración no se pueden invitar ni modificar usuarios.
          </div>
        )}
        <p className="mb-3 text-sm text-muted-foreground">
          Para darle acceso al portal a un propietario o residente del censo, use «Dar acceso al portal» en la ficha de
          su unidad: así verá su propia unidad y estado de cuenta.
          {pendientes > 0 && ` Hay ${pendientes} invitación(es) sin activar.`}
        </p>
        <div className="overflow-x-auto rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nombre</TableHead>
                <TableHead>Rol</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="hidden md:table-cell">Último ingreso</TableHead>
                <TableHead className="w-0" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 4 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={5}>
                      <Skeleton className="h-8 w-full" />
                    </TableCell>
                  </TableRow>
                ))}
              {data?.map((u) => (
                <TableRow key={u.user_id}>
                  <TableCell>
                    <p className="font-medium">
                      {u.nombre}
                      {u.es_usted && <span className="ml-1.5 text-xs font-normal text-muted-foreground">(usted)</span>}
                    </p>
                    <p className="text-xs text-muted-foreground">{u.email}</p>
                  </TableCell>
                  <TableCell>
                    <select
                      aria-label={`Rol de ${u.nombre}`}
                      className={`${campoClase()} h-8 w-auto min-w-40`}
                      value={u.rol}
                      disabled={demo}
                      onChange={(e) => void cambiarRol(u, e.target.value as Role)}
                    >
                      {ROLES_INVITABLES.map((r) => (
                        <option key={r.rol} value={r.rol}>
                          {r.etiqueta}
                        </option>
                      ))}
                    </select>
                  </TableCell>
                  <TableCell>
                    <Etiqueta tono={ESTADO_USUARIO[u.estado].tono}>{ESTADO_USUARIO[u.estado].etiqueta}</Etiqueta>
                  </TableCell>
                  <TableCell className="hidden text-sm text-muted-foreground md:table-cell">{fecha(u.ultimo_ingreso)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      {u.estado === "INVITADO" && (
                        <Button variant="ghost" size="sm" disabled={demo} onClick={() => void reenviar(u)}>
                          <RotateCw className="size-4" />
                          <span className="hidden lg:inline">Reenviar</span>
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        disabled={demo}
                        onClick={() => setRetirar(u)}
                        aria-label={`Retirar acceso a ${u.nombre}`}
                      >
                        <UserMinus className="size-4" />
                        <span className="hidden lg:inline">Retirar</span>
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {data?.length === 0 && <Vacio icono={UsersRound} titulo="Aún no hay usuarios" />}
        </div>
      </div>

      <InvitarDialog tenantId={tenant.tenant_id} open={invitar} onOpenChange={setInvitar} onInvitado={() => void mutate()} />

      <AlertDialog open={!!retirar} onOpenChange={(o) => !o && setRetirar(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Retirar el acceso de {retirar?.nombre}?</AlertDialogTitle>
            <AlertDialogDescription>
              Dejará de entrar a {tenant.tenant_name} de inmediato. Su cuenta sigue funcionando en otras copropiedades, y
              lo que registró (recaudos, PQRS, mantenimientos) se conserva con su nombre.
              {retirar?.es_usted && " Está retirando su propio acceso."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmarRetiro()}>Retirar acceso</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
