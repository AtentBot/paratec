"use client";

import { api } from "@/lib/api";
import { precoPlano } from "@/lib/format";
import type { AssinaturaStatus, Plano, Uso } from "@/lib/types";
import { CheckCircle2, AlertTriangle, Loader2, MessageSquare, X } from "lucide-react";
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
  const [retornoPacote, setRetornoPacote] = useState<string | null>(null);

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
    // Volta do checkout de pacote (?pacote=ok|cancelado): avisa e limpa a URL.
    const r = new URLSearchParams(window.location.search).get("pacote");
    if (r) {
      setRetornoPacote(r);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  async function comprarPacote(id: string) {
    setOcupado(true); setErro(null);
    try {
      const { url } = await api.comprarPacote(id);
      window.location.href = url;
    } catch (e) {
      setErro(String(e).includes("403")
        ? "Só o responsável da conta pode comprar pacotes."
        : "Não foi possível abrir o pagamento do pacote agora.");
      setOcupado(false);
    }
  }

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

      {retornoPacote === "ok" && (
        <p className="rounded-xl border bg-success/10 px-4 py-3 text-sm text-ink">
          Pagamento enviado. As mensagens do pacote entram no saldo assim que o pagamento
          for confirmado (no Pix, pode levar alguns minutos).
        </p>
      )}
      {retornoPacote === "cancelado" && (
        <p className="rounded-xl border bg-surface-2 px-4 py-3 text-sm text-muted">
          Compra do pacote cancelada. Nada foi cobrado.
        </p>
      )}

      {/* `limite` ausente = backend anterior à cota (deploy fora de ordem) */}
      {uso && temPlano && typeof uso.limite === "number" && (
        <CotaMensagens uso={uso} ocupado={ocupado} onComprar={comprarPacote} />
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
                  {p.mensagens_incluidas > 0 && (
                    <p className={"mt-2 text-xs font-medium " + (destaque ? "text-white/90" : "text-ink")}>
                      {p.mensagens_incluidas.toLocaleString("pt-BR")} mensagens da IA por mês
                    </p>
                  )}
                  <div className="mt-4 text-2xl font-bold">R$ {precoPlano(p.preco)}<span className={"text-sm font-normal " + (destaque ? "text-white/70" : "text-muted")}>/mês</span></div>
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

const num = (n: number) => n.toLocaleString("pt-BR");
const dataCurta = (iso: string) =>
  new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

function CotaMensagens({ uso, ocupado, onComprar }: {
  uso: Uso; ocupado: boolean; onComprar: (id: string) => void;
}) {
  const pct = Math.min(uso.percentual, 100);
  const alerta = !uso.ilimitado && uso.percentual >= 80;
  const barra = uso.esgotada ? "bg-danger" : alerta ? "bg-warning" : "bg-accent";

  return (
    <section className="rounded-2xl border bg-surface p-6 shadow-card">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-faint">
        <MessageSquare size={13} /> Mensagens da IA neste ciclo
      </p>

      {uso.ilimitado ? (
        <p className="mt-2 text-sm text-muted">
          {num(uso.usadas)} mensagens respondidas desde {dataCurta(uso.periodo_inicio)}. Sua conta
          não tem limite de mensagens.
        </p>
      ) : (
        <>
          <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-2xl font-bold tabular-nums text-ink">
              {num(uso.usadas)}{" "}
              <span className="text-base font-normal text-muted">de {num(uso.limite)}</span>
            </p>
            <p className="text-sm text-muted">
              {uso.esgotada ? "Saldo esgotado" : `${num(uso.restantes)} restantes`} · renova em{" "}
              {dataCurta(uso.periodo_fim)}
            </p>
          </div>
          <div
            className="mt-3 h-2.5 overflow-hidden rounded-full bg-surface-2"
            role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}
            aria-label="Uso das mensagens do ciclo"
          >
            <div className={"h-full rounded-full transition-all " + barra} style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-2 text-xs text-faint">
            {num(uso.incluidas)} do plano
            {uso.pacotes > 0 && ` + ${num(uso.pacotes)} de pacotes extras`}. Cada resposta do
            agente conta uma mensagem; ler documentos e catálogo não conta.
          </p>

          {uso.esgotada ? (
            <p className="mt-4 flex items-start gap-2 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              A IA parou de responder. Novas conversas estão indo para a fila humana até a
              renovação ou até você comprar um pacote.
            </p>
          ) : alerta ? (
            <p className="mt-4 flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              Você já usou {Math.floor(uso.percentual)}% das mensagens deste ciclo.
            </p>
          ) : null}

          {uso.pacotes_disponiveis?.length > 0 && (
            <div className="mt-6 border-t pt-5">
              <h3 className="text-sm font-semibold text-ink">Pacotes extras</h3>
              <p className="mt-0.5 text-xs text-muted">
                Pagamento único, sem mudar o plano. Vale até {dataCurta(uso.periodo_fim)}, o fim
                deste ciclo; o que sobrar não passa para o próximo.
              </p>
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                {uso.pacotes_disponiveis.map((p) => (
                  <div key={p.id} className="flex flex-col rounded-xl border p-4">
                    <p className="text-sm font-semibold text-ink">{p.nome}</p>
                    <p className="mt-1 text-xl font-bold tabular-nums text-ink">{brl(p.preco)}</p>
                    <p className="text-xs text-faint">
                      {brl(p.preco / p.mensagens)} por mensagem
                    </p>
                    <button
                      onClick={() => onComprar(p.id)} disabled={ocupado}
                      className="mt-3 rounded-lg bg-feature px-3 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-60"
                    >
                      Comprar
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {uso.pacotes_ativos?.length > 0 && (
            <p className="mt-4 text-xs text-muted">
              Pacotes ativos:{" "}
              {uso.pacotes_ativos
                .map((p) => `+${num(p.mensagens)} (até ${dataCurta(p.valido_ate)})`)
                .join(" · ")}
            </p>
          )}
        </>
      )}
    </section>
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
