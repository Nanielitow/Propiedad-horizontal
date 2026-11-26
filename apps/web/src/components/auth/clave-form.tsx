"use client";

import { AlertCircle, Check, Eye, EyeOff, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";
import { destinoInicial } from "@/lib/destino";
import type { Me } from "@/lib/types";
import { cn } from "@/lib/utils";

export const MIN_CLAVE = 10;

/** Contraseña nueva + confirmación, con los requisitos a la vista. */
export function CamposClave({
  clave,
  confirmar,
  onClave,
  onConfirmar,
  autoFocus,
}: {
  clave: string;
  confirmar: string;
  onClave: (v: string) => void;
  onConfirmar: (v: string) => void;
  autoFocus?: boolean;
}) {
  const [ver, setVer] = useState(false);
  const requisitos = [
    { ok: clave.length >= MIN_CLAVE, texto: `Al menos ${MIN_CLAVE} caracteres` },
    { ok: new Set(clave).size >= 4, texto: "No repetir siempre el mismo carácter" },
    { ok: clave.length > 0 && clave === confirmar, texto: "Las dos contraseñas coinciden" },
  ];
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="clave">Contraseña nueva</Label>
        <div className="relative">
          <Input
            id="clave"
            type={ver ? "text" : "password"}
            autoComplete="new-password"
            value={clave}
            onChange={(e) => onClave(e.target.value)}
            required
            autoFocus={autoFocus}
            className="h-10 pr-10"
          />
          <button
            type="button"
            onClick={() => setVer((v) => !v)}
            className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground"
            aria-label={ver ? "Ocultar contraseña" : "Mostrar contraseña"}
          >
            {ver ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="confirmar">Repita la contraseña</Label>
        <Input
          id="confirmar"
          type={ver ? "text" : "password"}
          autoComplete="new-password"
          value={confirmar}
          onChange={(e) => onConfirmar(e.target.value)}
          required
          className="h-10"
        />
      </div>
      <ul className="space-y-1 text-xs">
        {requisitos.map((r) => (
          <li key={r.texto} className={cn("flex items-center gap-1.5", r.ok ? "text-success" : "text-muted-foreground")}>
            <Check className={cn("size-3.5", !r.ok && "opacity-30")} />
            {r.texto}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function claveValida(clave: string, confirmar: string): boolean {
  return clave.length >= MIN_CLAVE && new Set(clave).size >= 4 && clave === confirmar;
}

export function Aviso({ children }: { children: React.ReactNode }) {
  return (
    <div role="alert" className="mt-6 flex gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

interface Props {
  modo: "activar" | "restablecer";
  token: string;
  nombre: string;
  email: string;
  copropiedad: string | null;
  requierePolitica: boolean;
}

/** Definir la contraseña desde un enlace del correo (primera vez o recuperación). Al terminar, entra solo. */
export function ClaveDesdeEnlace({ modo, token, nombre, email, copropiedad, requierePolitica }: Props) {
  const [clave, setClave] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [acepta, setAcepta] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const pidePolitica = modo === "activar" && requierePolitica;
  const listo = claveValida(clave, confirmar) && (!pidePolitica || acepta);

  async function enviar() {
    setError(null);
    setEnviando(true);
    try {
      const body = modo === "activar" ? { token, password: clave, acepta_politica: acepta || !pidePolitica } : { token, password: clave };
      const res = await fetch(`/api/auth/${modo}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        setError(errorMessage(data, "No se pudo guardar la contraseña."));
        return;
      }
      const destino = destinoInicial(data as Me);
      window.location.assign(destino ?? "/sin-acceso");
    } catch {
      setError("No se pudo conectar con el servidor.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div>
      <h2 className="text-2xl font-semibold tracking-tight">
        {modo === "activar" ? `Bienvenido(a), ${nombre.split(" ")[0]}` : "Elija una contraseña nueva"}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {modo === "activar"
          ? `Defina su contraseña para entrar a ${copropiedad ?? "PH Gestión"}.`
          : "Al guardarla se cerrarán las sesiones abiertas en otros equipos."}
      </p>
      <p className="mt-4 rounded-md border bg-muted/40 px-3 py-2 text-sm">
        <span className="text-muted-foreground">Cuenta: </span>
        <span className="font-medium">{email}</span>
      </p>

      {error && <Aviso>{error}</Aviso>}

      <form
        className="mt-6 space-y-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (listo) void enviar();
        }}
      >
        <CamposClave clave={clave} confirmar={confirmar} onClave={setClave} onConfirmar={setConfirmar} autoFocus />
        {pidePolitica && (
          <label className="flex items-start gap-2.5 text-sm">
            <input
              type="checkbox"
              checked={acepta}
              onChange={(e) => setAcepta(e.target.checked)}
              className="mt-0.5 size-4 shrink-0 accent-primary"
            />
            <span>
              Autorizo el tratamiento de mis datos personales según la{" "}
              <Link href="/privacidad" target="_blank" className="font-medium text-primary underline-offset-4 hover:underline">
                política de tratamiento de datos
              </Link>{" "}
              (Ley 1581 de 2012).
            </span>
          </label>
        )}
        <Button type="submit" className="h-10 w-full" disabled={!listo || enviando}>
          {enviando && <Loader2 className="size-4 animate-spin" />}
          {modo === "activar" ? "Activar mi cuenta" : "Guardar y entrar"}
        </Button>
      </form>
    </div>
  );
}
