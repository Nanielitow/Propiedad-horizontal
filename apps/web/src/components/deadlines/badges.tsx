import {
  Building,
  FileSignature,
  type LucideIcon,
  ShieldCheck,
  Stamp,
  Tag,
  Wrench,
} from "lucide-react";

import { confidenceLevel, DEADLINE_TYPE, relativeLabel, urgency, type Urgency } from "@/lib/deadlines";
import type { DeadlineType } from "@/lib/types";
import { cn } from "@/lib/utils";

const TYPE_ICON: Record<DeadlineType, LucideIcon> = {
  POLICY_EXPIRY: ShieldCheck,
  CONTRACT_END: FileSignature,
  MAINTENANCE: Wrench,
  CERTIFICATION: Stamp,
  OTHER: Tag,
};

export function TypeBadge({ type }: { type: DeadlineType }) {
  const Icon = TYPE_ICON[type] ?? Building;
  return (
    <span className="inline-flex items-center gap-1 rounded border bg-card px-1.5 py-0.5 text-xs text-muted-foreground">
      <Icon className="size-3" />
      {DEADLINE_TYPE[type]}
    </span>
  );
}

export const URGENCY_STYLE: Record<Urgency, string> = {
  overdue: "bg-destructive/10 text-destructive border-destructive/25",
  critical: "bg-destructive/10 text-destructive border-destructive/25",
  soon: "bg-warning-soft text-warning border-warning/25",
  later: "bg-secondary text-secondary-foreground border-transparent",
};

export function UrgencyBadge({ due, className }: { due: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        URGENCY_STYLE[urgency(due)],
        className,
      )}
    >
      {relativeLabel(due)}
    </span>
  );
}

export function ConfidencePill({ value }: { value: number | null }) {
  const { label, tone } = confidenceLevel(value);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs",
        tone === "high" && "text-success",
        tone === "medium" && "text-warning",
        tone === "low" && "text-destructive",
      )}
      title="Qué tan explícita es la fecha en el documento"
    >
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={cn(
              "h-2.5 w-1 rounded-full bg-current",
              (tone === "medium" && i > 1) || (tone === "low" && i > 0) ? "opacity-25" : "",
            )}
          />
        ))}
      </span>
      {label}
    </span>
  );
}
