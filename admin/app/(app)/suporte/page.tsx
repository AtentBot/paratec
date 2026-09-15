"use client";

import { api } from "@/lib/api";
import type { TicketDetalhe, TicketResumo } from "@/lib/types";
import { LifeBuoy, Loader2, Mail, Plus, Send, X } from "lucide-react";
import { useEffect, useState } from "react";

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

function quando(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function SuportePage() {
  const [tickets, setTickets] = useState<TicketResumo[]>([]);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [novo, setNovo] = useState(false);
  const [sel, setSel] = useState<number | null>(null);

  async function carregar() {
    setLoading(true);
    const t = await api.chamados().catch(() => []);
    setTickets(t);
    setLoading(false);
  }
  useEffect(() => {
    carregar();
    api.suporteEmail().then((r) => setEmail(r.email)).catch(() => {});
  }, []);

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted">
          <Mail size={15} className="text-faint" />
          Suporte:{" "}
          {email ? (
            <a href={`mailto:${email}`} className="font-medium text-accent-ink hover:underline">{email}</a>
          ) : "—"}
        </div>
        <button
          onClick={() => setNovo(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-feature px-3.5 py-2.5 text-sm font-semibold text-feature-fg transition hover:opacity-90"
        >
          <Plus size={15} /> Abrir chamado
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-2xl border bg-surface-2" />
          ))}
        </div>
      ) : tickets.length === 0 ? (
        <div className="rounded-2xl border bg-surface p-10 text-center shadow-card">
          <LifeBuoy size={28} className="mx-auto text-faint" />
          <p className="mt-3 text-sm font-medium text-ink">Nenhum chamado ainda</p>
          <p className="text-xs text-muted">Abra um chamado e acompanhe as respostas por aqui.</p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {tickets.map((t) => {
            const s = STATUS[t.status] ?? STATUS.aberto;
            return (
              <button
                key={t.id}
                onClick={() => setSel(t.id)}
                className="flex w-full items-center gap-3 rounded-2xl border bg-surface p-4 text-left shadow-card transition hover:-translate-y-0.5 hover:shadow-lift"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-faint">#{t.id}</span>
                    <p className="truncate text-sm font-semibold text-ink">{t.assunto}</p>
                  </div>
                  <p className="mt-0.5 text-xs text-muted">
                    {CAT[t.categoria] ?? t.categoria} · {t.mensagens} mensagem(ns) · {quando(t.updated_at)}
                  </p>
                </div>
                <span className={"shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold " + s.cls}>
                  {s.label}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {novo && <NovoChamado onClose={() => setNovo(false)} onDone={carregar} />}
      {sel !== null && (
        <ChamadoDrawer id={sel} onClose={() => setSel(null)} onChange={carregar} />
      )}
    </div>
  );
}

function NovoChamado({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [assunto, setAssunto] = useState("");
  const [categoria, setCategoria] = useState("duvida");
  const [prioridade, setPrioridade] = useState("normal");
  const [descricao, setDescricao] = useState("");
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar() {
    if (!assunto.trim() || !descricao.trim()) {
      setErro("Preencha o assunto e a descrição.");
      return;
    }
    setBusy(true); setErro(null);
    try {
      await api.abrirChamado({ assunto, descricao, categoria, prioridade });
      onDone();
      onClose();
    } catch {
      setErro("Não foi possível abrir o chamado.");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-2xl border bg-surface p-6 shadow-lift">
        <div className="flex items-start justify-between">
          <h2 className="text-base font-semibold text-ink">Abrir chamado</h2>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </div>
        <div className="mt-4 flex flex-col gap-3">
          <input
            value={assunto} onChange={(e) => setAssunto(e.target.value)}
            placeholder="Assunto"
            className="rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40"
          />
          <div className="flex gap-3">
            <select
              value={categoria} onChange={(e) => setCategoria(e.target.value)}
              className="flex-1 rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40"
            >
              {Object.entries(CAT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select
              value={prioridade} onChange={(e) => setPrioridade(e.target.value)}
              className="flex-1 rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40"
            >
              <option value="baixa">Prioridade baixa</option>
              <option value="normal">Prioridade normal</option>
              <option value="alta">Prioridade alta</option>
            </select>
          </div>
          <textarea
            value={descricao} onChange={(e) => setDescricao(e.target.value)}
            rows={5} placeholder="Descreva sua solicitação…"
            className="rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40"
          />
          {erro && <p className="text-sm text-danger">{erro}</p>}
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted hover:text-ink">Cancelar</button>
            <button
              onClick={enviar} disabled={busy}
              className="inline-flex items-center gap-2 rounded-lg bg-feature px-4 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-50"
            >
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} Abrir
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChamadoDrawer({ id, onClose, onChange }: { id: number; onClose: () => void; onChange: () => void }) {
  const [t, setT] = useState<TicketDetalhe | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function carregar() {
    const d = await api.chamado(id).catch(() => null);
    setT(d);
  }
  useEffect(() => { carregar(); }, [id]);

  async function responder() {
    if (!msg.trim()) return;
    setBusy(true);
    try {
      setT(await api.responderChamado(id, msg));
      setMsg("");
      onChange();
    } catch { /* ignora */ }
    setBusy(false);
  }

  async function alterarStatus(status: string) {
    setBusy(true);
    try {
      setT(await api.statusChamado(id, status));
      onChange();
    } catch { /* ignora */ }
    setBusy(false);
  }

  const s = t ? (STATUS[t.status] ?? STATUS.aberto) : null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <aside className="relative z-10 flex h-full w-full max-w-md flex-col bg-surface shadow-lift animate-fade-in">
        <div className="flex items-start justify-between border-b px-5 py-4">
          <div className="min-w-0">
            <p className="text-xs text-muted">Chamado #{id}</p>
            <h2 className="truncate text-base font-semibold text-ink">{t?.assunto ?? "…"}</h2>
            {s && <span className={"mt-1 inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold " + s.cls}>{s.label}</span>}
          </div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {!t ? (
            <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin" /> Carregando…</div>
          ) : (
            t.mensagens.map((m, i) => (
              <div key={i} className={m.autor === "cliente" ? "ml-6" : "mr-6"}>
                <div className={"rounded-xl border p-3 text-sm " + (m.autor === "cliente" ? "bg-feature text-feature-fg" : "bg-surface-2 text-ink")}>
                  {m.corpo}
                </div>
                <p className={"mt-1 text-[10px] text-faint " + (m.autor === "cliente" ? "text-right" : "")}>
                  {m.autor === "cliente" ? "Você" : "Suporte"} · {quando(m.created_at)}
                </p>
              </div>
            ))
          )}
        </div>

        {t && t.status !== "fechado" && (
          <div className="border-t p-3">
            <div className="flex items-end gap-2">
              <textarea
                value={msg} onChange={(e) => setMsg(e.target.value)}
                rows={2} placeholder="Escreva uma mensagem…"
                className="flex-1 resize-none rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40"
              />
              <button
                onClick={responder} disabled={busy || !msg.trim()}
                className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-feature text-feature-fg transition hover:opacity-90 disabled:opacity-50"
              >
                <Send size={16} />
              </button>
            </div>
            <button onClick={() => alterarStatus("fechado")} disabled={busy} className="mt-2 text-xs text-muted hover:text-danger">
              Encerrar chamado
            </button>
          </div>
        )}
        {t && t.status === "fechado" && (
          <div className="border-t p-3">
            <button onClick={() => alterarStatus("aberto")} disabled={busy} className="w-full rounded-lg border px-4 py-2 text-sm font-medium text-ink hover:bg-surface-2">
              Reabrir chamado
            </button>
          </div>
        )}
      </aside>
    </div>
  );
}
