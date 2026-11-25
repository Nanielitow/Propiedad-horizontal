"use client";

import {
  Gavel,
  AlertTriangle,
  Boxes,
  Building,
  CalendarPlus,
  Megaphone,
  MessageSquareWarning,
  CalendarRange,
  HandCoins,
  PiggyBank,
  UserX,
  Building2,
  Contact,
  Home,
  CalendarDays,
  ClipboardCheck,
  HardHat,
  ListChecks,
  CalendarClock,
  Check,
  ChevronsUpDown,
  CirclePlus,
  ClipboardList,
  FileText,
  Landmark,
  LayoutDashboard,
  ListOrdered,
  LogOut,
  MessageSquareText,
  Scale,
  Settings2,
  ShieldAlert,
  FileBarChart,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import useSWR from "swr";

import { useDeadlines } from "@/hooks/use-deadlines";
import { fetcher } from "@/lib/api";
import { alertCount } from "@/lib/deadlines";
import { ROLE_LABEL } from "@/lib/labels";
import { baseActivos, type Novedad, puedeActivos } from "@/lib/activos";
import { type Alerta, base, puede } from "@/lib/recaudos";
import { puedeUnidades } from "@/lib/unidades";
import { puedeCartera } from "@/lib/cartera";
import { puedeAsambleas } from "@/lib/asambleas";
import { basePortal, type PendientesPersonal, puedePortal } from "@/lib/portal";
import { cn } from "@/lib/utils";

import { useTenant } from "./tenant-context";

interface NavItem {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
  soon?: boolean;
  exact?: boolean;
}

const MAIN_NAV: NavItem[] = [
  { href: "search", label: "Buscador", description: "Pregunte a sus documentos", icon: MessageSquareText },
  { href: "documents", label: "Documentos", description: "Archivo de la copropiedad", icon: FileText },
];

const ADMIN_NAV: NavItem[] = [
  { href: "deadlines", label: "Vencimientos", description: "Pólizas, contratos, mantenimientos", icon: CalendarClock },
  { href: "quotes", label: "Cotizaciones", description: "Comparar proveedores", icon: Scale },
  { href: "minutes", label: "Actas", description: "Acuerdos y tareas de asambleas", icon: ClipboardList },
];

// Módulo de recaudos: cada ítem se muestra solo a los roles que lo usan
// Módulo de mantenimiento: también por rol (el técnico entra por «Mi trabajo»)
const ACTIVOS_NAV: (NavItem & { permiso: Parameters<typeof puedeActivos>[1] })[] = [
  { href: "activos/mi-trabajo", label: "Mi trabajo", description: "Lo asignado a usted", icon: ClipboardCheck, permiso: "miTrabajo" },
  { href: "activos/panel", label: "Panel", description: "Indicadores y presupuesto", icon: LayoutDashboard, permiso: "panel" },
  { href: "activos", label: "Activos", description: "Hojas de vida y semáforo", icon: Boxes, permiso: "ver", exact: true },
  { href: "activos/calendario", label: "Calendario", description: "Fechas de mantenimiento", icon: CalendarDays, permiso: "ver" },
  { href: "activos/novedades", label: "Novedades", description: "Fallas y su atención", icon: AlertTriangle, permiso: "ver" },
  { href: "activos/recomendaciones", label: "Recomendaciones", description: "Sugerencias de los técnicos", icon: ListChecks, permiso: "ver" },
  { href: "activos/planes", label: "Planes", description: "Mantenimiento preventivo", icon: CalendarClock, permiso: "contratistas" },
  { href: "activos/contratistas", label: "Contratistas", description: "Empresas y contratos", icon: HardHat, permiso: "contratistas" },
  { href: "activos/reportes", label: "Reportes", description: "Excel, PDF y presupuesto", icon: FileBarChart, permiso: "reportes" },
];

// Censo de la copropiedad: unidades y directorio (el residente ve «Mi unidad»)
const UNIDADES_NAV: (NavItem & { permiso: Parameters<typeof puedeUnidades>[1] })[] = [
  { href: "unidades", label: "Unidades", description: "Censo, coeficientes y ocupación", icon: Building, permiso: "verUnidades", exact: true },
  { href: "unidades/directorio", label: "Directorio", description: "Propietarios y residentes", icon: Contact, permiso: "directorio" },
];

const ASAMBLEAS_ITEM: NavItem = { href: "asambleas", label: "Asambleas", description: "Quórum, votaciones y actas", icon: Gavel };

// Cartera de cuotas de administración (el residente ve «Mi cuenta»)
const CARTERA_NAV: (NavItem & { permiso: Parameters<typeof puedeCartera>[1] })[] = [
  { href: "cartera", label: "Cartera", description: "Facturado, recaudado y mora", icon: LayoutDashboard, permiso: "ver", exact: true },
  { href: "cartera/periodos", label: "Facturación", description: "Cuotas de cada mes", icon: CalendarRange, permiso: "ver" },
  { href: "cartera/pagos", label: "Pagos", description: "Recibos de caja", icon: HandCoins, permiso: "ver" },
  { href: "cartera/morosos", label: "Morosos", description: "Saldos vencidos por antigüedad", icon: UserX, permiso: "ver" },
  { href: "cartera/configuracion", label: "Configuración", description: "Cuota, descuento e intereses", icon: Settings2, permiso: "configurar" },
];

// Portal del residente: todo lo suyo en un solo grupo
const RESIDENTE_NAV: NavItem[] = [
  { href: "inicio", label: "Inicio", description: "Resumen de su cuenta y avisos", icon: LayoutDashboard },
  { href: "mi-cuenta", label: "Mi cuenta", description: "Cuotas, pagos y paz y salvo", icon: PiggyBank },
  { href: "mi-portal/pqrs", label: "PQRS", description: "Peticiones, quejas y reclamos", icon: MessageSquareWarning },
  { href: "mi-portal/circulares", label: "Circulares", description: "Comunicados de la administración", icon: Megaphone },
  { href: "mi-portal/reservas", label: "Reservar", description: "Salón social, BBQ y más", icon: CalendarPlus },
  { href: "asambleas", label: "Asambleas", description: "Convocatorias, votaciones y actas", icon: Gavel },
  { href: "mi-unidad", label: "Mi unidad", description: "Sus datos, familia y vehículos", icon: Home },
];

// Atención al residente (personal)
const PORTAL_NAV: (NavItem & { permiso: Parameters<typeof puedePortal>[1] })[] = [
  { href: "portal/pqrs", label: "PQRS", description: "Bandeja y plazos de respuesta", icon: MessageSquareWarning, permiso: "verPqrs" },
  { href: "portal/circulares", label: "Circulares", description: "Comunicados a residentes", icon: Megaphone, permiso: "verPqrs" },
  { href: "portal/reservas", label: "Reservas", description: "Solicitudes y reglas de zonas", icon: CalendarPlus, permiso: "verReservas" },
];

const RECAUDOS_NAV: (NavItem & { permiso: Parameters<typeof puede>[1] })[] = [
  { href: "recaudos", label: "Resumen", description: "Ingresos del mes", icon: LayoutDashboard, permiso: "resumen", exact: true },
  { href: "recaudos/nuevo", label: "Registrar", description: "Cobro rápido en recepción", icon: CirclePlus, permiso: "registrar" },
  { href: "recaudos/movimientos", label: "Movimientos", description: "Buscar y auditar recaudos", icon: ListOrdered, permiso: "movimientos" },
  { href: "recaudos/caja", label: "Caja", description: "Cierres y entregas de efectivo", icon: Wallet, permiso: "caja" },
  { href: "recaudos/conciliacion", label: "Conciliación", description: "Consignaciones y bancos", icon: Landmark, permiso: "conciliacion" },
  { href: "recaudos/alertas", label: "Alertas", description: "Descuadres y pendientes", icon: ShieldAlert, permiso: "alertas" },
  { href: "recaudos/reportes", label: "Reportes", description: "Excel, PDF y cortes mensuales", icon: FileBarChart, permiso: "reportes" },
  { href: "recaudos/configuracion", label: "Configuración", description: "Conceptos y tarifas", icon: Settings2, permiso: "configurar" },
];

function initials(name: string) {
  return name
    .replace(/\(.*\)/, "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user, memberships, tenant, isAdmin } = useTenant();
  const pathname = usePathname();
  const router = useRouter();
  // Misma clave SWR que la página de vencimientos: el contador se actualiza al confirmar
  const { data: deadlines } = useDeadlines(tenant.tenant_id, isAdmin);
  const alerts = alertCount(deadlines?.deadlines);
  const recaudos = RECAUDOS_NAV.filter((i) => puede(tenant.role, i.permiso));
  const activos = ACTIVOS_NAV.filter((i) => puedeActivos(tenant.role, i.permiso));
  const unidades: NavItem[] = [
    ...UNIDADES_NAV.filter((i) => puedeUnidades(tenant.role, i.permiso)),
    ...(tenant.role !== "RESIDENTE" && puedeAsambleas(tenant.role, "ver") ? [ASAMBLEAS_ITEM] : []),
  ];
  const cartera = CARTERA_NAV.filter((i) => puedeCartera(tenant.role, i.permiso));
  const residente = tenant.role === "RESIDENTE";
  const portal = PORTAL_NAV.filter((i) => puedePortal(tenant.role, i.permiso));
  // Contadores del portal: PQRS vencidas o sin atender y reservas por decidir
  const { data: pendientesPortal } = useSWR<PendientesPersonal>(
    portal.length ? `${basePortal(tenant.tenant_id)}/pendientes` : null,
    fetcher,
    { refreshInterval: 60_000 },
  );
  // Contador: novedades reportadas que nadie ha atendido todavía
  const { data: sinAtender } = useSWR<Novedad[]>(
    puedeActivos(tenant.role, "ver") ? `${baseActivos(tenant.tenant_id)}/novedades?estado=REPORTADA` : null,
    fetcher,
    { refreshInterval: 60_000 },
  );
  const { data: alertasRecaudo } = useSWR<Alerta[]>(
    puede(tenant.role, "alertas") ? `${base(tenant.tenant_id)}/alertas` : null,
    fetcher,
    { refreshInterval: 60_000 },
  );

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    // Recarga completa: borra la caché en memoria para que el siguiente usuario
    // de esta pestaña no vea, ni por un instante, datos del anterior.
    window.location.assign("/login");
  }

  const renderItem = (item: NavItem) => {
    const href = `/${tenant.tenant_slug}/${item.href}`;
    // La ficha de una unidad (/unidades/{id}) y la importación también marcan «Unidades»; el directorio no
    const active = item.exact
      ? pathname === href || (item.href === "unidades" && pathname.startsWith(`${href}/`) && !pathname.startsWith(`${href}/directorio`)) ||
        (item.href === "cartera" && pathname.startsWith(`${href}/unidades/`))
      : pathname.startsWith(href);
    return (
      <li key={item.href}>
        <Link
          href={href}
          onClick={onNavigate}
          aria-current={active ? "page" : undefined}
          className={cn(
            "group flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors",
            active
              ? "bg-sidebar-accent text-white shadow-[inset_3px_0_0_0_var(--sidebar-primary)]"
              : "text-sidebar-foreground/85 hover:bg-sidebar-accent/60 hover:text-white",
          )}
        >
          <item.icon className={cn("size-4 shrink-0", active ? "text-white" : "text-sidebar-muted group-hover:text-white")} />
          <span className="min-w-0 flex-1">
            <span className="block leading-tight font-medium">{item.label}</span>
            <span className="block truncate text-xs leading-tight text-sidebar-muted">{item.description}</span>
          </span>
          {item.href === "deadlines" && alerts > 0 && (
            <span
              className="flex h-5 min-w-5 items-center justify-center rounded-full bg-warning-soft px-1.5 text-[11px] font-semibold text-warning"
              aria-label={`${alerts} vencimientos requieren atención`}
              title="Por revisar o con vencimiento en 7 días o menos"
            >
              {alerts}
            </span>
          )}
          {item.href === "activos/novedades" && (sinAtender?.length ?? 0) > 0 && (
            <span
              className="flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-[11px] font-semibold text-white"
              aria-label={`${sinAtender?.length} novedades sin atender`}
              title="Reportadas y sin atender"
            >
              {sinAtender?.length}
            </span>
          )}
          {item.href === "portal/pqrs" && (pendientesPortal?.pqrs_abiertas ?? 0) > 0 && (
            <span
              className={cn(
                "flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-semibold",
                pendientesPortal?.pqrs_vencidas ? "bg-destructive text-white" : "bg-warning-soft text-warning",
              )}
              aria-label={`${pendientesPortal?.pqrs_abiertas} PQRS abiertas, ${pendientesPortal?.pqrs_vencidas} vencidas`}
              title={pendientesPortal?.pqrs_vencidas ? `${pendientesPortal.pqrs_vencidas} vencidas` : "Abiertas"}
            >
              {pendientesPortal?.pqrs_abiertas}
            </span>
          )}
          {item.href === "portal/reservas" && (pendientesPortal?.reservas_por_decidir ?? 0) > 0 && (
            <span
              className="flex h-5 min-w-5 items-center justify-center rounded-full bg-warning-soft px-1.5 text-[11px] font-semibold text-warning"
              aria-label={`${pendientesPortal?.reservas_por_decidir} reservas por aprobar`}
            >
              {pendientesPortal?.reservas_por_decidir}
            </span>
          )}
          {item.href === "recaudos/alertas" && (alertasRecaudo?.length ?? 0) > 0 && (
            <span
              className="flex h-5 min-w-5 items-center justify-center rounded-full bg-warning-soft px-1.5 text-[11px] font-semibold text-warning"
              aria-label={`${alertasRecaudo?.length} alertas de recaudos abiertas`}
            >
              {alertasRecaudo?.length}
            </span>
          )}
          {item.soon && (
            <span className="rounded border border-sidebar-border px-1.5 py-px text-[10px] font-medium tracking-wide text-sidebar-muted uppercase">
              Pronto
            </span>
          )}
        </Link>
      </li>
    );
  };

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      {/* Marca */}
      <div className="flex items-center gap-2.5 px-4 pt-5 pb-4">
        <div className="flex size-8 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
          <Building2 className="size-4.5" />
        </div>
        <span className="font-semibold tracking-tight text-white">PH Gestión</span>
      </div>

      {/* Copropiedad actual */}
      <div className="px-3">
        <DropdownMenu>
          <DropdownMenuTrigger
            disabled={memberships.length < 2}
            className="flex w-full items-center gap-2.5 rounded-md border border-sidebar-border bg-sidebar-accent/40 px-3 py-2.5 text-left transition-colors enabled:hover:bg-sidebar-accent disabled:cursor-default"
          >
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-medium tracking-wide text-sidebar-muted uppercase">Copropiedad</p>
              <p className="truncate text-sm font-medium text-white">{tenant.tenant_name}</p>
            </div>
            {memberships.length > 1 && <ChevronsUpDown className="size-4 text-sidebar-muted" />}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-60">
            <DropdownMenuLabel>Cambiar de copropiedad</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {memberships.map((m) => (
              <DropdownMenuItem
                key={m.tenant_id}
                onSelect={() => {
                  onNavigate?.();
                  router.push(`/${m.tenant_slug}/search`);
                }}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate">{m.tenant_name}</p>
                  <p className="text-xs text-muted-foreground">{ROLE_LABEL[m.role]}</p>
                </div>
                {m.tenant_id === tenant.tenant_id && <Check className="size-4" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Navegación */}
      <nav className="mt-5 flex-1 space-y-6 overflow-y-auto px-3" aria-label="Principal">
        {residente && (
          <div>
            <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-sidebar-muted uppercase">Mi portal</p>
            <ul className="space-y-1">{RESIDENTE_NAV.map(renderItem)}</ul>
          </div>
        )}
        <ul className="space-y-1">{MAIN_NAV.map(renderItem)}</ul>
        {portal.length > 0 && (
          <div>
            <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-sidebar-muted uppercase">Atención al residente</p>
            <ul className="space-y-1">{portal.map(renderItem)}</ul>
          </div>
        )}
        {unidades.length > 0 && (
          <div>
            <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-sidebar-muted uppercase">Copropiedad</p>
            <ul className="space-y-1">{unidades.map(renderItem)}</ul>
          </div>
        )}
        {isAdmin && (
          <div>
            <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-sidebar-muted uppercase">
              Herramientas de administración
            </p>
            <ul className="space-y-1">{ADMIN_NAV.map(renderItem)}</ul>
          </div>
        )}
        {cartera.length > 0 && (
          <div>
            <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-sidebar-muted uppercase">Cartera</p>
            <ul className="space-y-1">{cartera.map(renderItem)}</ul>
          </div>
        )}
        {activos.length > 0 && (
          <div>
            <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-sidebar-muted uppercase">Mantenimiento</p>
            <ul className="space-y-1">{activos.map(renderItem)}</ul>
          </div>
        )}
        {recaudos.length > 0 && (
          <div>
            <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-sidebar-muted uppercase">Recaudos</p>
            <ul className="space-y-1">{recaudos.map(renderItem)}</ul>
          </div>
        )}
      </nav>

      {/* Usuario */}
      <div className="border-t border-sidebar-border p-3">
        <div className="flex items-center gap-2.5 rounded-md px-1.5 py-1">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-sidebar-accent text-xs font-semibold text-white">
            {initials(user.full_name)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-white">{user.full_name.replace(/\s*\(.*\)/, "")}</p>
            <p className="truncate text-xs text-sidebar-muted">{ROLE_LABEL[tenant.role]}</p>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={logout}
                className="rounded-md p-1.5 text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-white"
                aria-label="Cerrar sesión"
              >
                <LogOut className="size-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="top">Cerrar sesión</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  );
}
