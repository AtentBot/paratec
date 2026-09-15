"use client";

import { Loader2, Search } from "lucide-react";

export function Busca({ q, onChange, placeholder }: {
  q: string; onChange: (v: string) => void; placeholder: string;
}) {
  return (
    <div className="relative max-w-sm">
      <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
      <input
        value={q}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border bg-surface py-2.5 pl-9 pr-3 text-sm text-ink outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/40"
      />
    </div>
  );
}

export function Carregando() {
  return (
    <div className="flex items-center gap-2 text-muted">
      <Loader2 size={16} className="animate-spin" /> Carregando…
    </div>
  );
}

export function Pager({ offset, limit, count, total, onChange }: {
  offset: number; limit: number; count: number; total: number; onChange: (o: number) => void;
}) {
  const inicio = total === 0 ? 0 : offset + 1;
  const fim = offset + count;
  return (
    <div className="flex items-center justify-between text-xs text-muted">
      <span>{inicio}–{fim} de {total}</span>
      <div className="flex gap-2">
        <button
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
          className="rounded-lg border px-3 py-1.5 font-medium text-ink transition hover:bg-surface-2 disabled:opacity-40"
        >
          Anterior
        </button>
        <button
          disabled={fim >= total}
          onClick={() => onChange(offset + limit)}
          className="rounded-lg border px-3 py-1.5 font-medium text-ink transition hover:bg-surface-2 disabled:opacity-40"
        >
          Próxima
        </button>
      </div>
    </div>
  );
}
