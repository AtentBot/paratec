"use client";

import { api } from "@/lib/api";
import type { AssinaturaStatus, Plano, Uso } from "@/lib/types";
import { CheckCircle2, AlertTriangle, Loader2, Gauge, X } from "lucide-react";
import { useEffect, useState } from "react";

const brl = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

const STATUS_LABEL: Record<string, string> = {
  active: "Ativa",
  trialing: "Em teste",
  past_due: "Pagamento pendente",
  canceled: "Cancelada",
  unpaid: "Não paga",
  incomplete: "Incompleta",
  sem_assinatura: "Sem assinatura",
};

function fmtData(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
}

export default function AssinaturaPage() {
  const [sub, setSub] = useState<AssinaturaStatus | null>(null);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [uso, setUso] = useState<Uso | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);

  async function carregar() {
    const [s, p, u] = await Promise.all([
      api.assinaturaStatus().catch(() => null),
      api.planos().catch(() => []),
      api.uso().catch(() => null),
    ]);
    setSub(s);
    setPlanos(p || []);
    setUso(u);
  }

  useEffect(() => {
    carregar();
  }, []);

  async function assinar(id: string) {
    setOcupado(true); setErro(null);
    try {
      const { url } = await api.checkout(id);
      window.location.href = url;
    } catch {
      setErro("Não foi possível iniciar o checkout. Verifique se o billing está configurado.");
      setOcupado(false);
    }
  }

  async function confirmarCancelamento(
    respostas: Record<string, string>, comentario: string,
  ) {
    setOcupado(true); setErro(null);
    try {
      setSub(await api.cancelarAssinatura({ respostas, comentario: comentario || undefined }));
      setCancelOpen(false);
    } catch {
      setErro("Não foi possível cancelar agora.");
    }
    setOcupado(false);
  }

  async function reativar() {
    setOcupado(true); setErro(null);
    try {
      setSub(await api.reativarAssinatura());
    } catch {
      setErro("Não foi possível reativar agora.");
    }
    setOcupado(false);
  }

  if (!sub) {
    return (
      <div className="flex items-center gap-2 text-muted">
        <Loader2 size={16} className="animate-spin" /> Carregando…
      </div>
    );
  }

  const ativa = sub.ativa;
  const temPlano = sub.tem_assinatura && sub.status !== "canceled" && sub.status !== "sem_assinatura";

  return (
    <div className="flex flex-col gap-6">
      {/* Cartão de status */}
      <section className="rounded-2xl border bg-surface p-6 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-faint">Assinatura</p>
            <div className="mt-1 flex items-center gap-2">
              {ativa ? (
                <CheckCircle2 size={20} className="text-success" />
              ) : (
                <AlertTriangle size={20} className="text-warning" />
              )}
              <h2 className="text-xl font-semibold text-ink">
                {STATUS_LABEL[sub.status] || sub.status}
              </h2>
            </div>
            {sub.plan && (
              <p className="mt-1 text-sm text-muted">
                Plano <span className="font-medium capitalize text-ink">{sub.plan}</span>
              </p>
            )}
            {temPlano && (
              <p className="mt-1 text-sm text-muted">
                {sub.cancel_at_period_end ? "Acesso até" : "Renova em"}: {fmtData(sub.current_period_end)}
              </p>
            )}
          </div>

          {temPlano && (
            <div className="flex gap-2">
              {sub.cancel_at_period_end ? (
                <button
                  onClick={reativar} disabled={ocupado}
                  className="rounded-xl bg-feature px-4 py-2.5 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-60"
                >
                  Reativar assinatura
                </button>
              ) : (
                <button
                  onClick={() => setCancelOpen(true)} disabled={ocupado}
                  className="rounded-xl border px-4 py-2.5 text-sm font-semibold text-danger transition hover:bg-danger/10 disabled:opacity-60"
                >
                  Cancelar assinatura
                </button>
              )}
            </div>
          )}
        </div>

        {sub.cancel_at_period_end && (
          <p className="mt-4 rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
            Cancelamento agendado — sua assinatura não será renovada. Você mantém o acesso até {fmtData(sub.current_period_end)}.
          </p>
        )}
        {erro && <p className="mt-4 text-sm text-danger">{erro}</p>}
      </section>

      {/* Consumo pay-per-use do mês (medição — ainda não cobrado automaticamente) */}
      {uso && (
        <section className="rounded-2xl border bg-surface p-6 shadow-card">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-faint">
                <Gauge size={13} /> Consumo do mês ({uso.mes})
              </p>
              <p className="mt-1 text-2xl font-bold text-ink">{brl(uso.custo)}</p>
              <p className="text-sm text-muted">
                {uso.tokens.toLocaleString("pt-BR")} tokens · {uso.eventos} eventos
              </p>
            </div>
            <span className="rounded-full bg-surface-2 px-2.5 py-1 text-[11px] font-medium text-muted">
              {uso.cobranca_automatica ? "Cobrado na fatura" : "Estimativa (não cobrado ainda)"}
            </span>
          </div>

          {uso.por_tipo.length > 0 && (
            <div className="mt-4 divide-y border-t">
              {uso.por_tipo.map((t) => (
                <div key={t.tipo} className="flex items-center justify-between py-2.5 text-sm">
                  <span className="text-ink">{t.label}</span>
                  <span className="flex items-center gap-4 text-muted">
                    <span className="tabular-nums">{t.tokens.toLocaleString("pt-BR")} tk</span>
                    <span className="w-20 text-right font-medium text-ink tabular-nums">{brl(t.custo)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}

          <p className="mt-3 text-xs text-faint">
            Tarifas: indexação {brl(uso.precos.embedding_por_1k)}/1k tokens · conversas{" "}
            {brl(uso.precos.chat_por_1k)}/1k tokens. Quanto mais documentos e mensagens,
            maior o consumo.
          </p>
        </section>
      )}

      {/* Escolha de plano (quando sem assinatura ativa) */}
      {!temPlano && (
        <section>
          <h3 className="mb-3 text-sm font-semibold text-ink">Escolha um plano</h3>
          <div className="grid gap-4 md:grid-cols-3">
            {planos.map((p) => {
              const destaque = p.id === "profissional";
              return (
                <div key={p.id} className={"flex flex-col rounded-2xl border p-5 shadow-card " + (destaque ? "bg-feature text-feature-fg" : "bg-surface")}>
                  <h4 className={"text-base font-semibold " + (destaque ? "text-feature-fg" : "text-ink")}>{p.nome}</h4>
                  <p className={"mt-1 text-xs " + (destaque ? "text-white/70" : "text-muted")}>{p.descricao}</p>
                  <div className="mt-4 text-2xl font-bold">R$ {p.preco.toLocaleString("pt-BR")}<span className={"text-sm font-normal " + (destaque ? "text-white/70" : "text-muted")}>/mês</span></div>
                  <button
                    onClick={() => assinar(p.id)} disabled={ocupado || !p.disponivel}
                    className={"mt-4 rounded-xl px-4 py-2 text-sm font-semibold transition disabled:opacity-60 " + (destaque ? "bg-accent text-[#3a2500] hover:opacity-90" : "bg-feature text-feature-fg hover:opacity-90")}
                  >
                    {p.disponivel ? "Assinar" : "Em breve"}
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {cancelOpen && (
        <CancelamentoModal
          ocupado={ocupado}
          fim={sub.current_period_end}
          onClose={() => setCancelOpen(false)}
          onConfirm={confirmarCancelamento}
        />
      )}
    </div>
  );
}

const PERGUNTAS: { chave: string; label: string; opcoes: string[] }[] = [
  {
    chave: "motivo_principal",
    label: "Qual o principal motivo do cancelamento?",
    opcoes: ["Preço/custo alto", "Usei pouco", "Faltou um recurso", "Problemas técnicos", "Fui para outra solução", "Outro"],
  },
  {
    chave: "tempo_uso",
    label: "Há quanto tempo você usa o AtentBot?",
    opcoes: ["Menos de 1 mês", "1 a 3 meses", "3 a 6 meses", "Mais de 6 meses"],
  },
  {
    chave: "o_que_faltou",
    label: "O que mais faltou para você?",
    opcoes: ["Mais integrações", "Respostas melhores da IA", "Suporte", "Recursos de catálogo", "Nada específico"],
  },
  {
    chave: "recomendaria",
    label: "Você recomendaria o AtentBot a alguém?",
    opcoes: ["Sim", "Talvez", "Não"],
  },
  {
    chave: "voltaria",
    label: "Consideraria voltar no futuro?",
    opcoes: ["Sim", "Talvez", "Não"],
  },
];

function CancelamentoModal({
  ocupado, fim, onClose, onConfirm,
}: {
  ocupado: boolean;
  fim: string | null;
  onClose: () => void;
  onConfirm: (respostas: Record<string, string>, comentario: string) => void;
}) {
  const [respostas, setRespostas] = useState<Record<string, string>>({});
  const [comentario, setComentario] = useState("");
  const completo = PERGUNTAS.every((p) => respostas[p.chave]);
  const fimTxt = fim
    ? new Date(fim).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" })
    : "o fim do período";

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl border bg-surface shadow-lift">
        <div className="flex items-start justify-between border-b px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-ink">Cancelar assinatura</h2>
            <p className="mt-0.5 text-xs text-muted">
              Você mantém o acesso até {fimTxt}. Antes de ir, nos ajude a melhorar.
            </p>
          </div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          {PERGUNTAS.map((p) => (
            <div key={p.chave}>
              <p className="mb-2 text-sm font-medium text-ink">{p.label}</p>
              <div className="flex flex-wrap gap-1.5">
                {p.opcoes.map((op) => (
                  <button
                    key={op}
                    onClick={() => setRespostas((r) => ({ ...r, [p.chave]: op }))}
                    className={
                      "rounded-full px-3 py-1.5 text-xs font-medium transition " +
                      (respostas[p.chave] === op
                        ? "bg-feature text-feature-fg"
                        : "bg-surface text-muted ring-1 ring-inset ring-border hover:text-ink")
                    }
                  >
                    {op}
                  </button>
                ))}
              </div>
            </div>
          ))}

          <div>
            <p className="mb-2 text-sm font-medium text-ink">Deixe seu relato (opcional)</p>
            <textarea
              value={comentario}
              onChange={(e) => setComentario(e.target.value)}
              rows={4}
              placeholder="Conte o que aconteceu ou como podemos melhorar…"
              className="w-full rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40"
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-2 border-t px-6 py-4">
          <button onClick={onClose} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted transition hover:text-ink">
            Manter assinatura
          </button>
          <button
            onClick={() => onConfirm(respostas, comentario)}
            disabled={!completo || ocupado}
            className="inline-flex items-center gap-2 rounded-lg border border-danger/40 px-4 py-2 text-sm font-semibold text-danger transition hover:bg-danger/10 disabled:opacity-50"
          >
            {ocupado ? <Loader2 size={15} className="animate-spin" /> : null}
            Confirmar cancelamento
          </button>
        </div>
      </div>
    </div>
  );
}
