"use client";

import { Badge, Card, EmptyState } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { iniciais, relativo } from "@/lib/format";
import type { Vendedor } from "@/lib/types";
import {
  AtSign,
  Bell,
  Loader2,
  Pencil,
  Phone,
  Plus,
  Trash2,
  UserCog,
  WifiOff,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type Form = { nome: string; telefone: string; email: string };
const VAZIO: Form = { nome: "", telefone: "", email: "" };

export default function EquipePage() {
  const [lista, setLista] = useState<Vendedor[]>([]);
  const [offline, setOffline] = useState(false);
  const [carregando, setCarregando] = useState(true);

  // Formulário (criar / editar). editId = null quando é um novo cadastro.
  const [aberto, setAberto] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<Form>(VAZIO);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      setLista(await api.vendedores());
      setOffline(false);
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

  function novo() {
    setEditId(null);
    setForm(VAZIO);
    setErro(null);
    setAberto(true);
  }

  function editar(v: Vendedor) {
    setEditId(v.id);
    setForm({ nome: v.nome, telefone: v.telefone, email: v.email ?? "" });
    setErro(null);
    setAberto(true);
  }

  function fechar() {
    setAberto(false);
    setForm(VAZIO);
    setEditId(null);
    setErro(null);
  }

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      const body = {
        nome: form.nome.trim(),
        telefone: form.telefone.trim(),
        email: form.email.trim() || null,
      };
      if (editId === null) await api.criarVendedor(body);
      else await api.atualizarVendedor(editId, body);
      fechar();
      await carregar();
    } catch (e) {
      setErro(
        e instanceof Error && /422/.test(e.message)
          ? "Confira os dados: nome e WhatsApp (DDD + número) são obrigatórios."
          : "Não foi possível salvar. Tente novamente.",
      );
    } finally {
      setSalvando(false);
    }
  }

  async function toggleAtivo(v: Vendedor) {
    setLista((l) => l.map((x) => (x.id === v.id ? { ...x, ativo: !x.ativo } : x)));
    try {
      await api.atualizarVendedor(v.id, { ativo: !v.ativo });
    } catch {
      carregar(); // reverte em caso de falha
    }
  }

  async function remover(v: Vendedor) {
    if (!confirm(`Remover ${v.nome} da equipe de vendas?`)) return;
    setLista((l) => l.filter((x) => x.id !== v.id));
    try {
      await api.removerVendedor(v.id);
    } catch {
      carregar();
    }
  }

  const ativos = lista.filter((v) => v.ativo).length;
  const podeSalvar = form.nome.trim().length > 1 && form.telefone.trim().length >= 10;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      {/* Explica o comportamento do alerta */}
      <Card className="flex items-start gap-3 p-4">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink">
          <Bell size={16} />
        </span>
        <p className="text-xs leading-relaxed text-muted">
          Quando o assistente registra um <strong className="text-ink">novo orçamento</strong>, todos os
          vendedores <strong className="text-ink">ativos</strong> recebem um alerta no WhatsApp com o
          resumo e o link do painel. Quem entrar e{" "}
          <strong className="text-ink">assumir a conversa primeiro</strong> fica responsável por ela.
        </p>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {lista.length > 0 && (
            <Badge tone="success" dot>
              {ativos} {ativos === 1 ? "vendedor ativo" : "vendedores ativos"}
            </Badge>
          )}
        </div>
        <button
          onClick={novo}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-ink transition hover:opacity-90"
        >
          <Plus size={14} /> Novo vendedor
        </button>
      </div>

      {aberto && (
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">
              {editId === null ? "Novo vendedor" : "Editar vendedor"}
            </h3>
            <button onClick={fechar} className="text-faint transition hover:text-ink">
              <X size={16} />
            </button>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Campo label="Nome">
              <input
                autoFocus
                value={form.nome}
                onChange={(e) => setForm({ ...form, nome: e.target.value })}
                placeholder="Ex.: Ana Vendas"
                className={inputCls}
              />
            </Campo>
            <Campo label="WhatsApp (DDD + número)">
              <input
                value={form.telefone}
                onChange={(e) => setForm({ ...form, telefone: e.target.value })}
                placeholder="Ex.: 5511999998888"
                inputMode="numeric"
                className={inputCls}
              />
            </Campo>
            <Campo label="E-mail (opcional)">
              <input
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="ana@paratec.com.br"
                type="email"
                className={inputCls}
              />
            </Campo>
          </div>
          {erro && <p className="mt-3 text-xs text-danger">{erro}</p>}
          <div className="mt-4 flex items-center gap-2">
            <button
              disabled={!podeSalvar || salvando}
              onClick={salvar}
              className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-xs font-medium text-accent-ink transition hover:opacity-90 disabled:opacity-40"
            >
              {salvando ? <Loader2 size={14} className="animate-spin" /> : null}
              {editId === null ? "Cadastrar" : "Salvar alterações"}
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
            <div key={i} className="h-32 animate-pulse rounded-2xl border bg-surface-2" />
          ))}
        </div>
      ) : lista.length === 0 ? (
        <Card>
          <EmptyState
            icon={offline ? <WifiOff size={28} /> : <UserCog size={28} />}
            title={offline ? "Backend offline" : "Nenhum vendedor cadastrado"}
            hint={
              offline
                ? "Suba o agent-service para gerenciar a equipe."
                : "Cadastre os vendedores para que recebam os alertas de novos orçamentos."
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {lista.map((v) => (
            <Card key={v.id} className={cn("p-4", !v.ativo && "opacity-60")}>
              <div className="flex items-start gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-sm font-semibold text-accent-ink">
                  {iniciais(v.nome, v.telefone)}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-semibold text-ink">{v.nome}</p>
                    <Badge tone={v.ativo ? "success" : "neutral"} dot>
                      {v.ativo ? "Ativo" : "Inativo"}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-[11px] text-faint">
                    cadastrado {relativo(v.created_at)}
                  </p>
                </div>
              </div>

              <dl className="mt-3 space-y-1.5 border-t pt-3 text-xs">
                <div className="flex items-center gap-2">
                  <span className="flex w-16 shrink-0 items-center gap-1.5 text-muted">
                    <Phone size={13} /> WhatsApp
                  </span>
                  <span className="min-w-0 flex-1 truncate text-ink">{v.telefone}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="flex w-16 shrink-0 items-center gap-1.5 text-muted">
                    <AtSign size={13} /> E-mail
                  </span>
                  <span className="min-w-0 flex-1 truncate text-ink">
                    {v.email ?? <span className="text-faint">—</span>}
                  </span>
                </div>
              </dl>

              <div className="mt-3 flex items-center gap-1.5 border-t pt-3">
                <button
                  onClick={() => toggleAtivo(v)}
                  className="rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
                >
                  {v.ativo ? "Desativar" : "Ativar"}
                </button>
                <button
                  onClick={() => editar(v)}
                  className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
                >
                  <Pencil size={12} /> Editar
                </button>
                <button
                  onClick={() => remover(v)}
                  className="ml-auto inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-muted transition hover:bg-danger/10 hover:text-danger"
                >
                  <Trash2 size={12} /> Remover
                </button>
              </div>
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
