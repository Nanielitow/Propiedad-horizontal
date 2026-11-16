"use client";

import { AlertCircle, Eye, EyeOff, Loader2, UserRound } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";
import { DEMO_MODE } from "@/lib/config";
import type { Me } from "@/lib/types";

const DEMO_ACCOUNTS = [
  { email: "admin@lospinos.demo", label: "Administradora", detail: "Conjunto Los Pinos" },
  { email: "residente@lospinos.demo", label: "Residente", detail: "Conjunto Los Pinos · Apto 502" },
  { email: "admin@torrecentral.demo", label: "Administrador", detail: "Edificio Torre Central" },
];
const DEMO_PASSWORD = "Demo1234!";

export function LoginForm() {
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);

  async function login(emailValue: string, passwordValue: string, key: string) {
    setError(null);
    setLoading(key);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: emailValue.trim(), password: passwordValue }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setError(res.status === 401 ? "Correo o contraseña incorrectos." : errorMessage(data));
        return;
      }
      const first = (data as Me).memberships[0];
      if (!first) {
        setError("Su usuario no está vinculado a ninguna copropiedad. Contacte a la administración.");
        return;
      }
      const next = params.get("next");
      // Navegación COMPLETA (no router.push): descarta cualquier dato en memoria
      // de una sesión anterior en la misma pestaña (caché de SWR, visor, chat).
      window.location.assign(next?.startsWith("/") && !next.startsWith("//") ? next : `/${first.tenant_slug}/search`);
    } catch {
      setError("No se pudo conectar con el servidor.");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div>
      <h2 className="text-2xl font-semibold tracking-tight">Iniciar sesión</h2>
      <p className="mt-1 text-sm text-muted-foreground">Ingrese con el correo registrado en su copropiedad.</p>

      {params.get("expired") && !error && (
        <div className="mt-6 rounded-md border border-warning/30 bg-warning-soft px-3 py-2.5 text-sm text-warning">
          Su sesión expiró. Ingrese de nuevo para continuar.
        </div>
      )}
      {error && (
        <div role="alert" className="mt-6 flex gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          {error}
        </div>
      )}

      <form
        className="mt-6 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void login(email, password, "form");
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="email">Correo electrónico</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="nombre@correo.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="h-10"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Contraseña</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="h-10 pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground"
              aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
            >
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
        <Button type="submit" className="h-10 w-full" disabled={loading !== null}>
          {loading === "form" && <Loader2 className="size-4 animate-spin" />}
          Ingresar
        </Button>
      </form>

      {DEMO_MODE && (
        <div className="mt-10">
          <div className="flex items-center gap-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            <span className="h-px flex-1 bg-border" />
            Cuentas de demostración
            <span className="h-px flex-1 bg-border" />
          </div>
          <div className="mt-4 space-y-2">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                type="button"
                disabled={loading !== null}
                onClick={() => void login(account.email, DEMO_PASSWORD, account.email)}
                className="flex w-full items-center gap-3 rounded-md border bg-card px-3 py-2.5 text-left transition-colors hover:border-primary/40 hover:bg-accent disabled:opacity-60"
              >
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
                  {loading === account.email ? <Loader2 className="size-4 animate-spin" /> : <UserRound className="size-4" />}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium">{account.label}</p>
                  <p className="truncate text-xs text-muted-foreground">{account.detail}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
