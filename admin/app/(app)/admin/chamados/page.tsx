"use client";

import { Restrito } from "@/components/restrito";
import { Busca, Pager } from "@/components/admin-ui";
import { api } from "@/lib/api";
import type { AdminTicketDetalhe, AdminTicketResumo } from "@/lib/types";
import { Loader2, Send, X } from "lucide-react";
import { useEffect, useState } from "react";

const LIMIT = 25;

const CAT: Record<string, string> = {
  duvida: "Dúvida", problema_tecnico: "Problema técnico", cobranca: "Cobrança",
  sugestao: "Sugestão", outro: "Outro",
};
const STATUS: Record<string, { label: string; cls: string }> = {
  aberto: { label: "Aberto", cls: "bg-accent-soft text-accent-ink" },
  em_andamento: { label: "Em andamento", cls: "bg-surface-2 text-info" },
  resolvido: { label: "Resolvido", cls: "bg-surface-2 text-success" },
  fechado: { label: "Fechado", cls: "bg-surface-2 text-muted" },
};
const PRIO: Record<string, { label: string; cls: string }> = {
  alta: { label: "Alta", cls: "bg-danger/10 text-danger" },
  normal: { label: "Normal", cls: "bg-surface-2 text-muted" },
  baixa: { label: "Baixa", cls: "bg-surface-2 text-faint" },
};

function quando(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function AdminChamados() {
  const [rows, setRows] = useState<AdminTicketResumo[] | null>(null);
  const [total, setTotal] = useState(0);
  const [restrito, setRestrito] = useState(false);
  const [fStatus, setFStatus] = useState("");
  const [fPrio, setFPrio] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [sel, setSel] = useState<number | null>(null);

  async function carregar() {
    try {
      const r = await api.adminChamados({
        status: fStatus || undefined, prioridade: fPrio || undefined,
        q: q || undefined, limit: LIMIT, offset,
      });
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
  }, [fStatus, fPrio, q, offset]);

  if (restrito) return <Restrito />;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <div className="flex flex-wrap items-center gap-2">
        <Busca q={q} onChange={(v) => { setQ(v); setOffset(0); }} placeholder="Buscar cliente ou assunto…" />
        <select value={fStatus} onChange={(e) => { setFStatus(e.target.value); setOffset(0); }}
          className="rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40">
          <option value="">Todos os status</option>
          {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select value={fPrio} onChange={(e) => { setFPrio(e.target.value); setOffset(0); }}
          className="rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40">
          <option value="">Todas as prioridades</option>
          {Object.entries(PRIO).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>

      {!rows ? (
        <div className="flex items-center gap-2 text-muted"><Loader2 size={16} className="animate-spin" /> Carregando…</div>
      ) : rows.length === 0 ? (
        <div className="rounded-2xl border bg-surface p-10 text-center text-sm text-muted shadow-card">Nenhum chamado neste filtro.</div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border bg-surface shadow-card">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b text-left text-[11px] uppercase tracking-wider text-faint">
                <th className="px-4 py-3">#</th>
                <th className="px-4 py-3">Cliente</th>
                <th className="px-4 py-3">Assunto</th>
                <th className="px-4 py-3">Prioridade</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Atualizado</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => {
                const s = STATUS[t.status] ?? STATUS.aberto;
                const p = PRIO[t.prioridade] ?? PRIO.normal;
                return (
                  <tr key={t.id} onClick={() => setSel(t.id)} className="cursor-pointer border-b last:border-0 hover:bg-surface-2">
                    <td className="px-4 py-3 text-faint">{t.id}</td>
                    <td className="px-4 py-3 font-medium text-ink">{t.tenant_nome}</td>
                    <td className="px-4 py-3 text-muted">
                      <span className="line-clamp-1">{t.assunto}</span>
                      <span className="text-[11px] text-faint">{CAT[t.categoria] ?? t.categoria}</span>
                    </td>
                    <td className="px-4 py-3"><span className={"rounded-full px-2 py-0.5 text-[11px] font-semibold " + p.cls}>{p.label}</span></td>
                    <td className="px-4 py-3"><span className={"rounded-full px-2.5 py-1 text-[11px] font-semibold " + s.cls}>{s.label}</span></td>
                    <td className="px-4 py-3 text-muted">{quando(t.updated_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {rows && rows.length > 0 && (
        <Pager offset={offset} limit={LIMIT} count={rows.length} total={total} onChange={setOffset} />
      )}

      {sel !== null && <AdminDrawer id={sel} onClose={() => setSel(null)} onChange={carregar} />}
    </div>
  );
}

function AdminDrawer({ id, onClose, onChange }: { id: number; onClose: () => void; onChange: () => void }) {
  const [t, setT] = useState<AdminTicketDetalhe | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function carregar() { setT(await api.adminChamado(id).catch(() => null)); }
  useEffect(() => { carregar(); /* eslint-disable-next-line */ }, [id]);

  async function responder() {
    if (!msg.trim()) return;
    setBusy(true);
    try { setT(await api.adminResponderChamado(id, msg)); setMsg(""); onChange(); } catch { /**/ }
    setBusy(false);
  }
  async function mudar(campo: "status" | "prioridade", valor: string) {
    setBusy(true);
    try { setT(await api.adminAtualizarChamado(id, { [campo]: valor })); onChange(); } catch { /**/ }
    setBusy(false);
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <aside className="relative z-10 flex h-full w-full max-w-md flex-col bg-surface shadow-lift animate-fade-in">
        <div className="flex items-start justify-between border-b px-5 py-4">
          <div className="min-w-0">
            <p className="text-xs text-muted">Chamado #{id} · {t?.tenant_nome ?? "…"}</p>
            <h2 className="truncate text-base font-semibold text-ink">{t?.assunto ?? "…"}</h2>
            {t?.cliente_email && <p className="truncate text-[11px] text-faint">{t.cliente_email}</p>}
          </div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink"><X size={16} /></button>
        </div>

        {t && (
          <div className="flex flex-wrap gap-2 border-b px-5 py-3">
            <label className="text-[11px] text-muted">
              Status
              <select value={t.status} onChange={(e) => mudar("status", e.target.value)} disabled={busy}
                className="ml-1 rounded-md border bg-surface px-2 py-1 text-xs text-ink outline-none">
                {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </label>
            <label className="text-[11px] text-muted">
              Prioridade
              <select value={t.prioridade} onChange={(e) => mudar("prioridade", e.target.value)} disabled={busy}
                className="ml-1 rounded-md border bg-surface px-2 py-1 text-xs text-ink outline-none">
                {Object.entries(PRIO).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </label>
          </div>
        )}

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {!t ? (
            <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin" /> Carregando…</div>
          ) : (
            t.mensagens.map((m, i) => (
              <div key={i} className={m.autor === "suporte" ? "ml-6" : "mr-6"}>
                <div className={"rounded-xl border p-3 text-sm " + (m.autor === "suporte" ? "bg-feature text-feature-fg" : "bg-surface-2 text-ink")}>
                  {m.corpo}
                </div>
                <p className={"mt-1 text-[10px] text-faint " + (m.autor === "suporte" ? "text-right" : "")}>
                  {m.autor === "suporte" ? "Suporte" : "Cliente"} · {quando(m.created_at)}
                </p>
              </div>
            ))
          )}
        </div>

        <div className="border-t p-3">
          <div className="flex items-end gap-2">
            <textarea value={msg} onChange={(e) => setMsg(e.target.value)} rows={2}
              placeholder="Responder ao cliente…"
              className="flex-1 resize-none rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40" />
            <button onClick={responder} disabled={busy || !msg.trim()}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-feature text-feature-fg transition hover:opacity-90 disabled:opacity-50">
              <Send size={16} />
            </button>
          </div>
          <p className="mt-1 text-[10px] text-faint">A resposta é enviada ao cliente por e-mail e aparece no painel dele.</p>
        </div>
      </aside>
    </div>
  );
}
