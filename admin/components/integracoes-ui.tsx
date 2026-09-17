"use client";

import { cn } from "@/lib/cn";
import { Check, Copy, X } from "lucide-react";
import { useState } from "react";

// Peças compartilhadas pelas abas da tela de Integrações (chaves e webhooks).

export function quando(iso: string | null) {
  return iso
    ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" })
    : "—";
}

export function Copiar({ texto, className }: { texto: string; className?: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(texto).then(() => {
          setOk(true);
          setTimeout(() => setOk(false), 1500);
        }).catch(() => {});
      }}
      title="Copiar"
      className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink", className)}
    >
      {ok ? <Check size={15} className="text-success" /> : <Copy size={15} />}
    </button>
  );
}

export function AcaoBtn({ children, onClick, title, danger }: {
  children: React.ReactNode; onClick: () => void; title: string; danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn(
        "grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-surface-2",
        danger ? "hover:text-danger" : "hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

export function Modal({ titulo, children, onClose, largo }: {
  titulo: string; children: React.ReactNode; onClose: () => void; largo?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className={cn(
        "relative z-10 max-h-[90dvh] w-full overflow-y-auto rounded-2xl border bg-surface p-6 shadow-lift",
        largo ? "max-w-2xl" : "max-w-lg",
      )}>
        <div className="flex items-start justify-between">
          <h2 className="text-base font-semibold text-ink">{titulo}</h2>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}

export const inputCls = "w-full rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40";
