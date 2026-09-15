import Link from "next/link";
import {
  Zap, MessagesSquare, Package, Users, Megaphone, BarChart3, ShieldCheck, ArrowRight,
} from "lucide-react";

const BENEF = [
  { icon: MessagesSquare, t: "Atende sozinho no WhatsApp", d: "Um agente de IA responde, cadastra o cliente e monta o orçamento — 24/7, no seu número." },
  { icon: Package, t: "Ancorado no seu catálogo", d: "Ingestão do seu catálogo para respostas certas sobre produto, variante e código. Nada de alucinação." },
  { icon: Users, t: "Humano no loop", d: "Fila de atendimento, notas internas e handoff para o vendedor com alerta automático." },
  { icon: Megaphone, t: "Promoções em massa", d: "Broadcast segmentado com opt-out, direto do painel." },
  { icon: BarChart3, t: "Métricas do atendimento", d: "Conversas, orçamentos, conversão e tempo de resposta num dashboard só seu." },
  { icon: ShieldCheck, t: "Multi-número e multi-agente", d: "Vários números e personas na mesma conta, cada um com suas capacidades." },
];

const PLANOS = [
  { id: "essencial", nome: "Essencial", preco: "690", d: "1 número · 1 agente · catálogo até 500 SKUs · 3 usuários.", destaque: false },
  { id: "profissional", nome: "Profissional", preco: "1.690", d: "Até 3 números · multi-agente · equipe · broadcast · 8 usuários.", destaque: true },
  { id: "escala", nome: "Escala", preco: "3.900", d: "Números ilimitados · WhatsApp API oficial · ERP · SLA.", destaque: false },
];

export default function Landing() {
  return (
    <main>
      {/* Hero */}
      <section className="mx-auto w-full max-w-6xl px-6 pb-16 pt-16 md:pt-24">
        <div className="mx-auto max-w-3xl text-center">
          <span className="mb-5 inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent-soft px-3 py-1 text-xs font-medium text-accent-ink">
            <Zap size={13} className="fill-accent-ink" /> Atendimento com IA no WhatsApp
          </span>
          <h1 className="text-balance text-4xl font-bold tracking-tight text-ink md:text-6xl">
            O atendente de IA que vende pelo WhatsApp do seu negócio.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-pretty text-lg text-muted">
            O AtentBot responde dúvidas de produto, cadastra clientes e gera orçamentos —
            ancorado no seu catálogo — e passa para a sua equipe na hora certa. Para
            distribuidores e PMEs de qualquer ramo.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link href="/cadastro" className="inline-flex items-center gap-2 rounded-xl bg-feature px-5 py-3 text-sm font-semibold text-feature-fg transition hover:opacity-90">
              Criar conta <ArrowRight size={16} />
            </Link>
            <Link href="/precos" className="rounded-xl border px-5 py-3 text-sm font-semibold text-ink transition hover:bg-surface-2">
              Ver planos
            </Link>
          </div>
          <p className="mt-3 text-xs text-faint">Sem período de teste — você assina e já começa a usar.</p>
        </div>
      </section>

      {/* Benefícios */}
      <section className="border-y bg-surface/50">
        <div className="mx-auto grid w-full max-w-6xl gap-px overflow-hidden rounded-2xl px-6 py-14 sm:grid-cols-2 lg:grid-cols-3">
          {BENEF.map((b) => (
            <div key={b.t} className="p-6">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-accent-soft text-accent-ink">
                <b.icon size={20} />
              </span>
              <h3 className="mt-4 text-base font-semibold text-ink">{b.t}</h3>
              <p className="mt-1.5 text-sm text-muted">{b.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Planos */}
      <section id="planos" className="mx-auto w-full max-w-6xl px-6 py-16">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-ink">Planos</h2>
          <p className="mt-2 text-muted">Assinatura mensal. Sem trial, sem fidelidade — cancele quando quiser.</p>
        </div>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {PLANOS.map((p) => (
            <div
              key={p.id}
              className={
                "flex flex-col rounded-2xl border p-6 shadow-card " +
                (p.destaque ? "bg-feature text-feature-fg" : "bg-surface")
              }
            >
              {p.destaque && (
                <span className="mb-3 w-fit rounded-full bg-accent px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#3a2500]">
                  Mais vendido
                </span>
              )}
              <h3 className={"text-lg font-semibold " + (p.destaque ? "text-feature-fg" : "text-ink")}>{p.nome}</h3>
              <p className={"mt-1 text-sm " + (p.destaque ? "text-white/70" : "text-muted")}>{p.d}</p>
              <div className="mt-5 flex items-end gap-1">
                <span className={"text-4xl font-bold " + (p.destaque ? "text-feature-fg" : "text-ink")}>R$ {p.preco}</span>
                <span className={"pb-1 text-sm " + (p.destaque ? "text-white/70" : "text-muted")}>/mês</span>
              </div>
              <Link
                href={`/cadastro?plano=${p.id}`}
                className={
                  "mt-6 rounded-xl px-4 py-2.5 text-center text-sm font-semibold transition " +
                  (p.destaque
                    ? "bg-accent text-[#3a2500] hover:opacity-90"
                    : "bg-feature text-feature-fg hover:opacity-90")
                }
              >
                Assinar {p.nome}
              </Link>
            </div>
          ))}
        </div>
        <p className="mx-auto mt-6 max-w-2xl text-center text-xs text-faint">
          Mensalidade do plano <strong>+ consumo</strong> (indexação de documentos e conversas
          da IA, pay-per-use). Sem trial; cobrança via Stripe. Veja as{" "}
          <Link href="/cobranca" className="text-accent-ink hover:underline">regras de cobrança</Link>{" "}
          e a{" "}
          <Link href="/confidencialidade" className="text-accent-ink hover:underline">confidencialidade</Link>.
        </p>
      </section>

      {/* CTA final */}
      <section className="mx-auto w-full max-w-6xl px-6 pb-20">
        <div className="rounded-2xl bg-feature px-8 py-12 text-center text-feature-fg">
          <h2 className="text-2xl font-bold md:text-3xl">Pronto para pôr a IA para atender?</h2>
          <p className="mx-auto mt-2 max-w-xl text-white/70">
            Crie sua conta, conecte um número de WhatsApp e comece a atender em minutos.
          </p>
          <Link href="/cadastro" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-3 text-sm font-semibold text-[#3a2500] transition hover:opacity-90">
            Criar conta <ArrowRight size={16} />
          </Link>
        </div>
      </section>
    </main>
  );
}
