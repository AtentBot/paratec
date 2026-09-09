"use client";

import { Badge, Card, EmptyState } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativo } from "@/lib/format";
import type { Agente, Capacidade, CapacidadeInfo, WhatsappInstancia } from "@/lib/types";
import {
  Bot,
  Check,
  Info,
  Loader2,
  Pencil,
  Plus,
  Smartphone,
  Trash2,
  WifiOff,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type Form = {
  nome: string;
  descricao: string;
  instancia: string;
  persona: string;
  capacidades: Capacidade[];
};
const VAZIO: Form = { nome: "", descricao: "", instancia: "", persona: "", capacidades: [] };

export default function AgentesPage() {
  const [lista, setLista] = useState<Agente[]>([]);
  const [capacidades, setCapacidades] = useState<CapacidadeInfo[]>([]);
  const [conexoes, setConexoes] = useState<WhatsappInstancia[]>([]);
  const [offline, setOffline] = useState(false);
  const [carregando, setCarregando] = useState(true);

  const [aberto, setAberto] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<Form>(VAZIO);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const [ags, caps] = await Promise.all([api.agentes(), api.agenteCapacidades()]);
      setLista(ags);
      setCapacidades(caps);
      setOffline(false);
      // Conexões de WhatsApp: dependem da Evolution estar configurada; falha aqui
      // não deve derrubar a tela (o select mostra um aviso).
      try {
        setConexoes(await api.whatsappInstancias());
      } catch {
        setConexoes([]);
      }
    } catch {
      setOffline(true);
      setLista([]);
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const labelCap = (c: string) => capacidades.find((x) => x.chave === c)?.label ?? c;
  // Instâncias já usadas por OUTRO agente (para desabilitar no select).
  const usadas = new Map(lista.filter((a) => a.instancia).map((a) => [a.instancia!, a.id]));

  function novo() {
    setEditId(null);
    setForm(VAZIO);
    setErro(null);
    setAberto(true);
  }

  function editar(a: Agente) {
    setEditId(a.id);
    setForm({
      nome: a.nome,
      descricao: a.descricao ?? "",
      instancia: a.instancia ?? "",
      persona: a.persona ?? "",
      capacidades: a.capacidades ?? [],
    });
    setErro(null);
    setAberto(true);
  }

  function fechar() {
    setAberto(false);
    setForm(VAZIO);
    setEditId(null);
    setErro(null);
  }

  function toggleCap(c: Capacidade) {
    setForm((f) => ({
      ...f,
      capacidades: f.capacidades.includes(c)
        ? f.capacidades.filter((x) => x !== c)
        : [...f.capacidades, c],
    }));
  }

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      const body = {
        nome: form.nome.trim(),
        descricao: form.descricao.trim() || null,
        instancia: form.instancia || "", // "" desamarra no PATCH
        persona: form.persona.trim() || null,
        capacidades: form.capacidades,
      };
      if (editId === null) await api.criarAgente(body);
      else await api.atualizarAgente(editId, body);
      fechar();
      await carregar();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      setErro(
        /409/.test(msg)
          ? "Este número já está atribuído a outro agente. Escolha outra conexão."
          : /422/.test(msg)
            ? "Confira os dados: o nome do agente é obrigatório."
            : "Não foi possível salvar. Tente novamente.",
      );
    } finally {
      setSalvando(false);
    }
  }

  async function toggleAtivo(a: Agente) {
    setLista((l) => l.map((x) => (x.id === a.id ? { ...x, ativo: !x.ativo } : x)));
    try {
      await api.atualizarAgente(a.id, { ativo: !a.ativo });
    } catch {
      carregar();
    }
  }

  async function remover(a: Agente) {
    if (!confirm(`Remover o agente "${a.nome}"?`)) return;
    setLista((l) => l.filter((x) => x.id !== a.id));
    try {
      await api.removerAgente(a.id);
    } catch {
      carregar();
    }
  }

  const podeSalvar = form.nome.trim().length > 1;
  // O agente padrão (catch-all) não amarra número e não pode ser removido.
  const editandoPadrao = editId !== null && !!lista.find((a) => a.id === editId)?.is_default;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      <Card className="flex items-start gap-3 p-4">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink">
          <Bot size={16} />
        </span>
        <p className="text-xs leading-relaxed text-muted">
          Crie um agente para cada <strong className="text-ink">número de WhatsApp</strong> — por
          exemplo <strong className="text-ink">Financeiro</strong>,{" "}
          <strong className="text-ink">Comercial</strong> e{" "}
          <strong className="text-ink">Logística</strong>. Cada agente tem instruções próprias
          (persona) e só as <strong className="text-ink">capacidades</strong> que você habilitar.
          Ao chegar uma mensagem por aquele número, é esse agente que responde. Conecte novos
          números em{" "}
          <Link href="/configuracoes" className="font-medium text-accent-ink underline">
            Configurações
          </Link>
          .
        </p>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {lista.length > 0 && (
            <Badge tone="accent" dot>
              {lista.length} {lista.length === 1 ? "agente" : "agentes"}
            </Badge>
          )}
        </div>
        <button
          onClick={novo}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-ink transition hover:opacity-90"
        >
          <Plus size={14} /> Novo agente
        </button>
      </div>

      {aberto && (
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">
              {editId === null ? "Novo agente" : "Editar agente"}
            </h3>
            <button onClick={fechar} className="text-faint transition hover:text-ink">
              <X size={16} />
            </button>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Campo label="Nome do agente">
              <input
                autoFocus
                value={form.nome}
                onChange={(e) => setForm({ ...form, nome: e.target.value })}
                placeholder="Ex.: Financeiro"
                disabled={editandoPadrao}
                className={cn(inputCls, editandoPadrao && "opacity-60")}
              />
            </Campo>
            {editandoPadrao ? (
              <Campo label="Conexão de WhatsApp">
                <div className="flex h-[38px] items-center rounded-lg border bg-surface-2 px-3 text-xs text-muted">
                  Atende todos os números sem agente próprio (catch-all).
                </div>
              </Campo>
            ) : (
              <Campo label="Conexão de WhatsApp (número)">
                <select
                  value={form.instancia}
                  onChange={(e) => setForm({ ...form, instancia: e.target.value })}
                  className={inputCls}
                >
                  <option value="">— sem número amarrado —</option>
                  {conexoes.map((c) => {
                    const dono = usadas.get(c.nome);
                    const emUso = dono != null && dono !== editId;
                    return (
                      <option key={c.nome} value={c.nome} disabled={emUso}>
                        {c.nome}
                        {c.numero ? ` (+${c.numero})` : ""}
                        {emUso ? " — em uso" : ""}
                      </option>
                    );
                  })}
                </select>
              </Campo>
            )}
          </div>

          <div className="mt-3">
            <Campo label="Descrição (opcional)">
              <input
                value={form.descricao}
                onChange={(e) => setForm({ ...form, descricao: e.target.value })}
                placeholder="Para que serve este agente"
                className={inputCls}
              />
            </Campo>
          </div>

          <div className="mt-3">
            <span className="text-[11px] font-medium text-muted">Capacidades</span>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {capacidades.map((c) => {
                const on = form.capacidades.includes(c.chave);
                return (
                  <button
                    key={c.chave}
                    type="button"
                    onClick={() => toggleCap(c.chave)}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition",
                      on
                        ? "border-accent bg-accent-soft text-accent-ink"
                        : "text-muted hover:bg-surface-2 hover:text-ink",
                    )}
                  >
                    {on && <Check size={12} />} {c.label}
                  </button>
                );
              })}
            </div>
            <p className="mt-1.5 text-[11px] text-faint">
              O cadastro do cliente é sempre solicitado antes do atendimento.
            </p>
          </div>

          <div className="mt-3">
            <Campo label="Persona / instruções (opcional)">
              <textarea
                value={form.persona}
                onChange={(e) => setForm({ ...form, persona: e.target.value })}
                placeholder={
                  editandoPadrao
                    ? "Instruções gerais do atendimento. Deixe em branco para usar o prompt base padrão."
                    : "Ex.: Você é o atendimento financeiro. Foque em 2ª via de boleto e pagamentos; para dúvidas comerciais, oriente a procurar o número comercial."
                }
                rows={editandoPadrao ? 5 : 3}
                className={cn(inputCls, "resize-y")}
              />
            </Campo>
            {editandoPadrao && (
              <p className="mt-1.5 text-[11px] text-faint">
                Este é o atendimento aplicado a qualquer número sem agente próprio. Ajuste o texto e
                as capacidades para evoluir o comportamento padrão.
              </p>
            )}
          </div>

          {erro && <p className="mt-3 text-xs text-danger">{erro}</p>}
          <div className="mt-4 flex items-center gap-2">
            <button
              disabled={!podeSalvar || salvando}
              onClick={salvar}
              className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-xs font-medium text-accent-ink transition hover:opacity-90 disabled:opacity-40"
            >
              {salvando ? <Loader2 size={14} className="animate-spin" /> : null}
              {editId === null ? "Criar agente" : "Salvar alterações"}
            </button>
            <button
              onClick={fechar}
              className="rounded-lg border px-3.5 py-2 text-xs font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
            >
              Cancelar
            </button>
          </div>
        </Card>
      )}

      {carregando ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-44 animate-pulse rounded-2xl border bg-surface-2" />
          ))}
        </div>
      ) : lista.length === 0 ? (
        <Card>
          <EmptyState
            icon={offline ? <WifiOff size={28} /> : <Bot size={28} />}
            title={offline ? "Backend offline" : "Nenhum agente criado"}
            hint={
              offline
                ? "Suba o agent-service para gerenciar os agentes."
                : "Crie um agente por número de WhatsApp (ex.: Financeiro, Comercial, Logística)."
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {lista.map((a) => (
            <Card key={a.id} className={cn("flex flex-col p-4", !a.ativo && "opacity-60")}>
              <div className="flex items-start gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink">
                  <Bot size={18} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-semibold text-ink">{a.nome}</p>
                    {a.is_default ? (
                      <Badge tone="accent" dot>
                        Padrão
                      </Badge>
                    ) : (
                      <Badge tone={a.ativo ? "success" : "neutral"} dot>
                        {a.ativo ? "Ativo" : "Inativo"}
                      </Badge>
                    )}
                  </div>
                  {a.descricao && (
                    <p className="mt-0.5 truncate text-[11px] text-muted">{a.descricao}</p>
                  )}
                </div>
              </div>

              <div className="mt-3 flex items-center gap-1.5 border-t pt-3 text-xs">
                <Smartphone size={13} className="shrink-0 text-faint" />
                {a.is_default ? (
                  <span className="min-w-0 flex-1 truncate text-muted">
                    Todos os números sem agente próprio
                  </span>
                ) : a.instancia ? (
                  <span className="min-w-0 flex-1 truncate text-ink">{a.instancia}</span>
                ) : (
                  <span className="flex items-center gap-1 text-warning">
                    <Info size={12} /> sem número amarrado
                  </span>
                )}
              </div>

              {a.capacidades.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {a.capacidades.map((c) => (
                    <span
                      key={c}
                      className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium text-muted ring-1 ring-inset ring-border"
                    >
                      {labelCap(c)}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="mt-3 text-[11px] text-faint">Sem capacidades — só conversa/cadastro.</p>
              )}

              <div className="mt-auto flex items-center gap-1.5 border-t pt-3">
                {!a.is_default && (
                  <button
                    onClick={() => toggleAtivo(a)}
                    className="rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
                  >
                    {a.ativo ? "Desativar" : "Ativar"}
                  </button>
                )}
                <button
                  onClick={() => editar(a)}
                  className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
                >
                  <Pencil size={12} /> {a.is_default ? "Editar prompt" : "Editar"}
                </button>
                {!a.is_default && (
                  <button
                    onClick={() => remover(a)}
                    className="ml-auto inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-muted transition hover:bg-danger/10 hover:text-danger"
                  >
                    <Trash2 size={12} /> Remover
                  </button>
                )}
              </div>
              <p className="mt-2 text-[10px] text-faint">atualizado {relativo(a.updated_at)}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

const inputCls =
  "w-full rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none transition placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/20";

function Campo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] font-medium text-muted">{label}</span>
      {children}
    </label>
  );
}
