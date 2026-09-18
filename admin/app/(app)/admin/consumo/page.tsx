"use client";

import { Restrito } from "@/components/restrito";
import { Busca, Carregando, Pager } from "@/components/admin-ui";
import { api } from "@/lib/api";
import type { AdminConsumoTenant } from "@/lib/types";
import { useEffect, useState } from "react";

const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const LIMIT = 25;

export default function AdminConsumo() {
  const [rows, setRows] = useState<AdminConsumoTenant[] | null>(null);
  const [totais, setTotais] = useState<{ tenants: number; tokens: number; custo: number } | null>(null);
  const [restrito, setRestrito] = useState(false);
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => {
      api.adminConsumo({ q: q || undefined, limit: LIMIT, offset })
        .then((r) => { setRows(r.items); setTotais(r.totais); })
        .catch(() => setRestrito(true));
    }, 250);
    return () => clearTimeout(t);
  }, [q, offset]);

  if (restrito) return <Restrito />;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {totais && (
        <div className="rounded-2xl border bg-surface p-5 shadow-card">
          <p className="text-xs font-semibold uppercase tracking-wider text-faint">Custo de IA do mês — total{q ? " (filtrado)" : ""}</p>
          <p className="mt-1 text-2xl font-bold text-ink">{brl(Number(totais.custo))}</p>
          <p className="text-sm text-muted">{Number(totais.tokens).toLocaleString("pt-BR")} tokens em {totais.tenants} clientes</p>
        </div>
      )}

      <Busca q={q} onChange={(v) => { setQ(v); setOffset(0); }} placeholder="Buscar cliente…" />

      {!rows ? (
        <Carregando />
      ) : (
        <>
          <div className="overflow-x-auto rounded-2xl border bg-surface shadow-card">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b text-left text-[11px] uppercase tracking-wider text-faint">
                  <th className="px-4 py-3">Cliente</th>
                  <th className="px-4 py-3 text-right">Tokens</th>
                  <th className="px-4 py-3 text-right">Custo de IA (estimado)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b last:border-0">
                    <td className="px-4 py-3 font-medium text-ink">{r.nome}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{Number(r.tokens).toLocaleString("pt-BR")}</td>
                    <td className="px-4 py-3 text-right font-medium tabular-nums text-ink">{brl(Number(r.custo))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager offset={offset} limit={LIMIT} count={rows.length} total={totais?.tenants ?? 0} onChange={setOffset} />
        </>
      )}
    </div>
  );
}
