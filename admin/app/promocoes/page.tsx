"use client";

import { Badge, Card, CardHeader, EmptyState } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativo } from "@/lib/format";
import type { Broadcast } from "@/lib/types";
import { AlertTriangle, Megaphone, Send, Target } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const SEGMENTOS = [
  { key: "todos", label: "Todos os ativos" },
  { key: "com_orcamento", label: "Com orçamento aberto" },
  { key: "novos", label: "Novos (30 dias)" },
  { key: "recentes", label: "Ativos recentemente" },
];

export default function PromocoesPage() {
  const [texto, setTexto] = useState("");
  const [segmento, setSegmento] = useState("todos");
  const [segmentos, setSegmentos] = useState<Record<string, number>>({});
  const [enviando, setEnviando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [lista, setLista] = useState<Broadcast[]>([]);
  const elegiveis = segmentos[segmento] ?? null;

  const carregar = useCallback(async () => {
    try {
      const [segs, bcs] = await Promise.all([api.broadcastSegmentos(), api.broadcasts()]);
      setSegmentos(segs);
      setLista(bcs);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // Poll enquanto houver campanha "enviando".
  useEffect(() => {
    if (!lista.some((b) => b.status === "enviando")) return;
    const id = setInterval(carregar, 5000);
    return () => clearInterval(id);
  }, [lista, carregar]);

  async function enviar() {
    const t = texto.trim();
    if (!t || enviando) return;
    const segLabel = SEGMENTOS.find((s) => s.key === segmento)?.label ?? segmento;
    if (
      !window.confirm(
        `Enviar para ${elegiveis ?? "?"} clientes (${segLabel}) pelo WhatsApp?\n\n` +
          "⚠️ Disparo em massa pode levar ao bloqueio do número. O envio é espaçado (anti-bloqueio).",
      )
    )
      return;
    setEnviando(true);
    setMsg(null);
    try {
      const r = await api.enviarBroadcast(t, segmento);
      setMsg(`Campanha #${r.id} iniciada para ${r.total} clientes.`);
      setTexto("");
      carregar();
    } catch {
      setMsg("Não foi possível iniciar o envio. Verifique a Evolution API / clientes elegíveis.");
    } finally {
      setEnviando(false);
    }
  }

  const tone = (s: Broadcast["status"]) =>
    s === "concluido" ? "success" : s === "erro" ? "danger" : "info";

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 px-3 py-2.5 text-xs text-warning">
        <AlertTriangle size={15} className="mt-0.5 shrink-0" />
        <span>
          Disparo em massa por WhatsApp não-oficial pode <b>bloquear o número</b>. O envio é
          espaçado automaticamente e clientes que responderem <b>“sair”</b> deixam de receber
          (opt-out). Use com moderação e conteúdo relevante.
        </span>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader
            title="Nova promoção"
            subtitle={
              elegiveis === null
                ? "selecione um segmento"
                : `${elegiveis} clientes elegíveis neste segmento`
            }
          />
          <div className="flex flex-col gap-3 p-5">
            <div>
              <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted">
                <Target size={13} /> Segmento de destinatários
              </p>
              <div className="flex flex-wrap gap-1.5">
                {SEGMENTOS.map((s) => (
                  <button
                    key={s.key}
                    onClick={() => setSegmento(s.key)}
                    className={cn(
                      "rounded-lg px-3 py-1.5 text-xs font-medium transition",
                      segmento === s.key
                        ? "bg-accent-soft text-accent-ink"
                        : "bg-surface text-muted ring-1 ring-inset ring-border hover:text-ink",
                    )}
                  >
                    {s.label}
                    <span className="ml-1.5 text-faint">{segmentos[s.key] ?? "…"}</span>
                  </button>
                ))}
              </div>
            </div>
            <textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              rows={6}
              placeholder="Escreva a mensagem da promoção… (ex: Oferta especial em captores Franklin esta semana! ⚡)"
              className="w-full resize-y rounded-lg border bg-surface p-3 text-sm text-ink outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/40"
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-faint">{texto.length} caracteres</span>
              <button
                onClick={enviar}
                disabled={enviando || !texto.trim() || !elegiveis}
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:opacity-90 disabled:opacity-50"
              >
                <Send size={15} />
                {enviando ? "Enviando…" : `Enviar para ${elegiveis ?? 0}`}
              </button>
            </div>
            {msg && <p className="text-xs text-accent-ink">{msg}</p>}
          </div>
        </Card>

        <Card>
          <CardHeader title="Campanhas" subtitle="Histórico de disparos" />
          {lista.length === 0 ? (
            <EmptyState icon={<Megaphone size={24} />} title="Nenhuma campanha ainda" />
          ) : (
            <ul className="divide-y">
              {lista.map((b) => (
                <li key={b.id} className="px-5 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] text-faint">#{b.id}</span>
                    <Badge tone={tone(b.status)} dot>
                      {b.status}
                    </Badge>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-ink">{b.texto}</p>
                  <div className="mt-1.5 flex items-center gap-3 text-[11px] text-muted">
                    <span className="tnum">
                      {b.enviados}/{b.total} enviados
                    </span>
                    {b.falhas > 0 && (
                      <span className="tnum text-danger">{b.falhas} falhas</span>
                    )}
                    <span className="ml-auto">{relativo(b.created_at)}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        b.status === "erro" ? "bg-danger" : "bg-accent",
                      )}
                      style={{
                        width: `${b.total ? Math.round(((b.enviados + b.falhas) / b.total) * 100) : 0}%`,
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
