"use client";

import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";

export async function cerrarSesion() {
  await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
  window.location.assign("/login");
}

export function BotonSalir({ className, variant = "outline" }: { className?: string; variant?: "outline" | "ghost" }) {
  return (
    <Button type="button" variant={variant} className={className} onClick={() => void cerrarSesion()}>
      <LogOut className="size-4" />
      Cerrar sesión
    </Button>
  );
}
