"use client";

import { Building2, FlaskConical, Menu } from "lucide-react";
import { useState } from "react";

import { AceptarPolitica } from "@/components/auth/aceptar-politica";
import { PdfPanel } from "@/components/pdf-viewer/pdf-panel";
import { PdfViewerProvider } from "@/components/pdf-viewer/viewer-context";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import type { Membership, User } from "@/lib/types";

import { Sidebar } from "./sidebar";
import { TenantProvider } from "./tenant-context";

interface Props {
  user: User;
  memberships: Membership[];
  current: Membership;
  children: React.ReactNode;
}

export function AppShell({ user, memberships, current, children }: Props) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <TenantProvider value={{ user, memberships, tenant: current, isAdmin: current.role === "ADMIN" }}>
      <PdfViewerProvider>
        <AceptarPolitica requiere={user.requiere_politica} />
        <div className="flex h-dvh overflow-hidden bg-background">
          <aside className="hidden w-64 shrink-0 lg:block">
            <Sidebar />
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            {current.is_demo && (
              <div className="flex items-center justify-center gap-2 border-b border-warning/20 bg-warning-soft px-4 py-1.5 text-center text-xs text-warning">
                <FlaskConical className="size-3.5 shrink-0" />
                <span>
                  <span className="font-medium">Conjunto de demostración:</span> datos ficticios compartidos con otros
                  visitantes. No suba información personal real.
                </span>
              </div>
            )}
            {/* Barra superior solo en móvil/tablet */}
            <header className="flex items-center gap-3 border-b bg-sidebar px-3 py-2.5 text-sidebar-foreground lg:hidden">
              <Button
                variant="ghost"
                size="icon"
                className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-white"
                onClick={() => setMobileNavOpen(true)}
                aria-label="Abrir menú"
              >
                <Menu />
              </Button>
              <Building2 className="size-4 text-sidebar-muted" />
              <span className="truncate text-sm font-medium text-white">{current.tenant_name}</span>
            </header>

            <div className="flex min-h-0 flex-1">
              <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">{children}</main>
              <PdfPanel />
            </div>
          </div>
        </div>

        <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
          <SheetContent side="left" showCloseButton={false} className="w-64 border-none p-0">
            <SheetTitle className="sr-only">Menú de navegación</SheetTitle>
            <Sidebar onNavigate={() => setMobileNavOpen(false)} />
          </SheetContent>
        </Sheet>
      </PdfViewerProvider>
    </TenantProvider>
  );
}
