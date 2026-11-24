"use client";

import {
  AlertTriangle,
  Boxes,
  Building2,
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
  { href: "activos", label: "Activos", description: "Hojas de vida y semáforo", icon: Boxes, permiso: "ver", exact: true },
  { href: "activos/calendario", label: "Calendario", description: "Fechas de mantenimiento", icon: CalendarDays, permiso: "ver" },
  { href: "activos/novedades", label: "Novedades", description: "Fallas y su atención", icon: AlertTriangle, permiso: "ver" },
  { href: "activos/recomendaciones", label: "Recomendaciones", description: "Sugerencias de los técnicos", icon: ListChecks, permiso: "ver" },
  { href: "activos/planes", label: "Planes", description: "Mantenimiento preventivo", icon: CalendarClock, permiso: "contratistas" },
  { href: "activos/contratistas", label: "Contratistas", description: "Empresas y contratos", icon: HardHat, permiso: "contratistas" },
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
  // Contador: novedades reportadas que nadie ha atendido todavía
  const { data: sinAtender } = useSWR<Novedad[]>(
    activos.length ? `${baseActivos(tenant.tenant_id)}/novedades?estado=REPORTADA` : null,
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
    const active = item.exact ? pathname === href : pathname.startsWith(href);
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
        <ul className="space-y-1">{MAIN_NAV.map(renderItem)}</ul>
        {isAdmin && (
          <div>
            <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-sidebar-muted uppercase">
              Herramientas de administración
            </p>
            <ul className="space-y-1">{ADMIN_NAV.map(renderItem)}</ul>
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
