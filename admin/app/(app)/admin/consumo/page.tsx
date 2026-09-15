"use client";

import { Restrito } from "@/components/restrito";
import { api } from "@/lib/api";
import type { AdminConsumoTenant } from "@/lib/types";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export default function AdminConsumo() {
  const [rows, setRows] = useState<AdminConsumoTenant[] | null>(null);
  const [restrito, setRestrito] = useState(false);

  useEffect(() => {
    api.adminConsumo().then(setRows).catch(() => setRestrito(true));
  }, []);

  if (restrito) return <Restrito />;
  if (!rows) return <div className="flex items-center gap-2 text-muted"><Loader2 size={16} className="animate-spin" /> Carregando…</div>;

  const totalCusto = rows.reduce((a, r) => a + Number(r.custo || 0), 0);
  const totalTokens = rows.reduce((a, r) => a + Number(r.tokens || 0), 0);

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <div className="rounded-2xl border bg-surface p-5 shadow-card">
        <p className="text-xs font-semibold uppercase tracking-wider text-faint">Consumo do mês — total</p>
        <p className="mt-1 text-2xl font-bold text-ink">{brl(totalCusto)}</p>
        <p className="text-sm text-muted">{totalTokens.toLocaleString("pt-BR")} tokens em {rows.length} clientes</p>
      </div>

      <div className="overflow-x-auto rounded-2xl border bg-surface shadow-card">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b text-left text-[11px] uppercase tracking-wider text-faint">
              <th className="px-4 py-3">Cliente</th>
              <th className="px-4 py-3 text-right">Tokens</th>
              <th className="px-4 py-3 text-right">Custo estimado</th>
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
    </div>
  );
}
