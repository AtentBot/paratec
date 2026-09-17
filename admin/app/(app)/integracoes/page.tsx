"use client";

import { Pager } from "@/components/admin-ui";
import { Badge, Card, CardHeader, EmptyState, Pill } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { ApiChave, ApiChaveCriada, ApiEscopo, ApiLog, ApiResumo, Me } from "@/lib/types";
import {
  AlertTriangle, BookOpen, Check, Copy, KeyRound, Loader2, Plus, RefreshCw,
  ScrollText, ShieldCheck, Trash2, X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Aba = "chaves" | "logs" | "docs";

function quando(iso: string | null) {
  return iso
    ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" })
    : "—";
}

function situacao(k: ApiChave): { label: string; tone: "success" | "danger" | "neutral" } {
  if (k.revoked_at) return { label: "Revogada", tone: "neutral" };
  if (k.expires_at && new Date(k.expires_at) <= new Date()) return { label: "Expirada", tone: "danger" };
  return { label: "Ativa", tone: "success" };
}

function useBaseUrl() {
  const [base, setBase] = useState("https://atentbot.com/api/v1");
  useEffect(() => setBase(`${window.location.origin}/api/v1`), []);
  return base;
}

function Copiar({ texto, className }: { texto: string; className?: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(texto).then(() => {
          setOk(true);
          setTimeout(() => setOk(false), 1500);
        }).catch(() => {});
      }}
      title="Copiar"
      className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink", className)}
    >
      {ok ? <Check size={15} className="text-success" /> : <Copy size={15} />}
    </button>
  );
}

export default function IntegracoesPage() {
  const [aba, setAba] = useState<Aba>("chaves");
  const [me, setMe] = useState<Me | null>(null);
  const [escopos, setEscopos] = useState<ApiEscopo[]>([]);
  const [chaves, setChaves] = useState<ApiChave[] | null>(null);
  const [resumo, setResumo] = useState<ApiResumo | null>(null);
  const [form, setForm] = useState<{ modo: "nova" } | { modo: "editar"; chave: ApiChave } | null>(null);
  const [criada, setCriada] = useState<ApiChaveCriada | null>(null);
  const base = useBaseUrl();

  const owner = me?.role === "owner";

  async function carregar() {
    const [c, r] = await Promise.all([
      api.apiChaves().catch(() => []),
      api.apiResumo().catch(() => null),
    ]);
    setChaves(c);
    setResumo(r);
  }

  useEffect(() => {
    api.me().then(setMe).catch(() => {});
    api.apiEscopos().then((r) => setEscopos(r.escopos)).catch(() => {});
    carregar();
  }, []);

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      {/* Resumo + URL base */}
      <div className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_2fr]">
        <Stat label="Chaves ativas" valor={resumo?.chaves_ativas} />
        <Stat label="Chamadas (24h)" valor={resumo?.chamadas_24h} />
        <Stat label="Erros (24h)" valor={resumo?.erros_24h} alerta={!!resumo?.erros_24h} />
        <Card className="p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">URL base da API</p>
          <div className="mt-1.5 flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate font-mono text-sm text-ink">{base}</code>
            <Copiar texto={base} />
          </div>
        </Card>
      </div>

      {/* Abas */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-xl border bg-surface p-1">
          {([
            ["chaves", "Chaves de API", KeyRound],
            ["logs", "Logs de uso", ScrollText],
            ["docs", "Documentação", BookOpen],
          ] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setAba(id)}
              className={cn(
                "inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition",
                aba === id ? "bg-accent-soft text-accent-ink" : "text-muted hover:text-ink",
              )}
            >
              <Icon size={15} /> {label}
            </button>
          ))}
        </div>
        {aba === "chaves" && owner && (
          <button
            onClick={() => setForm({ modo: "nova" })}
            className="inline-flex items-center gap-2 rounded-lg bg-feature px-3.5 py-2.5 text-sm font-semibold text-feature-fg transition hover:opacity-90"
          >
            <Plus size={15} /> Nova chave
          </button>
        )}
      </div>

      {aba === "chaves" && (
        <ListaChaves
          chaves={chaves}
          escopos={escopos}
          owner={owner}
          onEditar={(c) => setForm({ modo: "editar", chave: c })}
          onRotacionada={(c) => { setCriada(c); carregar(); }}
          onMudou={carregar}
        />
      )}
      {aba === "logs" && <Logs chaves={chaves ?? []} />}
      {aba === "docs" && <Documentacao base={base} escopos={escopos} />}

      {form && (
        <FormChave
          escopos={escopos}
          chave={form.modo === "editar" ? form.chave : null}
          onClose={() => setForm(null)}
          onCriada={(c) => { setForm(null); setCriada(c); carregar(); }}
          onSalva={() => { setForm(null); carregar(); }}
        />
      )}
      {criada && <ChaveCriada chave={criada} base={base} onClose={() => setCriada(null)} />}
    </div>
  );
}

function Stat({ label, valor, alerta }: { label: string; valor?: number; alerta?: boolean }) {
  return (
    <Card className="p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">{label}</p>
      <p className={cn("mt-1 text-2xl font-bold tabular-nums", alerta ? "text-danger" : "text-ink")}>
        {valor === undefined ? "—" : valor.toLocaleString("pt-BR")}
      </p>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Chaves
// ---------------------------------------------------------------------------

function ListaChaves({ chaves, escopos, owner, onEditar, onRotacionada, onMudou }: {
  chaves: ApiChave[] | null;
  escopos: ApiEscopo[];
  owner: boolean;
  onEditar: (c: ApiChave) => void;
  onRotacionada: (c: ApiChaveCriada) => void;
  onMudou: () => void;
}) {
  const [confirmar, setConfirmar] = useState<{ tipo: "revogar" | "rotacionar"; chave: ApiChave } | null>(null);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const labels = useMemo(() => Object.fromEntries(escopos.map((e) => [e.id, e])), [escopos]);

  async function executar() {
    if (!confirmar) return;
    setBusy(true); setErro(null);
    try {
      if (confirmar.tipo === "revogar") {
        await api.apiRevogarChave(confirmar.chave.id);
        onMudou();
      } else {
        onRotacionada(await api.apiRotacionarChave(confirmar.chave.id));
      }
      setConfirmar(null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha na operação.");
    } finally {
      setBusy(false);
    }
  }

  if (!chaves) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-2xl border bg-surface-2" />
        ))}
      </div>
    );
  }

  if (chaves.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<KeyRound size={28} />}
          title="Nenhuma chave de API ainda"
          hint={owner
            ? "Crie uma chave com as permissões que o seu sistema precisa para começar a integrar."
            : "Peça ao responsável da conta para criar uma chave de integração."}
        />
      </Card>
    );
  }

  return (
    <div className="space-y-2.5">
      {!owner && (
        <p className="rounded-xl border bg-surface-2 px-4 py-2.5 text-xs text-muted">
          Somente o responsável da conta pode criar, editar ou revogar chaves.
        </p>
      )}
      {chaves.map((k) => {
        const s = situacao(k);
        const ativa = s.label === "Ativa";
        return (
          <Card key={k.id} className={cn("p-4", !ativa && "opacity-70")}>
            <div className="flex flex-wrap items-start gap-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink">
                <KeyRound size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-ink">{k.nome}</p>
                  <Badge tone={s.tone} dot>{s.label}</Badge>
                  <Pill>{k.prefixo}••••••••</Pill>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {k.escopos.map((e) => (
                    <Badge key={e} tone={labels[e]?.escrita ? "warning" : "info"} className="text-[11px]">
                      {labels[e]?.label ?? e}
                    </Badge>
                  ))}
                </div>
                <p className="mt-2 text-xs text-muted">
                  Criada {quando(k.created_at)} · Último uso {quando(k.last_used_at)}
                  {k.last_used_ip ? ` (${k.last_used_ip})` : ""} · {k.chamadas_24h ?? 0} chamadas/24h ·{" "}
                  {k.rate_limit_min} req/min ·{" "}
                  {k.expires_at ? `expira ${quando(k.expires_at)}` : "sem expiração"} ·{" "}
                  {k.ips_permitidos.length ? `IPs: ${k.ips_permitidos.join(", ")}` : "qualquer IP"}
                </p>
              </div>
              {owner && ativa && (
                <div className="flex gap-1">
                  <AcaoBtn onClick={() => onEditar(k)} title="Editar permissões"><ShieldCheck size={15} /></AcaoBtn>
                  <AcaoBtn onClick={() => setConfirmar({ tipo: "rotacionar", chave: k })} title="Rotacionar (gera nova e revoga esta)"><RefreshCw size={15} /></AcaoBtn>
                  <AcaoBtn onClick={() => setConfirmar({ tipo: "revogar", chave: k })} title="Revogar" danger><Trash2 size={15} /></AcaoBtn>
                </div>
              )}
            </div>
          </Card>
        );
      })}

      {confirmar && (
        <Modal
          titulo={confirmar.tipo === "revogar" ? "Revogar chave" : "Rotacionar chave"}
          onClose={() => { setConfirmar(null); setErro(null); }}
        >
          <p className="text-sm text-muted">
            {confirmar.tipo === "revogar" ? (
              <>A chave <b className="text-ink">{confirmar.chave.nome}</b> deixará de funcionar <b className="text-ink">imediatamente</b>. Os sistemas que a usam passarão a receber erro 401. Esta ação não pode ser desfeita.</>
            ) : (
              <>Uma chave nova será gerada com as mesmas permissões e a atual (<b className="text-ink">{confirmar.chave.nome}</b>) será revogada na hora. Atualize seus sistemas com a nova chave.</>
            )}
          </p>
          {erro && <p className="mt-3 text-sm text-danger">{erro}</p>}
          <div className="mt-5 flex justify-end gap-2">
            <button onClick={() => setConfirmar(null)} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted hover:text-ink">Cancelar</button>
            <button
              onClick={executar}
              disabled={busy}
              className={cn(
                "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition hover:opacity-90 disabled:opacity-50",
                confirmar.tipo === "revogar" ? "bg-danger text-white" : "bg-feature text-feature-fg",
              )}
            >
              {busy && <Loader2 size={15} className="animate-spin" />}
              {confirmar.tipo === "revogar" ? "Revogar" : "Rotacionar"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function AcaoBtn({ children, onClick, title, danger }: {
  children: React.ReactNode; onClick: () => void; title: string; danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn(
        "grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-surface-2",
        danger ? "hover:text-danger" : "hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function Modal({ titulo, children, onClose, largo }: {
  titulo: string; children: React.ReactNode; onClose: () => void; largo?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className={cn(
        "relative z-10 max-h-[90dvh] w-full overflow-y-auto rounded-2xl border bg-surface p-6 shadow-lift",
        largo ? "max-w-2xl" : "max-w-lg",
      )}>
        <div className="flex items-start justify-between">
          <h2 className="text-base font-semibold text-ink">{titulo}</h2>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}

const inputCls = "w-full rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40";

function FormChave({ escopos, chave, onClose, onCriada, onSalva }: {
  escopos: ApiEscopo[];
  chave: ApiChave | null;
  onClose: () => void;
  onCriada: (c: ApiChaveCriada) => void;
  onSalva: () => void;
}) {
  const [nome, setNome] = useState(chave?.nome ?? "");
  const [sel, setSel] = useState<Set<string>>(new Set(chave?.escopos ?? []));
  const [ips, setIps] = useState((chave?.ips_permitidos ?? []).join("\n"));
  const [rate, setRate] = useState(chave?.rate_limit_min ?? 60);
  const [expira, setExpira] = useState<string>("365");
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const grupos = useMemo(() => {
    const g: Record<string, ApiEscopo[]> = {};
    for (const e of escopos) (g[e.grupo] ??= []).push(e);
    return Object.entries(g);
  }, [escopos]);

  function toggle(id: string) {
    const n = new Set(sel);
    if (n.has(id)) n.delete(id); else n.add(id);
    setSel(n);
  }

  async function salvar() {
    if (!nome.trim()) return setErro("Dê um nome para identificar a integração.");
    if (sel.size === 0) return setErro("Selecione ao menos uma permissão.");
    setBusy(true); setErro(null);
    const lista = ips.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
    try {
      if (chave) {
        await api.apiAtualizarChave(chave.id, { nome, escopos: [...sel], ips_permitidos: lista, rate_limit_min: rate });
        onSalva();
      } else {
        onCriada(await api.apiCriarChave({
          nome, escopos: [...sel], ips_permitidos: lista, rate_limit_min: rate,
          expira_em_dias: expira === "nunca" ? null : Number(expira),
        }));
      }
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível salvar.");
      setBusy(false);
    }
  }

  return (
    <Modal titulo={chave ? "Editar chave" : "Nova chave de API"} onClose={onClose} largo>
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted">Nome da integração</span>
          <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: ERP Sankhya, Power BI…" className={inputCls} maxLength={80} />
        </label>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-muted">Permissões (conceda só o necessário)</span>
            <div className="flex gap-2 text-xs">
              <button type="button" onClick={() => setSel(new Set(escopos.filter((e) => !e.escrita).map((e) => e.id)))} className="font-medium text-accent-ink hover:underline">Somente leitura</button>
              <button type="button" onClick={() => setSel(new Set())} className="font-medium text-muted hover:text-ink">Limpar</button>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {grupos.map(([grupo, itens]) => (
              <div key={grupo} className="rounded-xl border p-3">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">{grupo}</p>
                <div className="flex flex-col gap-2">
                  {itens.map((e) => (
                    <label key={e.id} className="flex cursor-pointer items-start gap-2.5">
                      <input type="checkbox" checked={sel.has(e.id)} onChange={() => toggle(e.id)} className="mt-0.5 h-4 w-4 accent-[var(--accent)]" />
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
                          {e.label}
                          {e.escrita && <Badge tone="warning" className="px-1.5 text-[10px]">escrita</Badge>}
                        </span>
                        <span className="block text-xs text-muted">{e.descricao}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted">Limite de requisições por minuto</span>
            <input type="number" min={1} max={1000} value={rate} onChange={(e) => setRate(Number(e.target.value))} className={inputCls} />
          </label>
          {!chave && (
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-muted">Validade</span>
              <select value={expira} onChange={(e) => setExpira(e.target.value)} className={inputCls}>
                <option value="30">30 dias</option>
                <option value="90">90 dias</option>
                <option value="180">180 dias</option>
                <option value="365">1 ano</option>
                <option value="nunca">Sem expiração</option>
              </select>
            </label>
          )}
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted">IPs autorizados (opcional — um por linha, aceita CIDR)</span>
          <textarea value={ips} onChange={(e) => setIps(e.target.value)} rows={3} placeholder={"200.150.10.20\n10.0.0.0/24"} className={cn(inputCls, "font-mono")} />
          <span className="text-[11px] text-faint">Vazio = aceita chamadas de qualquer IP. Recomendado restringir aos servidores da integração.</span>
        </label>

        {erro && <p className="text-sm text-danger">{erro}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted hover:text-ink">Cancelar</button>
          <button onClick={salvar} disabled={busy} className="inline-flex items-center gap-2 rounded-lg bg-feature px-4 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-50">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <KeyRound size={15} />}
            {chave ? "Salvar" : "Gerar chave"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function ChaveCriada({ chave, base, onClose }: { chave: ApiChaveCriada; base: string; onClose: () => void }) {
  const [confirmado, setConfirmado] = useState(false);
  return (
    <Modal titulo="Chave gerada" onClose={() => confirmado && onClose()}>
      <div className="flex items-start gap-2.5 rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
        <AlertTriangle size={17} className="mt-0.5 shrink-0" />
        <p>Copie e guarde esta chave em local seguro (cofre de segredos / variável de ambiente). <b>Ela não será exibida novamente.</b></p>
      </div>
      <div className="mt-4 flex items-center gap-2 rounded-xl border bg-surface-2 p-3">
        <code className="min-w-0 flex-1 break-all font-mono text-xs text-ink">{chave.chave}</code>
        <Copiar texto={chave.chave} />
      </div>
      <p className="mt-4 text-xs font-medium text-muted">Teste rápido:</p>
      <pre className="mt-1.5 overflow-x-auto rounded-xl bg-surface-2 p-3 font-mono text-[11px] text-ink">
{`curl ${base}/me \\
  -H "Authorization: Bearer ${chave.chave}"`}
      </pre>
      <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={confirmado} onChange={(e) => setConfirmado(e.target.checked)} className="h-4 w-4" />
        Já copiei e guardei a chave
      </label>
      <div className="mt-4 flex justify-end">
        <button onClick={onClose} disabled={!confirmado} className="rounded-lg bg-feature px-4 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-40">
          Concluir
        </button>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Logs
// ---------------------------------------------------------------------------

const LOG_LIMIT = 25;

function Logs({ chaves }: { chaves: ApiChave[] }) {
  const [rows, setRows] = useState<ApiLog[] | null>(null);
  const [total, setTotal] = useState(0);
  const [chaveId, setChaveId] = useState<number | undefined>();
  const [offset, setOffset] = useState(0);

  async function carregar() {
    setRows(null);
    const r = await api.apiLogs({ chave_id: chaveId, limit: LOG_LIMIT, offset }).catch(() => ({ items: [], total: 0 }));
    setRows(r.items);
    setTotal(r.total);
  }
  useEffect(() => { carregar(); /* eslint-disable-next-line */ }, [chaveId, offset]);

  return (
    <Card>
      <CardHeader
        title="Chamadas recebidas"
        subtitle="Auditoria das requisições feitas com as suas chaves (retenção de 90 dias)."
        action={
          <div className="flex items-center gap-2">
            <select
              value={chaveId ?? ""}
              onChange={(e) => { setChaveId(e.target.value ? Number(e.target.value) : undefined); setOffset(0); }}
              className="rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none"
            >
              <option value="">Todas as chaves</option>
              {chaves.map((k) => <option key={k.id} value={k.id}>{k.nome} ({k.prefixo}…)</option>)}
            </select>
            <AcaoBtn onClick={carregar} title="Atualizar"><RefreshCw size={15} /></AcaoBtn>
          </div>
        }
      />
      {!rows ? (
        <div className="flex items-center gap-2 p-5 text-sm text-muted"><Loader2 size={16} className="animate-spin" /> Carregando…</div>
      ) : rows.length === 0 ? (
        <EmptyState icon={<ScrollText size={28} />} title="Nenhuma chamada registrada" hint="As requisições às suas chaves aparecem aqui." />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b text-left text-[11px] uppercase tracking-wider text-faint">
                  <th className="px-4 py-3">Quando</th>
                  <th className="px-4 py-3">Chave</th>
                  <th className="px-4 py-3">Requisição</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Tempo</th>
                  <th className="px-4 py-3">IP</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((l) => (
                  <tr key={l.id} className="border-b last:border-0">
                    <td className="whitespace-nowrap px-4 py-2.5 text-muted">{quando(l.created_at)}</td>
                    <td className="px-4 py-2.5 text-ink">{l.chave ?? "—"}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-ink">
                      <span className="mr-1.5 font-semibold text-accent-ink">{l.metodo}</span>{l.rota}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge tone={l.status >= 500 ? "danger" : l.status >= 400 ? "warning" : "success"}>{l.status}</Badge>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-muted">{l.duracao_ms} ms</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-muted">{l.ip ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t px-4 py-3">
            <Pager offset={offset} limit={LOG_LIMIT} count={rows.length} total={total} onChange={setOffset} />
          </div>
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Documentação
// ---------------------------------------------------------------------------

const ENDPOINTS: { metodo: string; rota: string; escopo: string | null; descricao: string }[] = [
  { metodo: "GET", rota: "/me", escopo: null, descricao: "Identifica a chave e o tenant (teste de conexão)." },
  { metodo: "GET", rota: "/catalogo/produtos?q=&categoria=&limit=&offset=", escopo: "catalogo:ler", descricao: "Lista produtos (paginado)." },
  { metodo: "GET", rota: "/catalogo/produtos/{id|slug}", escopo: "catalogo:ler", descricao: "Detalhe do produto com variantes." },
  { metodo: "GET", rota: "/catalogo/categorias", escopo: "catalogo:ler", descricao: "Categorias do catálogo." },
  { metodo: "GET", rota: "/clientes?status=&limit=", escopo: "clientes:ler", descricao: "Lista clientes (pendente | ativo)." },
  { metodo: "GET", rota: "/clientes/{telefone}", escopo: "clientes:ler", descricao: "Cadastro de um cliente." },
  { metodo: "PUT", rota: "/clientes/{telefone}", escopo: "clientes:escrever", descricao: "Cria/atualiza cadastro (razao_social, cnpj, email, nome_contato)." },
  { metodo: "GET", rota: "/conversas?status=&q=&limit=", escopo: "conversas:ler", descricao: "Lista conversas." },
  { metodo: "GET", rota: "/conversas/{thread_id}", escopo: "conversas:ler", descricao: "Conversa com histórico de mensagens." },
  { metodo: "POST", rota: "/conversas/{thread_id}/mensagens", escopo: "mensagens:enviar", descricao: "Envia mensagem no WhatsApp ({ texto, pausar_ia })." },
  { metodo: "GET", rota: "/fila?tipo=&status=", escopo: "fila:ler", descricao: "Itens da fila humana (pedido | entrega | boleto)." },
  { metodo: "PATCH", rota: "/fila/{id}", escopo: "fila:escrever", descricao: "Atualiza status (novo | andamento | concluido) e responsável." },
  { metodo: "GET", rota: "/orcamentos?status=", escopo: "orcamentos:ler", descricao: "Pedidos de orçamento." },
  { metodo: "GET", rota: "/metricas", escopo: "metricas:ler", descricao: "Indicadores do dashboard." },
  { metodo: "GET", rota: "/relatorios/resumo?desde=AAAA-MM-DD&ate=AAAA-MM-DD", escopo: "metricas:ler", descricao: "Resumo por período." },
];

const CODIGOS: [string, string][] = [
  ["401", "Chave ausente, inválida, revogada ou expirada."],
  ["402", "Assinatura da conta inativa."],
  ["403", "Chave sem o escopo exigido, IP não autorizado ou conta suspensa."],
  ["404", "Recurso não encontrado (ou pertence a outra conta)."],
  ["422", "Parâmetros inválidos — veja o campo detail."],
  ["429", "Limite por minuto excedido — respeite o cabeçalho Retry-After."],
];

function Documentacao({ base, escopos }: { base: string; escopos: ApiEscopo[] }) {
  const labels = Object.fromEntries(escopos.map((e) => [e.id, e.label]));
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <Card>
        <CardHeader title="Endpoints" subtitle={`Todos relativos a ${base}. Respostas em JSON.`} />
        <div className="divide-y">
          {ENDPOINTS.map((e) => (
            <div key={e.metodo + e.rota} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-5 py-3">
              <span className={cn(
                "w-14 shrink-0 rounded-md px-1.5 py-0.5 text-center font-mono text-[11px] font-semibold",
                e.metodo === "GET" ? "bg-info/10 text-info" : "bg-warning/10 text-warning",
              )}>{e.metodo}</span>
              <div className="min-w-0 flex-1">
                <code className="break-all font-mono text-xs text-ink">{e.rota}</code>
                <p className="text-xs text-muted">{e.descricao}</p>
              </div>
              {e.escopo ? <span title={labels[e.escopo]}><Pill>{e.escopo}</Pill></span> : <Pill>qualquer chave</Pill>}
            </div>
          ))}
        </div>
      </Card>

      <div className="flex flex-col gap-4">
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-ink">Autenticação</h3>
          <p className="mt-1 text-xs text-muted">Envie a chave em todas as requisições, sempre por HTTPS e a partir do seu servidor (nunca no navegador ou app).</p>
          <pre className="mt-3 overflow-x-auto rounded-xl bg-surface-2 p-3 font-mono text-[11px] text-ink">
{`curl ${base}/clientes?limit=10 \\
  -H "Authorization: Bearer atb_live_..."`}
          </pre>
          <p className="mt-2 text-[11px] text-faint">Alternativa: cabeçalho <code>X-API-Key</code>.</p>
        </Card>
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-ink">Segurança</h3>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-muted">
            <li>Cada chave acessa apenas os dados da sua conta.</li>
            <li>Permissões por funcionalidade (escopos), com leitura e escrita separadas.</li>
            <li>Restrição por IP, limite por minuto e validade configuráveis.</li>
            <li>Guardamos só uma impressão digital (hash) da chave.</li>
            <li>Rotacione periodicamente e revogue na hora em caso de vazamento.</li>
          </ul>
        </Card>
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-ink">Códigos de erro</h3>
          <dl className="mt-2 space-y-1.5">
            {CODIGOS.map(([c, d]) => (
              <div key={c} className="flex gap-2 text-xs">
                <dt className="w-8 shrink-0 font-mono font-semibold text-ink">{c}</dt>
                <dd className="text-muted">{d}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-[11px] text-faint">Cabeçalhos <code>X-RateLimit-Limit</code> e <code>X-RateLimit-Remaining</code> acompanham cada resposta.</p>
        </Card>
      </div>
    </div>
  );
}
