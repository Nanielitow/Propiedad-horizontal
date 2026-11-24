"use client";

import { AlertTriangle, ChevronRight, ClipboardCheck, FileText, Gauge, QrCode, Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { useTenant } from "@/components/layout/tenant-context";
import { Etiqueta, mensajeError, SinAcceso } from "@/components/recaudos/comunes";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, fetcher } from "@/lib/api";
import {
  baseActivos,
  ESTADO_ACTIVO,
  ESTADO_NOVEDAD,
  PRIORIDAD_NOVEDAD,
  puedeActivos,
  type QrResuelto,
  SEMAFORO,
  textoDias,
  TIPO_MANTENIMIENTO,
} from "@/lib/activos";
import { fechaCorta } from "@/lib/recaudos";
import { cn } from "@/lib/utils";

import { useRefrescarActivos } from "./comunes";
import { NovedadDetalleSheet } from "./detalles";
import { MantenimientoSheet } from "./formulario-mantenimiento";
import { LecturaDialog } from "./formularios-activo";
import { NovedadFormDialog } from "./formularios-novedad";

const FONDO_ESTADO = {
  OPERATIVO: "border-success/30 bg-success-soft",
  OPERATIVO_CON_OBSERVACIONES: "border-warning/30 bg-warning-soft",
  EN_MANTENIMIENTO: "border-primary/20 bg-info-soft",
  FUERA_DE_SERVICIO: "border-destructive/30 bg-destructive/10",
  DADO_DE_BAJA: "border-border bg-secondary",
} as const;

/**
 * Lo que ve el técnico al escanear la etiqueta: el estado del equipo de un vistazo y
 * botones grandes para actuar en sitio (pensado para el celular, con una mano).
 */
export function QrView({ token }: { token: string }) {
  const { tenant } = useTenant();
  const rol = tenant.role;
  const b = baseActivos(tenant.tenant_id);
  const refrescar = useRefrescarActivos();
  const { data: a, error, mutate } = useSWR<QrResuelto>(puedeActivos(rol, "ver") ? `${b}/qr/${encodeURIComponent(token)}` : null, fetcher);
  const [dialogo, setDialogo] = useState<null | "falla" | "mantenimiento" | "ejecutar" | "lectura">(null);
  const [nov, setNov] = useState<string | null>(null);

  const actualizar = async () => {
    await mutate();
    await refrescar(tenant.tenant_id);
  };

  if (!puedeActivos(rol, "ver")) return <SinAcceso texto="Su rol no tiene acceso a la información de los equipos" />;
  if (error) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <QrCode className="size-10 text-muted-foreground" />
        <p className="font-medium">{error instanceof ApiError && error.status === 404 ? "Código QR no reconocido" : mensajeError(error)}</p>
        <p className="max-w-xs text-sm text-muted-foreground">
          Puede ser una etiqueta antigua (el código se regeneró) o de otra copropiedad. Avise a la administración.
        </p>
        <Button variant="outline" asChild>
          <Link href={`/${tenant.tenant_slug}/activos`}>Ver todos los activos</Link>
        </Button>
      </div>
    );
  }
  if (!a) {
    return (
      <div className="mx-auto w-full max-w-md space-y-3 p-4">
        <Skeleton className="h-36" />
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
      </div>
    );
  }

  const prox = a.proxima_actividad;
  const vigente = a.estado !== "DADO_DE_BAJA";

  return (
    <div className="mx-auto w-full max-w-md space-y-3 p-4 pb-10">
      {/* Estado de un vistazo */}
      <div className={cn("rounded-xl border p-4", FONDO_ESTADO[a.estado])}>
        <p className="font-mono text-xs text-muted-foreground">{a.codigo_interno}</p>
        <h1 className="mt-0.5 text-xl leading-tight font-semibold">{a.nombre}</h1>
        <p className="text-sm text-muted-foreground">{a.ubicacion}</p>
        <p className="mt-3 text-lg font-semibold">{ESTADO_ACTIVO[a.estado].label}</p>
        {a.semaforo && vigente && (
          <p className="mt-1 flex items-center gap-1.5 text-sm">
            <span className={cn("size-2.5 rounded-full", SEMAFORO[a.semaforo].punto)} />
            Mantenimiento {SEMAFORO[a.semaforo].label.toLowerCase()}
          </p>
        )}
      </div>

      {vigente && (
        <div className="grid grid-cols-2 gap-2">
          {puedeActivos(rol, "reportarNovedad") && (
            <Button variant="outline" className="h-16 flex-col gap-1 border-destructive/30 text-destructive hover:bg-destructive/5" onClick={() => setDialogo("falla")}>
              <AlertTriangle className="size-5" /> Reportar falla
            </Button>
          )}
          {puedeActivos(rol, "registrarMantenimiento") && (
            <Button className="h-16 flex-col gap-1" onClick={() => setDialogo(prox ? "ejecutar" : "mantenimiento")}>
              <Wrench className="size-5" /> {prox ? "Ejecutar mantenimiento" : "Registrar trabajo"}
            </Button>
          )}
          {a.usa_horometro && puedeActivos(rol, "registrarMantenimiento") && (
            <Button variant="outline" className="h-14 flex-col gap-1" onClick={() => setDialogo("lectura")}>
              <Gauge className="size-5" /> Lectura del horómetro
            </Button>
          )}
          {prox && puedeActivos(rol, "registrarMantenimiento") && (
            <Button variant="outline" className="h-14 flex-col gap-1" onClick={() => setDialogo("mantenimiento")}>
              <ClipboardCheck className="size-5" /> Otro trabajo
            </Button>
          )}
        </div>
      )}

      {/* Próximo y último */}
      <div className="divide-y rounded-xl border bg-card">
        <div className="p-4">
          <p className="text-xs font-medium text-muted-foreground">Próximo mantenimiento</p>
          {prox ? (
            <>
              <p className="mt-1 font-medium">{prox.plan.nombre}</p>
              <p className={cn("text-sm", prox.semaforo === "ROJO" ? "text-destructive" : prox.semaforo === "AMARILLO" ? "text-warning" : "text-muted-foreground")}>
                {fechaCorta(prox.fecha_programada)} · {textoDias(prox.dias_restantes)}
                {prox.contratista && ` · ${prox.contratista.nombre}`}
              </p>
            </>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">Sin mantenimiento programado.</p>
          )}
        </div>
        <div className="p-4">
          <p className="text-xs font-medium text-muted-foreground">Último mantenimiento</p>
          {a.ultimo_mantenimiento ? (
            <>
              <p className="mt-1 font-medium">
                {fechaCorta(a.ultimo_mantenimiento.fecha_ejecucion)} · {TIPO_MANTENIMIENTO[a.ultimo_mantenimiento.tipo].label}
              </p>
              <p className="text-sm text-muted-foreground">{a.ultimo_mantenimiento.nombre_tecnico}</p>
            </>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">Sin registros.</p>
          )}
        </div>
      </div>

      {/* Novedades abiertas */}
      {a.novedades_abiertas.length > 0 && (
        <div className="rounded-xl border bg-card">
          <p className="border-b px-4 py-2.5 text-sm font-semibold">Novedades abiertas ({a.novedades_abiertas.length})</p>
          <ul className="divide-y">
            {a.novedades_abiertas.map((n) => (
              <li key={n.id}>
                <button type="button" onClick={() => setNov(n.id)} className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-accent">
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">{n.descripcion}</span>
                    <span className="mt-1 flex flex-wrap gap-1">
                      <Etiqueta tono={PRIORIDAD_NOVEDAD[n.prioridad].tono}>{PRIORIDAD_NOVEDAD[n.prioridad].label}</Etiqueta>
                      <Etiqueta tono={ESTADO_NOVEDAD[n.estado].tono}>{ESTADO_NOVEDAD[n.estado].label}</Etiqueta>
                    </span>
                  </span>
                  <ChevronRight className="size-4 text-muted-foreground" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Button variant="ghost" asChild className="w-full">
        <Link href={`/${tenant.tenant_slug}/activos/${a.id}`}>
          <FileText className="size-4" /> Ver hoja de vida completa
        </Link>
      </Button>

      <NovedadFormDialog abierto={dialogo === "falla"} onCambio={(v) => setDialogo(v ? "falla" : null)} activoId={a.id} onGuardado={() => void actualizar()} />
      <MantenimientoSheet
        abierto={dialogo === "mantenimiento" || dialogo === "ejecutar"}
        onCambio={(v) => !v && setDialogo(null)}
        activoId={a.id}
        actividad={dialogo === "ejecutar" ? prox : null}
        onGuardado={() => void actualizar()}
      />
      <LecturaDialog tenantId={tenant.tenant_id} abierto={dialogo === "lectura"} onCambio={(v) => setDialogo(v ? "lectura" : null)} activoId={a.id} onGuardado={() => void actualizar()} />
      <NovedadDetalleSheet id={nov} onCerrar={() => setNov(null)} />
    </div>
  );
}
