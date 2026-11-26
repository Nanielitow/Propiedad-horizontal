"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { ClaveDesdeEnlace } from "@/components/auth/clave-form";
import { EnlaceInvalido } from "@/components/auth/enlace-invalido";

interface Enlace {
  tipo: "INVITACION" | "RECUPERACION";
  email: string;
  nombre: string;
  copropiedad: string | null;
  requiere_politica: boolean;
}

type Estado = { fase: "cargando" } | { fase: "invalido" } | { fase: "listo"; token: string; enlace: Enlace };

/** Lee el token de la parte de la dirección tras "#" (que el navegador nunca envía a ningún servidor),
 *  lo borra de la barra de direcciones y del historial, y pide sus datos por POST. */
export function EnlaceDesdeFragmento({ modo }: { modo: "activar" | "restablecer" }) {
  const [estado, setEstado] = useState<Estado>({ fase: "cargando" });

  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.slice(1));
    // Compatibilidad con enlaces anteriores (?token=…)
    const token = hash.get("token") ?? new URLSearchParams(window.location.search).get("token");
    window.history.replaceState(null, "", window.location.pathname);
    if (!token) {
      setEstado({ fase: "invalido" });
      return;
    }
    const tipo = modo === "activar" ? "INVITACION" : "RECUPERACION";
    fetch("/api/auth/enlace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (res) => {
        const enlace = res.ok ? ((await res.json()) as Enlace) : null;
        setEstado(enlace && enlace.tipo === tipo ? { fase: "listo", token, enlace } : { fase: "invalido" });
      })
      .catch(() => setEstado({ fase: "invalido" }));
  }, [modo]);

  if (estado.fase === "cargando") {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Verificando el enlace…
      </div>
    );
  }
  if (estado.fase === "invalido") return <EnlaceInvalido recuperacion={modo === "restablecer"} />;
  const { token, enlace } = estado;
  return (
    <ClaveDesdeEnlace
      modo={modo}
      token={token}
      nombre={enlace.nombre}
      email={enlace.email}
      copropiedad={enlace.copropiedad}
      requierePolitica={modo === "activar" && enlace.requiere_politica}
    />
  );
}
