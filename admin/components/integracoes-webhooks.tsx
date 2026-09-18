"use client";

import { Pager } from "@/components/admin-ui";
import { AcaoBtn, Copiar, Modal, inputCls, quando } from "@/components/integracoes-ui";
import { Badge, Card, CardHeader, EmptyState, Pill } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Webhook, WebhookEntrega, WebhookEvento, WebhookResultado } from "@/lib/types";
import {
  Eye, History, KeyRound, Loader2, Pause, Pencil, Play, Plus, RefreshCw, Send, Trash2,
  Webhook as WebhookIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Acao =
  | { tipo: "form"; webhook: Webhook | null }
  | { tipo: "segredo"; webhook: Webhook; segredo: string; novo?: boolean }
  | { tipo: "entregas"; webhook: Webhook }
  | { tipo: "remover"; webhook: Webhook };

function saude(w: Webhook): { label: string; tone: "success" | "warning" | "danger" | "neutral" } {
  if (!w.ativo && w.desativado_motivo) return { label: "Desativado por falhas", tone: "danger" };
  if (!w.ativo) return { label: "Pausado", tone: "neutral" };
  if (w.falhas_consecutivas > 0) return { label: `${w.falhas_consecutivas} falha(s) seguida(s)`, tone: "warning" };
  return { label: "Ativo", tone: "success" };
}

export function Webhooks({ owner }: { owner: boolean }) {
  const [eventos, setEventos] = useState<WebhookEvento[]>([]);
  const [hooks, setHooks] = useState<Webhook[] | null>(null);
  const [acao, setAcao] = useState<Acao | null>(null);
  const [teste, setTeste] = useState<Record<number, WebhookResultado | "carregando">>({});
  const [erro, setErro] = useState<string | null>(null);

  const labels = useMemo(() => Object.fromEntries(eventos.map((e) => [e.id, e.label])), [eventos]);

  async function carregar() {
    setHooks(await api.webhooks().catch(() => []));
  }
  useEffect(() => {
    api.webhookEventos().then((r) => setEventos(r.eventos)).catch(() => {});
    carregar();
  }, []);

  async function executar(fn: () => Promise<unknown>) {
    setErro(null);
    try {
      await fn();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha na operação.");
    }
  }

  async function testar(w: Webhook) {
    setTeste((t) => ({ ...t, [w.id]: "carregando" }));
    try {
      const r = await api.testarWebhook(w.id);
      setTeste((t) => ({ ...t, [w.id]: r }));
    } catch (e) {
      setTeste((t) => ({ ...t, [w.id]: { sucesso: false, status_code: null, erro: e instanceof Error ? e.message : "falhou", tentativas: 1, duracao_ms: 0 } }));
    }
    carregar();
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <div className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted">Receba eventos da plataforma no seu sistema, em tempo real.</p>
          {owner && (
            <button
              onClick={() => setAcao({ tipo: "form", webhook: null })}
              className="inline-flex items-center gap-2 rounded-lg bg-feature px-3.5 py-2.5 text-sm font-semibold text-feature-fg transition hover:opacity-90"
            >
              <Plus size={15} /> Novo webhook
            </button>
          )}
        </div>
        {erro && <p className="text-sm text-danger">{erro}</p>}

        {!hooks ? (
          <div className="h-28 animate-pulse rounded-2xl border bg-surface-2" />
        ) : hooks.length === 0 ? (
          <Card>
            <EmptyState
              icon={<WebhookIcon size={28} />}
              title="Nenhum webhook configurado"
              hint="Cadastre a URL do seu sistema e escolha os eventos que ele deve receber."
            />
          </Card>
        ) : (
          hooks.map((w) => {
            const s = saude(w);
            const t = teste[w.id];
            return (
              <Card key={w.id} className={cn("p-4", !w.ativo && "opacity-80")}>
                <div className="flex flex-wrap items-start gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink">
                    <WebhookIcon size={18} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="break-all font-mono text-sm font-medium text-ink">{w.url}</code>
                      <Badge tone={s.tone} dot>{s.label}</Badge>
                    </div>
                    {w.descricao && <p className="mt-0.5 text-xs text-muted">{w.descricao}</p>}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {w.eventos.map((e) => <Badge key={e} tone="info" className="text-[11px]">{labels[e] ?? e}</Badge>)}
                    </div>
                    <p className="mt-2 text-xs text-muted">
                      Último envio {quando(w.ultimo_envio_at)}
                      {w.ultimo_status ? ` (HTTP ${w.ultimo_status})` : ""} · {w.entregas_24h ?? 0} entregas/24h
                      {w.falhas_24h ? ` · ${w.falhas_24h} falhas/24h` : ""}
                    </p>
                    {w.desativado_motivo && <p className="mt-1 text-xs text-danger">{w.desativado_motivo}. Corrija o endpoint e reative.</p>}
                    {t && (
                      <p className={cn("mt-2 text-xs", t === "carregando" ? "text-muted" : t.sucesso ? "text-success" : "text-danger")}>
                        {t === "carregando"
                          ? "Enviando evento de teste…"
                          : t.sucesso
                            ? `Teste entregue: HTTP ${t.status_code} em ${t.duracao_ms} ms`
                            : `Teste falhou: ${t.erro ?? `HTTP ${t.status_code}`}`}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <AcaoBtn onClick={() => setAcao({ tipo: "entregas", webhook: w })} title="Entregas"><History size={15} /></AcaoBtn>
                    {owner && (
                      <>
                        <AcaoBtn onClick={() => testar(w)} title="Enviar evento de teste"><Send size={15} /></AcaoBtn>
                        <AcaoBtn onClick={() => setAcao({ tipo: "form", webhook: w })} title="Editar"><Pencil size={15} /></AcaoBtn>
                        <AcaoBtn
                          onClick={() => executar(async () => { await api.atualizarWebhook(w.id, { ativo: !w.ativo }); await carregar(); })}
                          title={w.ativo ? "Pausar" : "Reativar"}
                        >
                          {w.ativo ? <Pause size={15} /> : <Play size={15} />}
                        </AcaoBtn>
                        <AcaoBtn
                          onClick={() => executar(async () => {
                            const r = await api.revelarSegredoWebhook(w.id);
                            setAcao({ tipo: "segredo", webhook: w, segredo: r.segredo });
                          })}
                          title="Segredo de assinatura"
                        >
                          <KeyRound size={15} />
                        </AcaoBtn>
                        <AcaoBtn onClick={() => setAcao({ tipo: "remover", webhook: w })} title="Excluir" danger><Trash2 size={15} /></AcaoBtn>
                      </>
                    )}
                  </div>
                </div>
              </Card>
            );
          })
        )}
      </div>

      <GuiaWebhooks eventos={eventos} />

      {acao?.tipo === "form" && (
        <FormWebhook
          eventos={eventos}
          webhook={acao.webhook}
          onClose={() => setAcao(null)}
          onCriado={(w, segredo) => { carregar(); setAcao({ tipo: "segredo", webhook: w, segredo, novo: true }); }}
          onSalvo={() => { setAcao(null); carregar(); }}
        />
      )}
      {acao?.tipo === "segredo" && (
        <SegredoModal
          webhook={acao.webhook}
          segredo={acao.segredo}
          novo={acao.novo}
          onClose={() => setAcao(null)}
          onRotacionado={(segredo) => setAcao({ ...acao, segredo })}
        />
      )}
      {acao?.tipo === "entregas" && (
        <EntregasModal webhook={acao.webhook} owner={owner} onClose={() => { setAcao(null); carregar(); }} />
      )}
      {acao?.tipo === "remover" && (
        <Modal titulo="Excluir webhook" onClose={() => setAcao(null)}>
          <p className="text-sm text-muted">
            <code className="break-all text-ink">{acao.webhook.url}</code> deixará de receber eventos e o histórico de entregas será apagado.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button onClick={() => setAcao(null)} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted hover:text-ink">Cancelar</button>
            <button
              onClick={() => executar(async () => { await api.removerWebhook(acao.webhook.id); setAcao(null); await carregar(); })}
              className="rounded-lg bg-danger px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90"
            >
              Excluir
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function FormWebhook({ eventos, webhook, onClose, onCriado, onSalvo }: {
  eventos: WebhookEvento[];
  webhook: Webhook | null;
  onClose: () => void;
  onCriado: (w: Webhook, segredo: string) => void;
  onSalvo: () => void;
}) {
  const [url, setUrl] = useState(webhook?.url ?? "https://");
  const [descricao, setDescricao] = useState(webhook?.descricao ?? "");
  const [sel, setSel] = useState<Set<string>>(new Set(webhook?.eventos ?? []));
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const grupos = useMemo(() => {
    const g: Record<string, WebhookEvento[]> = {};
    for (const e of eventos) (g[e.grupo] ??= []).push(e);
    return Object.entries(g);
  }, [eventos]);

  function toggle(id: string) {
    const n = new Set(sel);
    if (n.has(id)) n.delete(id); else n.add(id);
    setSel(n);
  }

  async function salvar() {
    if (sel.size === 0) return setErro("Selecione ao menos um evento.");
    setBusy(true); setErro(null);
    try {
      const body = { url: url.trim(), descricao: descricao.trim(), eventos: [...sel] };
      if (webhook) {
        await api.atualizarWebhook(webhook.id, body);
        onSalvo();
      } else {
        const { segredo, ...w } = await api.criarWebhook(body);
        onCriado(w, segredo);
      }
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível salvar.");
      setBusy(false);
    }
  }

  return (
    <Modal titulo={webhook ? "Editar webhook" : "Novo webhook"} onClose={onClose} largo>
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted">URL de destino (HTTPS, endereço público)</span>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://erp.suaempresa.com.br/webhooks/atentbot" className={cn(inputCls, "font-mono")} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted">Descrição (opcional)</span>
          <input value={descricao} onChange={(e) => setDescricao(e.target.value)} placeholder="Ex.: Orçamentos para o CRM" className={inputCls} maxLength={120} />
        </label>
        <div>
          <span className="mb-2 block text-xs font-medium text-muted">Eventos</span>
          <div className="grid gap-3 sm:grid-cols-2">
            {grupos.map(([grupo, itens]) => (
              <div key={grupo} className="rounded-xl border p-3">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">{grupo}</p>
                <div className="flex flex-col gap-2">
                  {itens.map((e) => (
                    <label key={e.id} className="flex cursor-pointer items-start gap-2.5">
                      <input type="checkbox" checked={sel.has(e.id)} onChange={() => toggle(e.id)} className="mt-0.5 h-4 w-4 accent-[var(--accent)]" />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-ink">{e.label}</span>
                        <span className="block text-xs text-muted">{e.descricao}</span>
                        <code className="text-[10px] text-faint">{e.id}</code>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        {erro && <p className="text-sm text-danger">{erro}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted hover:text-ink">Cancelar</button>
          <button onClick={salvar} disabled={busy} className="inline-flex items-center gap-2 rounded-lg bg-feature px-4 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-50">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <WebhookIcon size={15} />}
            {webhook ? "Salvar" : "Criar webhook"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function SegredoModal({ webhook, segredo, novo, onClose, onRotacionado }: {
  webhook: Webhook; segredo: string; novo?: boolean; onClose: () => void; onRotacionado: (s: string) => void;
}) {
  const [confirmar, setConfirmar] = useState(false);
  const [busy, setBusy] = useState(false);

  async function rotacionar() {
    setBusy(true);
    try {
      onRotacionado((await api.rotacionarSegredoWebhook(webhook.id)).segredo);
      setConfirmar(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal titulo={novo ? "Webhook criado" : "Segredo de assinatura"} onClose={onClose}>
      <p className="text-sm text-muted">
        Use este segredo no seu sistema para validar o cabeçalho <code className="text-ink">X-AtentBot-Assinatura</code> e garantir que o evento veio do AtentBot.
      </p>
      <div className="mt-4 flex items-center gap-2 rounded-xl border bg-surface-2 p-3">
        <code className="min-w-0 flex-1 break-all font-mono text-xs text-ink">{segredo}</code>
        <Copiar texto={segredo} />
      </div>
      {confirmar ? (
        <div className="mt-4 rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          <p>O segredo atual para de valer na hora. Os eventos passam a ser assinados com o novo — atualize seu sistema logo em seguida.</p>
          <div className="mt-3 flex justify-end gap-2">
            <button onClick={() => setConfirmar(false)} className="rounded-lg border px-3 py-1.5 text-xs font-medium text-muted hover:text-ink">Cancelar</button>
            <button onClick={rotacionar} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-feature px-3 py-1.5 text-xs font-semibold text-feature-fg disabled:opacity-50">
              {busy && <Loader2 size={13} className="animate-spin" />} Gerar novo segredo
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-5 flex justify-between gap-2">
          <button onClick={() => setConfirmar(true)} className="inline-flex items-center gap-1.5 text-xs font-medium text-muted hover:text-ink">
            <RefreshCw size={13} /> Rotacionar segredo
          </button>
          <button onClick={onClose} className="rounded-lg bg-feature px-4 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90">Concluir</button>
        </div>
      )}
    </Modal>
  );
}

const ENT_LIMIT = 15;

function EntregasModal({ webhook, owner, onClose }: { webhook: Webhook; owner: boolean; onClose: () => void }) {
  const [rows, setRows] = useState<WebhookEntrega[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [aberta, setAberta] = useState<number | null>(null);
  const [reenvio, setReenvio] = useState<Record<number, string>>({});

  async function carregar() {
    const r = await api.entregasWebhook({ webhook_id: webhook.id, limit: ENT_LIMIT, offset }).catch(() => ({ items: [], total: 0 }));
    setRows(r.items);
    setTotal(r.total);
  }
  useEffect(() => { carregar(); /* eslint-disable-next-line */ }, [offset]);

  async function reenviar(e: WebhookEntrega) {
    setReenvio((r) => ({ ...r, [e.id]: "Reenviando…" }));
    try {
      const r = await api.reenviarEntrega(e.id);
      setReenvio((x) => ({ ...x, [e.id]: r.sucesso ? `Reenviado (HTTP ${r.status_code})` : `Falhou: ${r.erro}` }));
      setOffset(0);
      carregar();
    } catch (err) {
      setReenvio((x) => ({ ...x, [e.id]: err instanceof Error ? err.message : "Falhou" }));
    }
  }

  return (
    <Modal titulo="Entregas do webhook" onClose={onClose} largo>
      <p className="mb-3 break-all font-mono text-xs text-muted">{webhook.url}</p>
      {!rows ? (
        <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> Carregando…</div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<History size={28} />} title="Nenhuma entrega ainda" hint="Use o botão de teste para enviar um evento agora." />
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((e) => (
            <div key={e.id} className="rounded-xl border">
              <button onClick={() => setAberta(aberta === e.id ? null : e.id)} className="flex w-full flex-wrap items-center gap-2 px-3 py-2.5 text-left">
                <Badge tone={e.sucesso ? "success" : "danger"}>{e.status_code ?? "erro"}</Badge>
                <Pill>{e.evento}</Pill>
                <span className="flex-1 text-xs text-muted">
                  {quando(e.created_at)} · {e.tentativas} tentativa(s) · {e.duracao_ms} ms
                </span>
                <Eye size={14} className="text-faint" />
              </button>
              {aberta === e.id && (
                <div className="border-t px-3 py-3">
                  {e.erro && <p className="mb-2 text-xs text-danger">{e.erro}</p>}
                  <pre className="max-h-60 overflow-auto rounded-lg bg-surface-2 p-3 font-mono text-[11px] text-ink">
                    {JSON.stringify(e.payload, null, 2)}
                  </pre>
                  {owner && (
                    <div className="mt-2 flex items-center justify-end gap-2">
                      {reenvio[e.id] && <span className="text-xs text-muted">{reenvio[e.id]}</span>}
                      <button onClick={() => reenviar(e)} className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-2">
                        <Send size={13} /> Reenviar
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          <Pager offset={offset} limit={ENT_LIMIT} count={rows.length} total={total} onChange={setOffset} />
        </div>
      )}
    </Modal>
  );
}

const EXEMPLO_NODE = `import crypto from "node:crypto";

// Use o corpo CRU da requisição (antes de JSON.parse)
function eventoValido(req, corpoCru, segredo) {
  const ts = req.headers["x-atentbot-timestamp"];
  const recebida = req.headers["x-atentbot-assinatura"] ?? "";
  if (Math.abs(Date.now() / 1000 - Number(ts)) > 300) return false; // anti-replay
  const esperada = "sha256=" + crypto
    .createHmac("sha256", segredo)
    .update(\`\${ts}.\${corpoCru}\`)
    .digest("hex");
  return recebida.length === esperada.length &&
    crypto.timingSafeEqual(Buffer.from(recebida), Buffer.from(esperada));
}`;

const EXEMPLO_PY = `import hashlib, hmac, time

def evento_valido(headers, corpo_cru: bytes, segredo: str) -> bool:
    ts = headers["X-AtentBot-Timestamp"]
    if abs(time.time() - int(ts)) > 300:  # anti-replay
        return False
    esperada = "sha256=" + hmac.new(
        segredo.encode(), f"{ts}.".encode() + corpo_cru, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(headers["X-AtentBot-Assinatura"], esperada)`;

function GuiaWebhooks({ eventos }: { eventos: WebhookEvento[] }) {
  const [lang, setLang] = useState<"node" | "python">("node");
  const [evento, setEvento] = useState<string>("orcamento.criado");
  const ex = eventos.find((e) => e.id === evento);
  const envelope = {
    id: "evt_3f9c…",
    evento,
    criado_em: "2026-09-17T14:03:11.204Z",
    tenant_id: 1,
    dados: ex?.exemplo ?? {},
  };

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader title="Formato do evento" subtitle="POST JSON para a sua URL" />
        <div className="p-4">
          <select value={evento} onChange={(e) => setEvento(e.target.value)} className={cn(inputCls, "py-2 font-mono text-xs")}>
            {eventos.map((e) => <option key={e.id} value={e.id}>{e.id}</option>)}
          </select>
          <pre className="mt-3 max-h-72 overflow-auto rounded-xl bg-surface-2 p-3 font-mono text-[11px] text-ink">
            {JSON.stringify(envelope, null, 2)}
          </pre>
          <p className="mt-3 text-xs text-muted">
            Responda com <b className="text-ink">2xx em até 10 s</b>. Erros 5xx, 408, 429 e falhas de rede são repetidos até 3 vezes. Use o <code>id</code> para evitar processar o mesmo evento duas vezes.
          </p>
        </div>
      </Card>
      <Card>
        <CardHeader
          title="Validar a assinatura"
          action={
            <div className="flex gap-1 rounded-lg border p-0.5 text-xs">
              {(["node", "python"] as const).map((l) => (
                <button key={l} onClick={() => setLang(l)} className={cn("rounded-md px-2 py-1 font-medium", lang === l ? "bg-accent-soft text-accent-ink" : "text-muted")}>
                  {l === "node" ? "Node.js" : "Python"}
                </button>
              ))}
            </div>
          }
        />
        <div className="p-4">
          <p className="text-xs text-muted">
            Cabeçalhos: <code>X-AtentBot-Evento</code>, <code>X-AtentBot-Entrega</code>, <code>X-AtentBot-Timestamp</code> e <code>X-AtentBot-Assinatura</code>.
          </p>
          <pre className="mt-3 overflow-x-auto rounded-xl bg-surface-2 p-3 font-mono text-[11px] text-ink">
            {lang === "node" ? EXEMPLO_NODE : EXEMPLO_PY}
          </pre>
          <p className="mt-3 text-[11px] text-faint">
            Após 15 falhas seguidas o webhook é desativado automaticamente; corrija o endpoint e reative.
          </p>
        </div>
      </Card>
    </div>
  );
}
