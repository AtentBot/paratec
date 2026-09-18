"use client";

import { Restrito } from "@/components/restrito";
import { Busca, Carregando, Pager } from "@/components/admin-ui";
import { api } from "@/lib/api";
import type { AdminApiChave } from "@/lib/types";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

const LIMIT = 25;

function quando(iso: string | null) {
  return iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
}

function situacao(k: AdminApiChave) {
  if (k.revoked_at) return { label: "Revogada", cls: "bg-surface-2 text-muted" };
  if (k.expires_at && new Date(k.expires_at) <= new Date()) return { label: "Expirada", cls: "bg-warning/10 text-warning" };
  return { label: "Ativa", cls: "bg-surface-2 text-success" };
}

// Visão cross-tenant das chaves de API: auditoria e revogação de emergência
// (ex.: cliente reporta vazamento). A gestão do dia a dia é do próprio cliente.
export default function AdminIntegracoes() {
  const [rows, setRows] = useState<AdminApiChave[] | null>(null);
  const [total, setTotal] = useState(0);
  const [restrito, setRestrito] = useState(false);
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [revogando, setRevogando] = useState<number | null>(null);

  async function carregar() {
    try {
      const r = await api.adminApiChaves({ q: q || undefined, limit: LIMIT, offset });
      setRows(r.items);
      setTotal(r.total);
    } catch {
      setRestrito(true);
    }
  }
  useEffect(() => {
    const t = setTimeout(carregar, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line
  }, [q, offset]);

  async function revogar(k: AdminApiChave) {
    if (!window.confirm(`Revogar a chave "${k.nome}" de ${k.tenant_nome}? As integrações do cliente param na hora.`)) return;
    setRevogando(k.id);
    try {
      await api.adminRevogarApiChave(k.id);
      await carregar();
    } finally {
      setRevogando(null);
    }
  }

  if (restrito) return <Restrito />;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <Busca q={q} onChange={(v) => { setQ(v); setOffset(0); }} placeholder="Buscar cliente, chave ou prefixo…" />
      {!rows ? (
        <Carregando />
      ) : (
        <>
          <div className="overflow-x-auto rounded-2xl border bg-surface shadow-card">
            <table className="w-full min-w-[860px] text-sm">
              <thead>
                <tr className="border-b text-left text-[11px] uppercase tracking-wider text-faint">
                  <th className="px-4 py-3">Cliente</th>
                  <th className="px-4 py-3">Chave</th>
                  <th className="px-4 py-3">Escopos</th>
                  <th className="px-4 py-3">Último uso</th>
                  <th className="px-4 py-3 text-right">24h</th>
                  <th className="px-4 py-3">Situação</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-muted">Nenhuma chave encontrada.</td></tr>
                )}
                {rows.map((k) => {
                  const s = situacao(k);
                  return (
                    <tr key={k.id} className="border-b last:border-0">
                      <td className="px-4 py-3 font-medium text-ink">{k.tenant_nome}</td>
                      <td className="px-4 py-3">
                        <p className="text-ink">{k.nome}</p>
                        <p className="font-mono text-[11px] text-faint">{k.prefixo}…</p>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted">{k.escopos.join(", ")}</td>
                      <td className="px-4 py-3 text-xs text-muted">
                        {quando(k.last_used_at)}
                        {k.last_used_ip && <span className="block font-mono text-[11px] text-faint">{k.last_used_ip}</span>}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-muted">{k.chamadas_24h ?? 0}</td>
                      <td className="px-4 py-3">
                        <span className={"rounded-full px-2.5 py-1 text-[11px] font-semibold " + s.cls}>{s.label}</span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {!k.revoked_at && (
                          <button
                            onClick={() => revogar(k)}
                            disabled={revogando === k.id}
                            className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium text-danger transition hover:bg-danger/10 disabled:opacity-50"
                          >
                            {revogando === k.id && <Loader2 size={13} className="animate-spin" />} Revogar
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pager offset={offset} limit={LIMIT} count={rows.length} total={total} onChange={setOffset} />
        </>
      )}
    </div>
  );
}
