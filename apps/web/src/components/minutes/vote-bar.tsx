"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Vote } from "@/lib/types";

/*
  Barra apilada de votación. Paleta validada con el script de dataviz
  (protan ΔE 20,4; normal ΔE 25,6; contraste >= 3:1): azul = a favor,
  naranja tostado = en contra, gris neutro = abstención. Se evita verde/rojo
  (indistinguibles para daltonismo rojo-verde). Separación de 2 px entre
  segmentos, extremos redondeados y los porcentajes siempre escritos: el color
  nunca es la única forma de leer el resultado.
*/
export const VOTE_COLORS = { yes: "#2f6db0", no: "#b65a26", abstain: "#c9cdd3" } as const;
const LABELS = { yes: "A favor", no: "En contra", abstain: "Abstención" } as const;

const pct = (n: number) => `${n.toLocaleString("es-CO", { maximumFractionDigits: 1 })} %`;

export function VoteLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
      {(Object.keys(LABELS) as (keyof typeof LABELS)[]).map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: VOTE_COLORS[k] }} /> {LABELS[k]}
        </span>
      ))}
    </div>
  );
}

export function VoteBar({ vote }: { vote: Vote }) {
  const parts = (["yes", "no", "abstain"] as const)
    .map((k) => ({ key: k, value: vote[`${k}_pct` as const] }))
    .filter((p): p is { key: "yes" | "no" | "abstain"; value: number } => p.value !== null && p.value > 0);
  const known = parts.reduce((s, p) => s + p.value, 0);
  const rest = Math.max(0, 100 - known);

  return (
    <div>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded" role="img" aria-label={`Votación: ${parts.map((p) => `${LABELS[p.key]} ${pct(p.value)}`).join(", ")}`}>
        {parts.map((p) => (
          <Tooltip key={p.key}>
            <TooltipTrigger asChild>
              <div className="h-full first:rounded-l last:rounded-r" style={{ width: `${p.value}%`, background: VOTE_COLORS[p.key] }} />
            </TooltipTrigger>
            <TooltipContent>
              {LABELS[p.key]}: {pct(p.value)}
            </TooltipContent>
          </Tooltip>
        ))}
        {rest > 0.5 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="h-full rounded-r bg-muted" style={{ width: `${rest}%` }} />
            </TooltipTrigger>
            <TooltipContent>El acta no desglosa el {pct(rest)} restante</TooltipContent>
          </Tooltip>
        )}
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground tabular-nums">
        {parts.map((p) => `${LABELS[p.key]} ${pct(p.value)}`).join(" · ")}
        {rest > 0.5 && " · resto sin desglose"}
      </p>
    </div>
  );
}
