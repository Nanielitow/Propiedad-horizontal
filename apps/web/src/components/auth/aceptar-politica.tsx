"use client";

import { Loader2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { cerrarSesion } from "@/components/auth/boton-salir";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { POLITICA_FECHA, POLITICA_VERSION } from "@/lib/politica";

/** Pide aceptar la política de datos vigente cuando cambió desde la última vez (prueba de autorización, Ley 1581).
 *  No se puede cerrar sin aceptar; la alternativa es cerrar sesión. */
export function AceptarPolitica({ requiere }: { requiere?: boolean }) {
  const [abierto, setAbierto] = useState(!!requiere);
  const [acepta, setAcepta] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function aceptar() {
    setEnviando(true);
    setError(null);
    try {
      await api("/auth/aceptar-politica", { method: "POST", json: { version: POLITICA_VERSION } });
      setAbierto(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo registrar la aceptación.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <AlertDialog open={abierto}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-primary" />
            Actualizamos la política de tratamiento de datos
          </AlertDialogTitle>
          <AlertDialogDescription>
            La política vigente desde el {POLITICA_FECHA} identifica al encargado del tratamiento, detalla cómo ejercer sus
            derechos y explica el tratamiento de datos de menores y los proveedores que usamos. Para seguir usando PH Gestión
            necesitamos su autorización.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <label className="flex items-start gap-2.5 text-sm">
          <input
            type="checkbox"
            checked={acepta}
            onChange={(e) => setAcepta(e.target.checked)}
            className="mt-0.5 size-4 shrink-0 accent-primary"
          />
          <span>
            He leído y autorizo el tratamiento de mis datos personales según la{" "}
            <Link href="/privacidad" target="_blank" className="font-medium text-primary underline-offset-4 hover:underline">
              política de tratamiento de datos
            </Link>{" "}
            (Ley 1581 de 2012).
          </span>
        </label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <AlertDialogFooter>
          <Button variant="outline" onClick={() => void cerrarSesion()}>
            Cerrar sesión
          </Button>
          <Button onClick={() => void aceptar()} disabled={!acepta || enviando}>
            {enviando && <Loader2 className="size-4 animate-spin" />}
            Aceptar y continuar
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
