"use client";

import { Restrito } from "@/components/restrito";
import { Carregando } from "@/components/admin-ui";
import { api } from "@/lib/api";
import type { AdminPacote, AdminPlano, AdminPlanos } from "@/lib/types";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";

const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const dataHora = (iso: string | null) => (iso ? new Date(iso).toLocaleString("pt-BR") : "—");

export default function AdminPlanosPage() {
  const [dados, setDados] = useState<AdminPlanos | null>(null);
  const [restrito, setRestrito] = useState(false);
  const [edit, setEdit] = useState<AdminPlano | null>(null);
  const [editCota, setEditCota] = useState<AdminPlano | null>(null);
  const [editPacote, setEditPacote] = useState<AdminPacote | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  async function carregar() {
    try {
      setDados(await api.adminPlanos());
    } catch {
      setRestrito(true);
    }
  }
  useEffect(() => { carregar(); }, []);

  if (restrito) return <Restrito />;
  if (!dados) return <Carregando />;

  const nomePlano = (id: string) => dados.items.find((p) => p.id === id)?.nome ?? id;

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      {!dados.stripe_configurado && (
        <p className="flex items-center gap-2 rounded-xl border bg-warning/10 px-4 py-3 text-sm text-warning">
          <AlertTriangle size={16} /> Stripe não configurado: a alteração muda só o valor exibido, sem cobrança.
        </p>
      )}
      {aviso && (
        <p className="rounded-xl border bg-surface-2 px-4 py-3 text-sm text-ink">{aviso}</p>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {dados.items.map((p) => (
          <div key={p.id} className="flex flex-col rounded-2xl border bg-surface p-5 shadow-card">
            <p className="text-sm font-semibold text-ink">{p.nome}</p>
            <p className="mt-1 text-xs text-muted">{p.descricao}</p>
            <p className="mt-4 text-3xl font-bold tabular-nums text-ink">
              {brl(p.preco)}<span className="text-sm font-normal text-muted">/mês</span>
            </p>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-faint">Mensagens/mês</dt>
              <dd className="tabular-nums text-muted">{(p.mensagens_incluidas ?? 0).toLocaleString("pt-BR")}</dd>
              <dt className="text-faint">Assinantes</dt>
              <dd className="tabular-nums text-muted">{p.assinantes}</dd>
              <dt className="text-faint">Price Stripe</dt>
              <dd className="truncate font-mono text-muted" title={p.stripe_price_id ?? ""}>{p.stripe_price_id ?? "—"}</dd>
              <dt className="text-faint">Alterado</dt>
              <dd className="truncate text-muted">{p.updated_by ? `${dataHora(p.updated_at)} · ${p.updated_by}` : "—"}</dd>
            </dl>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button onClick={() => { setAviso(null); setEdit(p); }}
                className="rounded-lg border px-3 py-2 text-sm font-medium text-ink hover:bg-surface-2">
                Alterar preço
              </button>
              <button onClick={() => { setAviso(null); setEditCota(p); }}
                className="rounded-lg border px-3 py-2 text-sm font-medium text-ink hover:bg-surface-2">
                Alterar cota
              </button>
            </div>
          </div>
        ))}
      </div>

      <section>
        <h3 className="text-sm font-semibold text-ink">Pacotes de mensagens</h3>
        <p className="mb-3 text-xs text-muted">
          Compra avulsa e pré-paga, válida até o fim do ciclo do cliente. O preço vai direto no
          checkout: alterar aqui vale para as próximas compras.
        </p>
        <div className="overflow-x-auto rounded-2xl border bg-surface shadow-card">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b text-left text-[11px] uppercase tracking-wider text-faint">
                <th className="px-4 py-3">Pacote</th>
                <th className="px-4 py-3 text-right">Mensagens</th>
                <th className="px-4 py-3 text-right">Preço</th>
                <th className="px-4 py-3 text-right">Por mensagem</th>
                <th className="px-4 py-3">Situação</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {(dados.pacotes ?? []).map((k) => (
                <tr key={k.id} className="border-b last:border-0">
                  <td className="px-4 py-3 text-ink">{k.nome}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-muted">{k.mensagens.toLocaleString("pt-BR")}</td>
                  <td className="px-4 py-3 text-right tabular-nums font-medium text-ink">{brl(k.preco)}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-muted">{brl(k.preco / k.mensagens)}</td>
                  <td className="px-4 py-3 text-muted">{k.ativo ? "À venda" : "Oculto"}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => { setAviso(null); setEditPacote(k); }}
                      className="rounded-lg border px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-2">
                      Editar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">Histórico de alterações</h3>
        {dados.historico.length === 0 ? (
          <p className="text-sm text-faint">Nenhuma alteração de preço ainda.</p>
        ) : (
          <div className="overflow-x-auto rounded-2xl border bg-surface shadow-card">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b text-left text-[11px] uppercase tracking-wider text-faint">
                  <th className="px-4 py-3">Quando</th>
                  <th className="px-4 py-3">Plano</th>
                  <th className="px-4 py-3 text-right">De</th>
                  <th className="px-4 py-3 text-right">Para</th>
                  <th className="px-4 py-3 text-center">Assinaturas migradas</th>
                  <th className="px-4 py-3">Por</th>
                </tr>
              </thead>
              <tbody>
                {dados.historico.map((h) => (
                  <tr key={h.id} className="border-b last:border-0">
                    <td className="px-4 py-3 text-muted">{dataHora(h.created_at)}</td>
                    <td className="px-4 py-3 text-ink">{nomePlano(h.plan_id)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{h.preco_anterior != null ? brl(h.preco_anterior) : "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-medium text-ink">{brl(h.preco_novo)}</td>
                    <td className="px-4 py-3 text-center tabular-nums text-muted">
                      {h.assinaturas_migradas}
                      {h.assinaturas_falhas > 0 && <span className="ml-1 text-danger">({h.assinaturas_falhas} falha{h.assinaturas_falhas > 1 ? "s" : ""})</span>}
                    </td>
                    <td className="px-4 py-3 text-muted">{h.alterado_por ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {editCota && (
        <AlterarCota
          plano={editCota}
          onClose={() => setEditCota(null)}
          onDone={(r, n) => {
            setDados(r);
            setAviso(`${editCota.nome} agora inclui ${n.toLocaleString("pt-BR")} mensagens por ciclo, para todos os assinantes.`);
          }}
        />
      )}
      {editPacote && (
        <EditarPacote
          pacote={editPacote}
          onClose={() => setEditPacote(null)}
          onDone={(r) => { setDados(r); setAviso("Pacote atualizado. Vale para as próximas compras."); }}
        />
      )}
      {edit && (
        <AlterarPreco
          plano={edit}
          stripe={dados.stripe_configurado}
          onClose={() => setEdit(null)}
          onDone={(r) => {
            setDados(r);
            const res = r.resultado;
            if (res) {
              let msg = `${nomePlano(res.plano)} agora custa ${brl(res.preco)}/mês. Novos checkouts e o site já usam o valor novo.`;
              if (res.assinaturas_migradas || res.assinaturas_falhas) {
                msg += ` ${res.assinaturas_migradas} assinatura(s) migrada(s) a partir da próxima fatura`;
                msg += res.assinaturas_falhas ? `; ${res.assinaturas_falhas} falharam (seguem no preço anterior).` : ".";
              }
              setAviso(msg);
            }
          }}
        />
      )}
    </div>
  );
}

function AlterarPreco({ plano, stripe, onClose, onDone }: {
  plano: AdminPlano; stripe: boolean; onClose: () => void; onDone: (r: AdminPlanos) => void;
}) {
  const [valor, setValor] = useState(String(plano.preco).replace(".", ","));
  const [aplicar, setAplicar] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Aceita "1.690,50" (pt-BR) e "1690.50".
  const txt = valor.trim();
  const preco = Number(txt.includes(",") ? txt.replace(/\./g, "").replace(",", ".") : txt);
  const valido = Number.isFinite(preco) && preco > 0 && Math.round(preco * 100) !== Math.round(plano.preco * 100);

  async function salvar() {
    setBusy(true); setErro(null);
    try {
      onDone(await api.adminAlterarPreco(plano.id, { preco, aplicar_existentes: aplicar }));
      onClose();
    } catch (e) {
      setErro(String(e).includes("502")
        ? "O Stripe recusou o novo preço. Nada foi alterado."
        : "Não foi possível salvar.");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={busy ? undefined : onClose} />
      <div className="relative z-10 w-full max-w-md rounded-2xl border bg-surface p-6 shadow-lift">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-ink">Preço — {plano.nome}</h2>
            <p className="text-xs text-muted">Atual: {brl(plano.preco)}/mês</p>
          </div>
          <button onClick={onClose} disabled={busy} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink"><X size={16} /></button>
        </div>
        <div className="mt-4 flex flex-col gap-3">
          <label className="text-sm">
            <span className="font-medium text-ink">Novo preço mensal (R$)</span>
            <input value={valor} onChange={(e) => setValor(e.target.value)} inputMode="decimal" autoFocus
              className="mt-1 w-full rounded-lg border bg-surface px-3 py-2.5 tabular-nums text-ink outline-none focus:ring-2 focus:ring-accent/40" />
          </label>
          {stripe && (
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={aplicar} onChange={(e) => setAplicar(e.target.checked)} className="mt-1" />
              <span className="text-muted">
                Aplicar também às <strong className="text-ink">{plano.assinantes}</strong> assinatura(s) atuais,
                a partir da próxima fatura (sem cobrança proporcional).
              </span>
            </label>
          )}
          <p className="text-xs text-faint">
            {stripe
              ? "Cria um novo preço no Stripe e arquiva o anterior. O site, a página de planos e os novos checkouts passam a usar o valor novo na hora."
              : "Atualiza o valor exibido no site e no painel."}
            {stripe && !aplicar && " Quem já assina continua pagando o valor anterior."}
          </p>
          {erro && <p className="text-sm text-danger">{erro}</p>}
          <div className="flex justify-end gap-2">
            <button onClick={onClose} disabled={busy} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted hover:text-ink">Cancelar</button>
            <button onClick={salvar} disabled={busy || !valido}
              className="inline-flex items-center gap-2 rounded-lg bg-feature px-4 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-50">
              {busy && <Loader2 size={15} className="animate-spin" />} Salvar {valido ? brl(preco) : ""}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Aceita "1.690,50" (pt-BR) e "1690.50".
const parseValor = (v: string) => {
  const t = v.trim();
  return Number(t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t);
};
const parseInteiro = (v: string) => Number(v.replace(/\D/g, "") || NaN);

function Modal({ titulo, sub, busy, onClose, children }: {
  titulo: string; sub: string; busy: boolean; onClose: () => void; children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={busy ? undefined : onClose} />
      <div className="relative z-10 w-full max-w-md rounded-2xl border bg-surface p-6 shadow-lift">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-ink">{titulo}</h2>
            <p className="text-xs text-muted">{sub}</p>
          </div>
          <button onClick={onClose} disabled={busy} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink"><X size={16} /></button>
        </div>
        <div className="mt-4 flex flex-col gap-3">{children}</div>
      </div>
    </div>
  );
}

function Acoes({ busy, valido, rotulo, erro, onClose, onSalvar }: {
  busy: boolean; valido: boolean; rotulo: string; erro: string | null; onClose: () => void; onSalvar: () => void;
}) {
  return (
    <>
      {erro && <p className="text-sm text-danger">{erro}</p>}
      <div className="flex justify-end gap-2">
        <button onClick={onClose} disabled={busy} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted hover:text-ink">Cancelar</button>
        <button onClick={onSalvar} disabled={busy || !valido}
          className="inline-flex items-center gap-2 rounded-lg bg-feature px-4 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-50">
          {busy && <Loader2 size={15} className="animate-spin" />} {rotulo}
        </button>
      </div>
    </>
  );
}

const inputCls = "mt-1 w-full rounded-lg border bg-surface px-3 py-2.5 tabular-nums text-ink outline-none focus:ring-2 focus:ring-accent/40";

function AlterarCota({ plano, onClose, onDone }: {
  plano: AdminPlano; onClose: () => void; onDone: (r: AdminPlanos, n: number) => void;
}) {
  const [valor, setValor] = useState(String(plano.mensagens_incluidas));
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const n = parseInteiro(valor);
  const valido = Number.isInteger(n) && n >= 0 && n !== plano.mensagens_incluidas;

  async function salvar() {
    setBusy(true); setErro(null);
    try {
      onDone(await api.adminAlterarCota(plano.id, n), n);
      onClose();
    } catch {
      setErro("Não foi possível salvar.");
      setBusy(false);
    }
  }

  return (
    <Modal titulo={`Cota — ${plano.nome}`} sub={`Atual: ${plano.mensagens_incluidas.toLocaleString("pt-BR")} mensagens por ciclo`} busy={busy} onClose={onClose}>
      <label className="text-sm">
        <span className="font-medium text-ink">Mensagens da IA incluídas por ciclo</span>
        <input value={valor} onChange={(e) => setValor(e.target.value)} inputMode="numeric" autoFocus className={inputCls} />
      </label>
      <p className="text-xs text-faint">
        Vale na hora para os {plano.assinantes} assinante(s) do plano, já no ciclo atual. Não muda nada no Stripe.
      </p>
      <Acoes busy={busy} valido={valido} rotulo="Salvar" erro={erro} onClose={onClose} onSalvar={salvar} />
    </Modal>
  );
}

function EditarPacote({ pacote, onClose, onDone }: {
  pacote: AdminPacote; onClose: () => void; onDone: (r: AdminPlanos) => void;
}) {
  const [mensagens, setMensagens] = useState(String(pacote.mensagens));
  const [preco, setPreco] = useState(String(pacote.preco).replace(".", ","));
  const [ativo, setAtivo] = useState(pacote.ativo);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const n = parseInteiro(mensagens);
  const v = parseValor(preco);
  const valido = Number.isInteger(n) && n > 0 && Number.isFinite(v) && v > 0
    && (n !== pacote.mensagens || Math.round(v * 100) !== Math.round(pacote.preco * 100) || ativo !== pacote.ativo);

  async function salvar() {
    setBusy(true); setErro(null);
    try {
      onDone(await api.adminAlterarPacote(pacote.id, { mensagens: n, preco: v, ativo }));
      onClose();
    } catch {
      setErro("Não foi possível salvar.");
      setBusy(false);
    }
  }

  return (
    <Modal titulo={pacote.nome} sub={`Atual: ${pacote.mensagens.toLocaleString("pt-BR")} mensagens por ${brl(pacote.preco)}`} busy={busy} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm">
          <span className="font-medium text-ink">Mensagens</span>
          <input value={mensagens} onChange={(e) => setMensagens(e.target.value)} inputMode="numeric" className={inputCls} />
        </label>
        <label className="text-sm">
          <span className="font-medium text-ink">Preço (R$)</span>
          <input value={preco} onChange={(e) => setPreco(e.target.value)} inputMode="decimal" className={inputCls} />
        </label>
      </div>
      <label className="flex items-center gap-2 text-sm text-muted">
        <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} />
        À venda no painel dos clientes
      </label>
      <p className="text-xs text-faint">
        Quem já comprou mantém o que pagou. O nome exibido acompanha a quantidade.
      </p>
      <Acoes busy={busy} valido={valido} rotulo="Salvar" erro={erro} onClose={onClose} onSalvar={salvar} />
    </Modal>
  );
}
