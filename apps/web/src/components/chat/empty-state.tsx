import { FileSearch, MessageSquareText, MousePointerClick } from "lucide-react";

import type { Role } from "@/lib/types";

const SUGGESTIONS = {
  RESIDENTE: [
    "¿Se permiten mascotas y qué requisitos hay?",
    "¿Cuál es el horario de la piscina?",
    "¿En qué horario se pueden hacer remodelaciones?",
    "¿Qué horario de silencio se debe respetar?",
  ],
  ADMIN: [
    "¿Hasta cuándo está vigente la póliza de áreas comunes?",
    "¿Qué se aprobó en la última asamblea?",
    "¿Cuánto costó la impermeabilización de la torre 2?",
    "¿Qué dice el manual sobre las mascotas?",
  ],
} as const;

const STEPS = [
  { icon: MessageSquareText, title: "Pregunte", text: "en lenguaje natural, como se lo preguntaría a la administración." },
  { icon: FileSearch, title: "Lea la respuesta", text: "construida solo con los documentos oficiales del conjunto." },
  { icon: MousePointerClick, title: "Verifique", text: "pulsando el número de cada cita para abrir la página exacta." },
];

export function ChatEmptyState({
  role,
  tenantName,
  onPick,
}: {
  role: Role;
  tenantName: string;
  onPick: (q: string) => void;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center py-8 text-center sm:py-14">
      <div className="flex size-12 items-center justify-center rounded-lg bg-accent text-primary">
        <FileSearch className="size-6" />
      </div>
      <h2 className="mt-4 text-xl font-semibold tracking-tight">¿Qué necesita consultar?</h2>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">
        Pregunte sobre los documentos de {tenantName}. Cada respuesta indica el documento y la página de donde
        proviene.
      </p>

      <div className="mt-8 grid w-full gap-2 sm:grid-cols-2">
        {(role === "ADMIN" ? SUGGESTIONS.ADMIN : SUGGESTIONS.RESIDENTE).map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onPick(q)}
            className="rounded-md border bg-card px-4 py-3 text-left text-sm transition-colors hover:border-primary/40 hover:bg-accent/60"
          >
            {q}
          </button>
        ))}
      </div>

      <div className="mt-10 grid w-full gap-4 border-t pt-8 text-left sm:grid-cols-3">
        {STEPS.map(({ icon: Icon, title, text }, i) => (
          <div key={title} className="flex gap-3">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold text-secondary-foreground">
              {i + 1}
            </div>
            <div>
              <p className="flex items-center gap-1.5 text-sm font-medium">
                <Icon className="size-3.5 text-muted-foreground" />
                {title}
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
