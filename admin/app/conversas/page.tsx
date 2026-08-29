"use client";

import { Badge, Card, EmptyState } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { especialistaLabel, hora, iniciais, relativo } from "@/lib/format";
import type {
  ConversaDetalhe,
  ConversaResumo,
  ConversaStatus,
} from "@/lib/types";
import {
  CheckCheck,
  Headset,
  Inbox,
  Phone,
  Send,
  WifiOff,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

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
  const [offline, setOffline] = useState(false);
  const [carregando, setCarregando] = useState(true);

  const carregarLista = useCallback(async () => {
    try {
      const data = await api.conversas(filtro === "todas" ? undefined : filtro);
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
  }, [filtro]);

  const abrir = useCallback(async (threadId: string) => {
    try {
      setAtiva(await api.conversa(threadId));
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    carregarLista().then((data) => {
      if (data.length && (!ativa || !data.some((c) => c.thread_id === ativa.thread_id))) {
        abrir(data[0].thread_id);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtro]);

  async function assumir() {
    if (!ativa) return;
    try {
      setAtiva(await api.assumirConversa(ativa.thread_id));
      carregarLista();
    } catch {
      setOffline(true);
    }
  }

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      <div className="grid h-[calc(100dvh-200px)] grid-cols-1 gap-4 lg:grid-cols-[340px_1fr]">
        {/* Lista */}
        <Card className="flex flex-col overflow-hidden">
          <div className="flex gap-1.5 border-b p-3">
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

          {carregando ? (
            <div className="flex-1 space-y-px overflow-hidden p-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-16 animate-pulse rounded-lg bg-surface-2" />
              ))}
            </div>
          ) : lista.length === 0 ? (
            <EmptyState
              icon={offline ? <WifiOff size={24} /> : <Inbox size={24} />}
              title={offline ? "Backend offline" : "Nenhuma conversa"}
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
                        <p className="truncate text-sm font-medium text-ink">
                          {nome(c)}
                        </p>
                        <span className="shrink-0 text-[11px] text-faint">
                          {relativo(c.updated_at)}
                        </span>
                      </div>
                      <p className="truncate text-xs text-muted">
                        {c.last_preview ?? "—"}
                      </p>
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
              <div className="flex items-center gap-3 border-b px-5 py-3.5">
                <span className="grid h-10 w-10 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent-ink">
                  {iniciais(ativa.cliente, ativa.telefone ?? ativa.thread_id)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-ink">
                    {nome(ativa)}
                  </p>
                  <p className="flex items-center gap-1 text-xs text-muted">
                    <Phone size={11} /> {ativa.telefone ?? ativa.thread_id}
                  </p>
                </div>
                {ativa.especialista && (
                  <Badge tone="neutral">
                    {especialistaLabel[ativa.especialista] ?? ativa.especialista}
                  </Badge>
                )}
                <Badge tone={statusMeta[ativa.status].tone} dot>
                  {statusMeta[ativa.status].label}
                </Badge>
              </div>

              <div className="flex-1 space-y-3 overflow-y-auto bg-surface-2/40 p-5">
                {ativa.mensagens.length === 0 ? (
                  <p className="py-8 text-center text-xs text-muted">
                    Sem mensagens nesta conversa.
                  </p>
                ) : (
                  ativa.mensagens.map((m, i) => {
                    const meu = m.role !== "cliente";
                    return (
                      <div
                        key={i}
                        className={cn("flex", meu ? "justify-end" : "justify-start")}
                      >
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
                {ativa.status !== "humano" ? (
                  <button
                    onClick={assumir}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-feature px-3 py-2 text-xs font-medium text-feature-fg transition hover:opacity-90"
                  >
                    <Headset size={14} /> Assumir atendimento
                  </button>
                ) : (
                  <Badge tone="danger" dot>
                    Atendimento humano em andamento
                  </Badge>
                )}
                <div className="relative flex-1">
                  <input
                    placeholder="Responder (envio manual em breve)…"
                    disabled
                    className="w-full rounded-lg border bg-surface py-2 pl-3 pr-10 text-sm text-ink outline-none placeholder:text-faint disabled:opacity-60"
                  />
                  <button
                    disabled
                    className="absolute right-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md bg-accent text-accent-ink opacity-60"
                  >
                    <Send size={14} />
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
