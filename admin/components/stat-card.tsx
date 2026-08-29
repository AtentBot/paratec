import { cn } from "@/lib/cn";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";

export function StatCard({
  label,
  value,
  icon,
  delta,
  hint,
  accent,
}: {
  label: string;
  value: ReactNode;
  icon: ReactNode;
  delta?: number; // variação em %
  hint?: string;
  accent?: boolean;
}) {
  const up = (delta ?? 0) >= 0;
  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-2xl border p-5 shadow-card transition hover:shadow-lift",
        accent ? "border-transparent bg-feature text-feature-fg" : "bg-surface",
      )}
    >
      <div className="flex items-start justify-between">
        <span
          className={cn(
            "grid h-10 w-10 place-items-center rounded-xl",
            accent ? "bg-white/10 text-accent" : "bg-accent-soft text-accent-ink",
          )}
        >
          {icon}
        </span>
        {delta !== undefined && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold",
              up ? "bg-success/10 text-success" : "bg-danger/10 text-danger",
              accent && "bg-white/10 text-white",
            )}
          >
            {up ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
            {Math.abs(delta)}%
          </span>
        )}
      </div>
      <p
        className={cn(
          "mt-4 text-[13px] font-medium",
          accent ? "text-white/70" : "text-muted",
        )}
      >
        {label}
      </p>
      <p className="tnum mt-1 text-3xl font-semibold tracking-tight">{value}</p>
      {hint && (
        <p
          className={cn(
            "mt-1 text-xs",
            accent ? "text-white/60" : "text-faint",
          )}
        >
          {hint}
        </p>
      )}
    </div>
  );
}
