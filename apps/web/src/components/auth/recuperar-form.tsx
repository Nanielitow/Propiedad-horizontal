"use client";

import { Loader2, MailCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Aviso } from "@/components/auth/clave-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";

export function RecuperarForm() {
  const [email, setEmail] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar() {
    setError(null);
    setEnviando(true);
    try {
      const res = await fetch("/api/auth/recuperar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      if (!res.ok) {
        setError(errorMessage(await res.json().catch(() => null), "No se pudo enviar la solicitud."));
        return;
      }
      setEnviado(true);
    } catch {
      setError("No se pudo conectar con el servidor.");
    } finally {
      setEnviando(false);
    }
  }

  if (enviado) {
    return (
      <div>
        <div className="flex size-10 items-center justify-center rounded-full bg-success-soft">
          <MailCheck className="size-5 text-success" />
        </div>
        <h2 className="mt-4 text-2xl font-semibold tracking-tight">Revise su correo</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Si <span className="font-medium text-foreground">{email.trim()}</span> está registrado, en unos minutos le
          llegará un enlace para elegir una contraseña nueva. Vence en 1 hora. Revise también la carpeta de correo no
          deseado.
        </p>
        <Button asChild variant="outline" className="mt-6 h-10 w-full">
          <Link href="/login">Volver a iniciar sesión</Link>
        </Button>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-2xl font-semibold tracking-tight">¿Olvidó su contraseña?</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Escriba el correo con el que entra a PH Gestión y le enviaremos un enlace para elegir una nueva.
      </p>
      {error && <Aviso>{error}</Aviso>}
      <form
        className="mt-6 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar();
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
            autoFocus
            className="h-10"
          />
        </div>
        <Button type="submit" className="h-10 w-full" disabled={enviando}>
          {enviando && <Loader2 className="size-4 animate-spin" />}
          Enviar enlace
        </Button>
      </form>
      <p className="mt-6 text-center text-sm">
        <Link href="/login" className="text-primary underline-offset-4 hover:underline">
          Volver a iniciar sesión
        </Link>
      </p>
    </div>
  );
}
