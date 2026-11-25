"use client";

import {
  ArrowLeft,
  BadgeCheck,
  Car,
  CirclePlus,
  CreditCard,
  History,
  Home,
  MoreHorizontal,
  Pencil,
  Plus,
  Power,
  ReceiptText,
  UserMinus,
  UserPlus,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import useSWR from "swr";

import { Fila } from "@/components/activos/comunes";
import { PageHeader } from "@/components/layout/page-header";
import { useTenant } from "@/components/layout/tenant-context";
import { EstadoBadge, Etiqueta, mensajeError, MotivoDialog, Seccion, SinAcceso, Vacio } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError, fetcher } from "@/lib/api";
import { type EstadoRecaudo, fechaCorta, pesos } from "@/lib/recaudos";
import {
  ACCION_AUDITORIA,
  baseTenant,
  baseUnidades,
  coeficienteTexto,
  ENTIDAD_AUDITORIA,
  OCUPACION,
  type Persona,
  puedeUnidades,
  TIPO_UNIDAD,
  TIPO_VEHICULO,
  type UnidadDetalle,
  type Vehiculo,
  type Vinculo,
} from "@/lib/unidades";
import { cn } from "@/lib/utils";

import { MarcasVinculo, OcupacionBadge, RelacionBadge, Telefono, useRefrescarUnidades } from "./comunes";
import { CerrarVinculoDialog, PersonaFormDialog, UnidadFormDialog, VehiculoDialog, VincularDialog } from "./formularios";

export function FichaUnidadView({ unidadId }: { unidadId: string }) {
  const { tenant } = useTenant();
  const clave = `${baseUnidades(tenant.tenant_id)}/${unidadId}`;
  const { data: u, error, mutate } = useSWR<UnidadDetalle>(clave, fetcher);
  const refrescar = useRefrescarUnidades();
  const gestionar = puedeUnidades(tenant.role, "gestionar");
  const volver = `/${tenant.tenant_slug}/${tenant.role === "RESIDENTE" ? "mi-unidad" : "unidades"}`;

  const [editar, setEditar] = useState(false);
  const [vincular, setVincular] = useState(false);
  const [vehiculo, setVehiculo] = useState<Vehiculo | "nuevo" | null>(null);
  const [cerrar, setCerrar] = useState<Vinculo | null>(null);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [retirarVehiculo, setRetirarVehiculo] = useState<Vehiculo | null>(null);
  const [desactivar, setDesactivar] = useState(false);

  function actualizado(nueva: UnidadDetalle) {
    void mutate(nueva, { revalidate: false });
    void refrescar(tenant.tenant_id);
  }

  async function cambiarVinculo(v: Vinculo, cambios: Partial<Pick<Vinculo, "es_contacto_principal" | "responsable_pago" | "reside">>, mensaje: string) {
    try {
      actualizado(await api<UnidadDetalle>(`${baseTenant(tenant.tenant_id)}/vinculos/${v.id}`, { method: "PATCH", json: cambios }));
      toast.success(mensaje);
    } catch (e) {
      toast.error(mensajeError(e));
    }
  }

  if (!puedeUnidades(tenant.role, "verUnidades") && tenant.role !== "RESIDENTE") return <SinAcceso />;
  if (error instanceof ApiError && error.status === 404) {
    return <SinAcceso texto="La unidad no existe o no tiene acceso a ella" />;
  }
  if (!u) {
    return (
      <div className="space-y-3 p-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-40" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const esPrincipal = !u.unidad_principal;
  const directorio = puedeUnidades(tenant.role, "directorio") || tenant.role === "RESIDENTE";
  const verVehiculos = puedeUnidades(tenant.role, "vehiculos") || tenant.role === "RESIDENTE";
  const sugerenciaDistinta = esPrincipal && u.ocupacion !== u.ocupacion_sugerida;

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader
        title={`${TIPO_UNIDAD[u.tipo]} ${u.etiqueta}`}
        description={
          u.unidad_principal
            ? `Anexo de ${u.unidad_principal.etiqueta}`
            : [u.coefficient && `Coeficiente ${coeficienteTexto(u.coefficient)}`, u.area_m2 && `${Number(u.area_m2).toLocaleString("es-CO")} m²`].filter(Boolean).join(" · ") || undefined
        }
        actions={
          <>
            <Button variant="ghost" size="icon" asChild aria-label="Volver">
              <Link href={volver}>
                <ArrowLeft className="size-4" />
              </Link>
            </Button>
            {gestionar && u.activa && (
              <>
                <Button variant="outline" onClick={() => setEditar(true)} className="hidden sm:inline-flex">
                  <Pencil className="size-4" /> Editar
                </Button>
                <Button onClick={() => setVincular(true)}>
                  <UserPlus className="size-4" /> <span className="hidden sm:inline">Agregar persona</span>
                </Button>
              </>
            )}
            {(gestionar || puedeUnidades(tenant.role, "vehiculos")) && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon" aria-label="Más acciones">
                    <MoreHorizontal className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {["ADMIN", "AUXILIAR"].includes(tenant.role) && (
                    <DropdownMenuItem asChild>
                      <Link href={`/${tenant.tenant_slug}/recaudos/nuevo?unidad=${u.id}`}>
                        <ReceiptText className="size-4" /> Registrar un recaudo
                      </Link>
                    </DropdownMenuItem>
                  )}
                  {gestionar && u.activa && (
                    <>
                      <DropdownMenuItem onSelect={() => setEditar(true)} className="sm:hidden">
                        <Pencil className="size-4" /> Editar datos
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => setVehiculo("nuevo")}>
                        <Car className="size-4" /> Registrar vehículo
                      </DropdownMenuItem>
                    </>
                  )}
                  {gestionar && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onSelect={() => setDesactivar(true)} className={u.activa ? "text-destructive" : undefined}>
                        <Power className="size-4" /> {u.activa ? "Desactivar unidad" : "Reactivar unidad"}
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </>
        }
      />

      <div className="space-y-4 p-4 sm:p-6">
        {/* Encabezado de estado */}
        <div className="flex flex-wrap items-center gap-2">
          {!u.activa && <Etiqueta tono="danger">Desactivada</Etiqueta>}
          {esPrincipal && <OcupacionBadge ocupacion={u.ocupacion} />}
          {u.responsable_pago && (
            <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
              <CreditCard className="size-4 text-success" /> Paga: <span className="font-medium text-foreground">{u.responsable_pago.nombre}</span>
            </span>
          )}
          {u.anexos.map((a) => (
            <Link key={a.id} href={`/${tenant.tenant_slug}/unidades/${a.id}`} className="rounded-md border px-2 py-0.5 text-xs hover:bg-accent">
              {TIPO_UNIDAD[a.tipo]} {a.etiqueta.split("-").slice(-2).join("-")}
            </Link>
          ))}
          {u.unidad_principal && (
            <Link href={`/${tenant.tenant_slug}/unidades/${u.unidad_principal.id}`} className="text-sm font-medium text-primary hover:underline">
              Ir a {u.unidad_principal.etiqueta}
            </Link>
          )}
        </div>
        {sugerenciaDistinta && gestionar && (
          <p className="rounded-md border border-warning/30 bg-warning-soft/40 px-3 py-2 text-sm">
            Según las personas vinculadas, la ocupación sería <strong>{OCUPACION[u.ocupacion_sugerida].label.toLowerCase()}</strong>.{" "}
            <button
              type="button"
              className="font-medium text-primary hover:underline"
              onClick={async () => {
                try {
                  actualizado(await api<UnidadDetalle>(clave, { method: "PATCH", json: { ocupacion: u.ocupacion_sugerida } }));
                } catch (e) {
                  toast.error(mensajeError(e));
                }
              }}
            >
              Corregir
            </button>
          </p>
        )}

        <Tabs defaultValue="personas">
          <TabsList className="flex-wrap">
            <TabsTrigger value="personas">Personas ({u.vinculos.length})</TabsTrigger>
            <TabsTrigger value="datos">Datos</TabsTrigger>
            {verVehiculos && <TabsTrigger value="vehiculos">Vehículos ({u.vehiculos_lista.length})</TabsTrigger>}
            {u.historial.length > 0 && <TabsTrigger value="historial">Historial ({u.historial.length})</TabsTrigger>}
            {u.recaudos.length > 0 && <TabsTrigger value="recaudos">Recaudos</TabsTrigger>}
            {u.auditoria.length > 0 && <TabsTrigger value="auditoria">Auditoría</TabsTrigger>}
          </TabsList>

          {/* Personas vigentes */}
          <TabsContent value="personas" className="mt-4">
            {!directorio ? (
              <SinAcceso texto="Su rol no tiene acceso al directorio de personas" />
            ) : !u.vinculos.length ? (
              <div className="rounded-lg border bg-card">
                <Vacio
                  icono={Users}
                  titulo={esPrincipal ? "Nadie vinculado a esta unidad" : "Este anexo no tiene personas propias"}
                  texto={esPrincipal ? "Agregue al propietario y, si aplica, al arrendatario y a quienes viven allí." : "Las personas se registran en la unidad principal."}
                />
              </div>
            ) : (
              <ul className="grid gap-3 lg:grid-cols-2">
                {u.vinculos.map((v) => (
                  <li key={v.id} className="rounded-lg border bg-card p-4">
                    <div className="flex items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium">{v.persona.nombre_completo}</p>
                          <RelacionBadge relacion={v.relacion} />
                          {v.porcentaje_propiedad && <span className="text-xs text-muted-foreground">{Number(v.porcentaje_propiedad)} %</span>}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                          <Telefono numero={v.persona.telefono} />
                          {v.persona.email && (
                            <a href={`mailto:${v.persona.email}`} className="truncate text-sm text-muted-foreground hover:underline">
                              {v.persona.email}
                            </a>
                          )}
                        </div>
                        {v.persona.numero_documento && (
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {v.persona.tipo_documento} {v.persona.numero_documento}
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                          <MarcasVinculo v={v} />
                          <span className="text-muted-foreground">Desde {fechaCorta(v.fecha_inicio)}</span>
                          {v.persona.tiene_cuenta && <Etiqueta tono="info">Tiene cuenta</Etiqueta>}
                        </div>
                      </div>
                      {gestionar && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" aria-label={`Acciones para ${v.persona.nombre_completo}`}>
                              <MoreHorizontal className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={() => setPersona(v.persona)}>
                              <Pencil className="size-4" /> Editar datos de contacto
                            </DropdownMenuItem>
                            {!v.es_contacto_principal && (
                              <DropdownMenuItem onSelect={() => cambiarVinculo(v, { es_contacto_principal: true }, `${v.persona.nombre_completo} es ahora el contacto principal`)}>
                                <BadgeCheck className="size-4" /> Hacer contacto principal
                              </DropdownMenuItem>
                            )}
                            {!v.responsable_pago && v.relacion !== "AUTORIZADO" && (
                              <DropdownMenuItem onSelect={() => cambiarVinculo(v, { responsable_pago: true }, `${v.persona.nombre_completo} es ahora responsable del pago`)}>
                                <CreditCard className="size-4" /> Hacer responsable del pago
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem onSelect={() => cambiarVinculo(v, { reside: !v.reside }, v.reside ? "Marcado como que no vive allí" : "Marcado como que vive allí")}>
                              <Home className="size-4" /> {v.reside ? "Ya no vive aquí" : "Vive aquí"}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onSelect={() => setCerrar(v)} className="text-destructive">
                              <UserMinus className="size-4" /> Retirar de la unidad…
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>

          {/* Datos de la unidad */}
          <TabsContent value="datos" className="mt-4">
            <Seccion titulo="Datos de la unidad">
              <dl className="divide-y px-4 py-1">
                <Fila k="Tipo" v={TIPO_UNIDAD[u.tipo]} />
                <Fila k="Torre" v={u.tower || "—"} />
                <Fila k="Número" v={u.number} />
                {u.coefficient !== null && <Fila k="Coeficiente de copropiedad" v={coeficienteTexto(u.coefficient)} />}
                {u.area_m2 !== null && <Fila k="Área privada" v={`${Number(u.area_m2).toLocaleString("es-CO")} m²`} />}
                {u.matricula_inmobiliaria && <Fila k="Matrícula inmobiliaria" v={u.matricula_inmobiliaria} />}
                {esPrincipal && <Fila k="Ocupación" v={OCUPACION[u.ocupacion].label} />}
                <Fila k="Residentes" v={String(u.residentes)} />
                {u.observaciones && <Fila k="Observaciones" v={u.observaciones} />}
                <Fila k="Registrada" v={fechaCorta(u.created_at)} />
              </dl>
            </Seccion>
          </TabsContent>

          {/* Vehículos */}
          {verVehiculos && (
            <TabsContent value="vehiculos" className="mt-4">
              <Seccion
                titulo="Vehículos registrados"
                descripcion="Recepción los reconoce como vehículos de residentes al registrar el parqueadero."
                acciones={gestionar && u.activa ? (
                  <Button size="sm" variant="outline" onClick={() => setVehiculo("nuevo")}>
                    <Plus className="size-4" /> Registrar
                  </Button>
                ) : undefined}
              >
                {!u.vehiculos_lista.length ? (
                  <Vacio icono={Car} titulo="Sin vehículos registrados" />
                ) : (
                  <ul className="divide-y">
                    {u.vehiculos_lista.map((v) => (
                      <li key={v.id} className="flex items-center gap-3 px-4 py-3">
                        <span className="rounded border-2 border-foreground/70 bg-warning-soft px-2 py-0.5 font-mono text-sm font-semibold tracking-wider">{v.placa}</span>
                        <div className="min-w-0 flex-1 text-sm">
                          <p>
                            {TIPO_VEHICULO[v.tipo]}
                            {v.marca && ` · ${v.marca}`}
                            {v.color && ` · ${v.color}`}
                          </p>
                          {v.persona && <p className="text-xs text-muted-foreground">{v.persona.nombre}</p>}
                        </div>
                        {gestionar && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" aria-label={`Acciones para ${v.placa}`}>
                                <MoreHorizontal className="size-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onSelect={() => setVehiculo(v)}>
                                <Pencil className="size-4" /> Editar
                              </DropdownMenuItem>
                              <DropdownMenuItem onSelect={() => setRetirarVehiculo(v)} className="text-destructive">
                                <Power className="size-4" /> Retirar
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Seccion>
            </TabsContent>
          )}

          {/* Historial de propietarios y arrendatarios */}
          <TabsContent value="historial" className="mt-4">
            <Seccion titulo="Historial" descripcion="Personas que ya no figuran en la unidad: ventas, arriendos terminados, mudanzas.">
              <ul className="divide-y">
                {u.historial.map((v) => (
                  <li key={v.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
                    <History className="size-4 text-muted-foreground" />
                    <span className="font-medium">{v.persona.nombre_completo}</span>
                    <RelacionBadge relacion={v.relacion} />
                    <span className="text-muted-foreground">
                      {fechaCorta(v.fecha_inicio)} → {v.fecha_fin ? fechaCorta(v.fecha_fin) : "hoy"}
                    </span>
                    {v.motivo_cierre && <span className="w-full pl-7 text-xs text-muted-foreground">{v.motivo_cierre}</span>}
                  </li>
                ))}
              </ul>
            </Seccion>
          </TabsContent>

          {/* Recaudos de la unidad */}
          <TabsContent value="recaudos" className="mt-4">
            <Seccion
              titulo="Últimos recaudos"
              descripcion="Ingresos extraordinarios asociados a esta unidad (parqueadero, zonas sociales, aseo…)."
              acciones={
                <Button size="sm" variant="outline" asChild>
                  <Link href={`/${tenant.tenant_slug}/recaudos/nuevo?unidad=${u.id}`}>
                    <CirclePlus className="size-4" /> Registrar
                  </Link>
                </Button>
              }
            >
              <ul className="divide-y">
                {u.recaudos.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                    <span className="w-14 font-mono text-xs text-muted-foreground">#{r.consecutivo}</span>
                    <span className="min-w-0 flex-1 truncate">{r.concepto}</span>
                    <span className="hidden text-muted-foreground sm:inline">{fechaCorta(r.fecha_recaudo)}</span>
                    <EstadoBadge estado={r.estado as EstadoRecaudo} />
                    <span className="w-24 text-right font-medium tabular-nums">{pesos(r.valor)}</span>
                  </li>
                ))}
              </ul>
            </Seccion>
          </TabsContent>

          {/* Auditoría */}
          <TabsContent value="auditoria" className="mt-4">
            <Seccion titulo="Auditoría" descripcion="Cada cambio con quién lo hizo, cuándo y por qué. Nada se borra.">
              <ul className="divide-y">
                {u.auditoria.map((a, i) => (
                  <li key={i} className="px-4 py-2.5 text-sm">
                    <div className="flex flex-wrap items-center gap-x-2">
                      <span className="font-medium">
                        {ACCION_AUDITORIA[a.accion]} · {ENTIDAD_AUDITORIA[a.entidad].toLowerCase()}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(a.fecha_hora).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Bogota" })}
                        {a.usuario && ` · ${a.usuario.replace(/\s*\(.*\)/, "")}`}
                      </span>
                    </div>
                    {a.motivo && <p className="text-xs text-muted-foreground">Motivo: {a.motivo}</p>}
                    {a.accion === "EDICION" && a.cambios && (
                      <p className="truncate text-xs text-muted-foreground" title={JSON.stringify(a.cambios)}>
                        Cambió: {Object.keys(a.cambios).filter((k) => !["id", "tenant_id"].includes(k)).join(", ")}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </Seccion>
          </TabsContent>
        </Tabs>
      </div>

      {gestionar && (
        <>
          <UnidadFormDialog tenantId={tenant.tenant_id} abierto={editar} onCambio={setEditar} unidad={u} onGuardado={actualizado} />
          <VincularDialog tenantId={tenant.tenant_id} abierto={vincular} onCambio={setVincular} unidad={u} onGuardado={actualizado} />
          <CerrarVinculoDialog tenantId={tenant.tenant_id} vinculo={cerrar} onCerrar={() => setCerrar(null)} onGuardado={actualizado} />
          <VehiculoDialog
            tenantId={tenant.tenant_id}
            abierto={vehiculo !== null}
            onCambio={(v) => !v && setVehiculo(null)}
            unidad={u}
            vehiculo={vehiculo && vehiculo !== "nuevo" ? vehiculo : undefined}
            onGuardado={actualizado}
          />
          {persona && (
            <PersonaFormDialog
              tenantId={tenant.tenant_id}
              abierto={!!persona}
              onCambio={(v) => !v && setPersona(null)}
              persona={persona}
              onGuardado={() => {
                void mutate();
                void refrescar(tenant.tenant_id);
              }}
            />
          )}
          <MotivoDialog
            abierto={!!retirarVehiculo}
            onCambio={(v) => !v && setRetirarVehiculo(null)}
            titulo={`Retirar el vehículo ${retirarVehiculo?.placa ?? ""}`}
            descripcion="Deja de reconocerse como vehículo de residente. Queda en la auditoría."
            boton="Retirar"
            minimo={5}
            onConfirmar={async (motivo) => {
              if (!retirarVehiculo) return;
              actualizado(await api<UnidadDetalle>(`${baseTenant(tenant.tenant_id)}/vehiculos/${retirarVehiculo.id}/retirar`, { method: "POST", json: { motivo } }));
              toast.success(`Vehículo ${retirarVehiculo.placa} retirado`);
            }}
          />
          <MotivoDialog
            abierto={desactivar}
            onCambio={setDesactivar}
            titulo={u.activa ? `Desactivar ${u.etiqueta}` : `Reactivar ${u.etiqueta}`}
            descripcion={
              u.activa
                ? "Para unidades creadas por error o fusionadas. No se borra: sigue en la auditoría y en los recaudos. Antes debe retirar a las personas vinculadas."
                : "La unidad vuelve al censo."
            }
            boton={u.activa ? "Desactivar" : "Reactivar"}
            peligro={u.activa}
            onConfirmar={async (motivo) => {
              actualizado(await api<UnidadDetalle>(`${clave}/${u.activa ? "desactivar" : "reactivar"}`, { method: "POST", json: { motivo } }));
              toast.success(u.activa ? "Unidad desactivada" : "Unidad reactivada");
            }}
          />
        </>
      )}
    </div>
  );
}
