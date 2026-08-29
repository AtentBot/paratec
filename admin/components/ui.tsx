import { cn } from "@/lib/cn";
import type { ReactNode } from "react";

export function Card({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border bg-surface shadow-card",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b px-5 py-4">
      <div>
        <h3 className="text-sm font-semibold tracking-tight text-ink">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

const toneMap: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted ring-1 ring-inset ring-border",
  accent: "bg-accent-soft text-accent-ink ring-1 ring-inset ring-accent/30",
  success: "bg-success/10 text-success ring-1 ring-inset ring-success/25",
  warning: "bg-warning/10 text-warning ring-1 ring-inset ring-warning/25",
  danger: "bg-danger/10 text-danger ring-1 ring-inset ring-danger/25",
  info: "bg-info/10 text-info ring-1 ring-inset ring-info/25",
};

export function Badge({
  tone = "neutral",
  children,
  className,
  dot,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        toneMap[tone],
        className,
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function Pill({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <code
      className={cn(
        "rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-muted ring-1 ring-inset ring-border",
        className,
      )}
    >
      {children}
    </code>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      {icon && <div className="text-faint">{icon}</div>}
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="max-w-xs text-xs text-muted">{hint}</p>}
    </div>
  );
}
