"use client";

import { Badge, Card, EmptyState } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { especialistaLabel, hora, iniciais, relativo } from "@/lib/format";
import type { ConversaDetalhe, ConversaResumo, ConversaStatus } from "@/lib/types";
import {
  Bot,
  CheckCheck,
  CircleCheck,
  Inbox,
  Phone,
  RotateCcw,
  Search,
  Send,
  StickyNote,
  UserCheck,
  UserPlus,
  WifiOff,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

const statusMeta: Record<
  ConversaStatus,
  { label: string; tone: "accent" | "danger" | "success" }
> = {
  ia: { label: "IA", tone: "accent" },
  humano: { label: "Humano", tone: "danger" },
  resolvida: { label: "Resolvida", tone: "success" },
};

function nome(c: { cliente: string | null; telefone: string | null; thread_id: string }) {
  return c.cliente ?? c.telefone ?? c.thread_id;
}

export default function ConversasPage() {
  const [lista, setLista] = useState<ConversaResumo[]>([]);
  const [ativa, setAtiva] = useState<ConversaDetalhe | null>(null);
  const [filtro, setFiltro] = useState<"todas" | ConversaStatus>("todas");
  const [q, setQ] = useState("");
  const [offline, setOffline] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [texto, setTexto] = useState("");
  const [modoNota, setModoNota] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erroEnvio, setErroEnvio] = useState<string | null>(null);
  const [eu, setEu] = useState<{ name: string | null } | null>(null);

  // Rolagem do histórico: `pinned` indica que o atendente está no fim da lista
  // (para dar auto-scroll em mensagens novas sem "puxar" a tela enquanto ele lê
  // o histórico). `prevThread` detecta troca de conversa para rolar ao abrir.
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  const prevThreadRef = useRef<string | null>(null);

  useEffect(() => {
    api.whoami().then(setEu);
  }, []);

  // Auto-scroll: ao abrir uma conversa (troca de thread) ou ao chegar mensagem
  // nova estando no fim. Roda após o render, quando o DOM já tem as mensagens.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !ativa) return;
    const trocou = prevThreadRef.current !== ativa.thread_id;
    if (trocou || pinnedRef.current) {
      el.scrollTop = el.scrollHeight;
      pinnedRef.current = true;
    }
    prevThreadRef.current = ativa.thread_id;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ativa?.thread_id, ativa?.mensagens.length]);

  const carregarLista = useCallback(async () => {
    try {
      const data = await api.conversas({
        status: filtro === "todas" ? undefined : filtro,
        q: q.trim() || undefined,
      });
      setLista(data);
      setOffline(false);
      return data;
    } catch {
      setOffline(true);
      setLista([]);
      return [];
    } finally {
      setCarregando(false);
    }
  }, [filtro, q]);

  const abrir = useCallback(async (threadId: string) => {
    try {
      setAtiva(await api.conversa(threadId));
    } catch {
      setOffline(true);
    }
  }, []);

  // Realtime: enquanto uma conversa está aberta, revalida a conversa ativa e a
  // lista a cada 4s (o backend é REST, sem websocket) — reflete o que entra/sai
  // pelo WhatsApp sem o atendente recarregar a página.
  useEffect(() => {
    const id = ativa?.thread_id;
    if (!id) return;
    const iv = setInterval(async () => {
      try {
        const d = await api.conversa(id);
        setAtiva((cur) => (cur && cur.thread_id === id ? d : cur));
        setOffline(false);
      } catch {
        // silencioso: falha de rede pontual não deve limpar a tela
      }
      carregarLista();
    }, 4000);
    return () => clearInterval(iv);
  }, [ativa?.thread_id, carregarLista]);

  useEffect(() => {
    const t = setTimeout(() => {
      carregarLista().then((data) => {
        if (data.length && (!ativa || !data.some((c) => c.thread_id === ativa.thread_id))) {
          abrir(data[0].thread_id);
        }
      });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtro, q]);

  async function acao(fn: () => Promise<ConversaDetalhe>) {
    try {
      setAtiva(await fn());
      carregarLista();
    } catch {
      setOffline(true);
    }
  }

  async function enviar() {
    const t = texto.trim();
    if (!t || !ativa || enviando) return;
    setEnviando(true);
    setErroEnvio(null);
    pinnedRef.current = true; // ao enviar, rola para ver a própria mensagem
    try {
      if (modoNota) {
        setAtiva(await api.addNota(ativa.thread_id, t, eu?.name ?? undefined));
      } else {
        setAtiva(await api.responderConversa(ativa.thread_id, t));
      }
      setTexto("");
      carregarLista();
    } catch {
      setErroEnvio(
        modoNota
          ? "Não foi possível salvar a nota."
          : "Não foi possível enviar. Verifique se a Evolution API está configurada.",
      );
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}
      {erroEnvio && (
        <div className="rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-xs text-danger">
          {erroEnvio}
        </div>
      )}

      <div className="grid h-[calc(100dvh-200px)] grid-cols-1 gap-4 lg:grid-cols-[340px_1fr]">
        {/* Lista */}
        <Card className="flex flex-col overflow-hidden">
          <div className="border-b p-3">
            <div className="relative mb-2">
              <Search
                size={14}
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint"
              />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Buscar cliente ou telefone…"
                className="w-full rounded-lg border bg-surface py-1.5 pl-8 pr-3 text-xs text-ink outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/40"
              />
            </div>
            <div className="flex gap-1.5">
              {(["todas", "ia", "humano", "resolvida"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFiltro(f)}
                  className={cn(
                    "rounded-lg px-2.5 py-1 text-xs font-medium capitalize transition",
                    filtro === f
                      ? "bg-accent-soft text-accent-ink"
                      : "text-muted hover:bg-surface-2 hover:text-ink",
                  )}
                >
                  {f === "ia" ? "IA" : f}
                </button>
              ))}
            </div>
          </div>

          {carregando ? (
            <div className="flex-1 space-y-px overflow-hidden p-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-16 animate-pulse rounded-lg bg-surface-2" />
              ))}
            </div>
          ) : lista.length === 0 ? (
            <EmptyState
              icon={offline ? <WifiOff size={24} /> : <Inbox size={24} />}
              title={offline ? "Backend offline" : q ? "Nada encontrado" : "Nenhuma conversa"}
              hint={
                offline
                  ? "Suba o agent-service para ver os atendimentos."
                  : "As conversas aparecem aqui conforme chegam pelo WhatsApp."
              }
            />
          ) : (
            <ul className="flex-1 divide-y overflow-y-auto">
              {lista.map((c) => (
                <li key={c.thread_id}>
                  <button
                    onClick={() => abrir(c.thread_id)}
                    className={cn(
                      "flex w-full items-start gap-3 px-4 py-3 text-left transition",
                      ativa?.thread_id === c.thread_id
                        ? "bg-accent-soft/50"
                        : "hover:bg-surface-2",
                    )}
                  >
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent-ink">
                      {iniciais(c.cliente, c.telefone ?? c.thread_id)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium text-ink">{nome(c)}</p>
                        <span className="shrink-0 text-[11px] text-faint">
                          {relativo(c.updated_at)}
                        </span>
                      </div>
                      <p className="truncate text-xs text-muted">{c.last_preview ?? "—"}</p>
                      {c.responsavel && (
                        <p className="mt-0.5 flex items-center gap-1 text-[10px] text-info">
                          <UserCheck size={10} /> {c.responsavel}
                        </p>
                      )}
                    </div>
                    {c.unread > 0 && (
                      <span className="mt-1 grid h-5 min-w-5 place-items-center rounded-full bg-danger px-1.5 text-[11px] font-semibold text-white">
                        {c.unread}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Detalhe */}
        <Card className="flex flex-col overflow-hidden">
          {!ativa ? (
            <EmptyState
              icon={<Inbox size={26} />}
              title="Selecione uma conversa"
              hint="Escolha um atendimento na lista para ver o histórico."
            />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 border-b px-5 py-3">
                <span className="grid h-10 w-10 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent-ink">
                  {iniciais(ativa.cliente, ativa.telefone ?? ativa.thread_id)}
                </span>
                <div className="mr-auto min-w-0">
                  <p className="truncate text-sm font-semibold text-ink">{nome(ativa)}</p>
                  <p className="flex items-center gap-1 text-xs text-muted">
                    <Phone size={11} /> {ativa.telefone ?? ativa.thread_id}
                  </p>
                </div>
                {ativa.responsavel ? (
                  <Badge tone="info" dot>
                    <UserCheck size={11} /> {ativa.responsavel}
                  </Badge>
                ) : (
                  <button
                    onClick={() => eu?.name && acao(() => api.atribuir(ativa.thread_id, eu.name))}
                    disabled={!eu?.name}
                    className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium text-ink transition hover:bg-surface-2 disabled:opacity-50"
                  >
                    <UserPlus size={13} /> Atribuir a mim
                  </button>
                )}
                {ativa.especialista && (
                  <Badge tone="neutral">
                    {especialistaLabel[ativa.especialista] ?? ativa.especialista}
                  </Badge>
                )}
                {ativa.status === "resolvida" ? (
                  <Badge tone={statusMeta.resolvida.tone} dot>
                    {statusMeta.resolvida.label}
                  </Badge>
                ) : (
                  <button
                    type="button"
                    role="switch"
                    aria-checked={ativa.status === "ia"}
                    onClick={() =>
                      acao(() => api.setBot(ativa.thread_id, ativa.status !== "ia"))
                    }
                    title={
                      ativa.status === "ia"
                        ? "IA respondendo automaticamente. Clique para pausar e assumir o atendimento."
                        : "Atendimento humano (IA pausada). Clique para devolver o atendimento à IA."
                    }
                    className={cn(
                      "inline-flex items-center gap-2 rounded-full border px-2.5 py-1.5 text-xs font-medium transition",
                      ativa.status === "ia"
                        ? "border-accent/40 bg-accent-soft text-accent-ink"
                        : "border-warning/50 bg-warning/10 text-warning",
                    )}
                  >
                    <Bot size={14} />
                    {ativa.status === "ia" ? "IA ativa" : "IA pausada"}
                    <span
                      className={cn(
                        "relative h-4 w-7 rounded-full transition-colors",
                        ativa.status === "ia" ? "bg-accent" : "bg-warning/60",
                      )}
                    >
                      <span
                        className={cn(
                          "absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all",
                          ativa.status === "ia" ? "left-3.5" : "left-0.5",
                        )}
                      />
                    </span>
                  </button>
                )}
                {ativa.status === "resolvida" ? (
                  <button
                    onClick={() => acao(() => api.reabrirConversa(ativa.thread_id))}
                    className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium text-ink transition hover:bg-surface-2"
                  >
                    <RotateCcw size={13} /> Reabrir
                  </button>
                ) : (
                  <button
                    onClick={() => acao(() => api.resolverConversa(ativa.thread_id))}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-success/10 px-2.5 py-1.5 text-xs font-medium text-success transition hover:bg-success/20"
                  >
                    <CircleCheck size={13} /> Resolver
                  </button>
                )}
              </div>

              <div
                ref={scrollRef}
                onScroll={(e) => {
                  const el = e.currentTarget;
                  pinnedRef.current =
                    el.scrollHeight - el.scrollTop - el.clientHeight < 120;
                }}
                className="flex-1 space-y-3 overflow-y-auto bg-surface-2/40 p-5"
              >
                {ativa.mensagens.length === 0 ? (
                  <p className="py-8 text-center text-xs text-muted">
                    Sem mensagens nesta conversa.
                  </p>
                ) : (
                  ativa.mensagens.map((m, i) => {
                    if (m.role === "nota") {
                      return (
                        <div key={i} className="flex justify-center">
                          <div className="max-w-[85%] rounded-lg border border-warning/40 bg-warning/10 px-3 py-1.5 text-xs text-warning">
                            <span className="mr-1 font-semibold">📝 Nota interna:</span>
                            <span className="whitespace-pre-wrap">{m.content}</span>
                            <span className="ml-1 text-[10px] opacity-70">
                              · {hora(m.created_at)}
                            </span>
                          </div>
                        </div>
                      );
                    }
                    const meu = m.role !== "cliente";
                    return (
                      <div key={i} className={cn("flex", meu ? "justify-end" : "justify-start")}>
                        <div
                          className={cn(
                            "max-w-[75%] rounded-2xl px-3.5 py-2 text-sm shadow-card",
                            meu
                              ? "rounded-br-sm bg-accent text-accent-ink"
                              : "rounded-bl-sm bg-surface text-ink",
                          )}
                        >
                          <p className="whitespace-pre-wrap">{m.content}</p>
                          <span
                            className={cn(
                              "mt-1 flex items-center justify-end gap-1 text-[10px]",
                              meu ? "text-accent-ink/70" : "text-faint",
                            )}
                          >
                            {hora(m.created_at)}
                            {meu && <CheckCheck size={12} />}
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              <div className="flex items-center gap-2 border-t p-3">
                <button
                  onClick={() => setModoNota((v) => !v)}
                  title={modoNota ? "Modo: nota interna" : "Modo: responder cliente"}
                  className={cn(
                    "grid h-9 w-9 shrink-0 place-items-center rounded-lg border transition",
                    modoNota
                      ? "border-warning/50 bg-warning/10 text-warning"
                      : "text-muted hover:bg-surface-2 hover:text-ink",
                  )}
                >
                  <StickyNote size={15} />
                </button>
                <div className="relative flex-1">
                  <input
                    value={texto}
                    onChange={(e) => setTexto(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        enviar();
                      }
                    }}
                    placeholder={
                      modoNota
                        ? "Nota interna (não vai ao cliente)…"
                        : "Responder ao cliente pelo WhatsApp…"
                    }
                    disabled={enviando}
                    className={cn(
                      "w-full rounded-lg border bg-surface py-2 pl-3 pr-10 text-sm text-ink outline-none placeholder:text-faint focus:ring-2 disabled:opacity-60",
                      modoNota ? "focus:ring-warning/40" : "focus:ring-accent/40",
                    )}
                  />
                  <button
                    onClick={enviar}
                    disabled={enviando || !texto.trim()}
                    className={cn(
                      "absolute right-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md transition hover:opacity-90 disabled:opacity-50",
                      modoNota ? "bg-warning text-white" : "bg-accent text-accent-ink",
                    )}
                  >
                    {modoNota ? <StickyNote size={14} /> : <Send size={14} />}
                  </button>
                </div>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
