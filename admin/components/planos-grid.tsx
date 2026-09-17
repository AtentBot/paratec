"use client";

import { precoPlano } from "@/lib/format";
import type { Plano } from "@/lib/types";

/** Cards de plano com botão "Assinar" (usado em /precos e /ativar). */
export function PlanosGrid({
  planos,
  ocupado,
  onAssinar,
}: {
  planos: Plano[];
  ocupado: string | null;
  onAssinar: (id: string) => void;
}) {
  return (
    <div className="grid gap-5 md:grid-cols-3">
      {planos.map((p) => {
        const destaque = p.id === "profissional";
        return (
          <div
            key={p.id}
            className={"flex flex-col rounded-2xl border p-6 shadow-card " + (destaque ? "bg-feature text-feature-fg" : "bg-surface")}
          >
            {destaque && (
              <span className="mb-3 w-fit rounded-full bg-cta px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-cta-fg">
                Mais vendido
              </span>
            )}
            <h3 className={"text-lg font-semibold " + (destaque ? "text-feature-fg" : "text-ink")}>{p.nome}</h3>
            <p className={"mt-1 text-sm " + (destaque ? "text-white/70" : "text-muted")}>{p.descricao}</p>
            <div className="mt-5 flex items-end gap-1">
              <span className={"text-4xl font-bold " + (destaque ? "text-feature-fg" : "text-ink")}>
                R$ {precoPlano(p.preco)}
              </span>
              <span className={"pb-1 text-sm " + (destaque ? "text-white/70" : "text-muted")}>/mês</span>
            </div>
            <button
              onClick={() => onAssinar(p.id)}
              disabled={!p.disponivel || ocupado !== null}
              className={
                "mt-6 rounded-xl px-4 py-2.5 text-center text-sm font-semibold transition disabled:opacity-60 " +
                (destaque ? "bg-cta text-cta-fg hover:opacity-90" : "bg-feature text-feature-fg hover:opacity-90")
              }
            >
              {ocupado === p.id ? "Redirecionando…" : p.disponivel ? `Assinar ${p.nome}` : "Em breve"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
