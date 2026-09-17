import Link from "next/link";
import {
  QrCode, FileUp, SlidersHorizontal, BookOpenCheck, Hand, ReceiptText, Bot,
  UserRound, Megaphone, BarChart3, Plus, Lock,
} from "lucide-react";
import { ConversaDemo, PainelDemo } from "./_components/mockups";
import { PlanosCards } from "./_components/planos";
import { api } from "@/lib/api";
import { precoPlano } from "@/lib/format";

// O preço dos planos é parametrizado na central admin: renderiza a cada acesso.
export const dynamic = "force-dynamic";

// Passos reais de ativação — é uma sequência, por isso a numeração.
const PASSOS = [
  {
    icon: QrCode,
    t: "Conecte seu número",
    d: "Leia um QR Code no painel. O número continua o mesmo e nada muda para quem já fala com você.",
  },
  {
    icon: FileUp,
    t: "Suba seu catálogo",
    d: "Importe a planilha de produtos e anexe manuais, tabelas e PDFs. É desse material que o agente tira as respostas.",
  },
  {
    icon: SlidersHorizontal,
    t: "Diga o que ele pode fazer",
    d: "Ligue as capacidades — tirar dúvida, orçar, cadastrar, chamar o vendedor — e defina o tom de voz da sua empresa.",
  },
];

const RECURSOS = [
  {
    icon: BookOpenCheck,
    t: "Responde com o que é seu",
    d: "Preço, código e variante saem do seu catálogo e dos seus documentos. Quando não sabe, não inventa: passa para uma pessoa.",
  },
  {
    icon: ReceiptText,
    t: "Orçamento que chega no vendedor",
    d: "O agente monta o orçamento, registra o cliente e avisa seu vendedor no WhatsApp na mesma hora.",
  },
  {
    icon: Hand,
    t: "Sua equipe assume quando quiser",
    d: "Fila humana, conversa assumida em um clique e notas internas que o cliente nunca vê.",
  },
  {
    icon: UserRound,
    t: "Lembra de cada cliente",
    d: "Com a hiperpersonalização ligada, o agente considera os pedidos e orçamentos anteriores antes de responder.",
  },
  {
    icon: Bot,
    t: "Um agente para cada número",
    d: "Vendas, pós-venda e suporte com personas e permissões diferentes, na mesma conta.",
  },
  {
    icon: Megaphone,
    t: "Promoções para a sua base",
    d: "Envie campanhas segmentadas pelo painel, com descadastro automático para quem pedir.",
  },
];

// Textos de venda dos planos; o PREÇO vem da API (tabela `plans`).
const PERGUNTAS = [
  {
    q: "Preciso trocar o número da empresa?",
    a: "Não. Você conecta o número que já usa lendo um QR Code no painel. Se preferir, pode usar um número novo só para o atendimento automático.",
  },
  {
    q: "E se o agente não souber responder?",
    a: "Ele responde apenas com base no seu catálogo e nos documentos que você enviou. Fora disso, avisa o cliente e coloca a conversa na fila humana para a sua equipe.",
  },
  {
    q: "Como funciona a cobrança do consumo?",
    a: "Além da mensalidade, você paga pelo que a IA usa: as conversas com seus clientes e os documentos que ela lê para aprender sobre o seu negócio. As tarifas e o valor acumulado do mês ficam visíveis no painel, em Assinatura.",
  },
  {
    q: "Tem fidelidade ou multa?",
    a: "Não. A assinatura é mensal e você cancela pelo próprio painel. O acesso continua até o fim do período já pago.",
  },
  {
    q: "Tem período de teste grátis?",
    a: "Não temos teste. Em troca, não há fidelidade: você assina, usa no seu número real e cancela quando quiser.",
  },
  {
    q: "Meus dados ficam separados dos de outras empresas?",
    a: "Sim. Cada conta tem catálogo, conversas e base de conhecimento isolados, e o agente só consulta o que pertence à sua empresa.",
  },
];

async function precosVigentes(): Promise<Record<string, number>> {
  try {
    const planos = await api.planos();
    return Object.fromEntries(planos.map((p) => [p.id, p.preco]));
  } catch {
    return {};
  }
}

export default async function Landing() {
  const precos = await precosVigentes();
  return (
    <main>
      {/* ---------- Hero ---------- */}
      <section className="overflow-hidden">
        <div className="mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-12 px-6 pb-20 pt-12 md:pt-20 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] lg:gap-10">
          <div>
            <h1 className="site-display site-h1 text-balance text-ink">
              O cliente chama no WhatsApp. O AtentBot responde, orça e chama seu vendedor.
            </h1>
            <p className="mt-6 max-w-[34rem] text-pretty text-lg leading-relaxed text-muted">
              Um atendente de IA que conhece o seu catálogo: tira dúvida de produto, monta o
              orçamento e entrega a conversa para a sua equipe na hora certa. A qualquer hora,
              no número que seus clientes já têm.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link
                href="/cadastro"
                className="rounded-full bg-feature px-7 py-3.5 text-[15px] font-semibold text-feature-fg transition hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Criar conta
              </Link>
              <Link
                href="#planos"
                className="rounded-full border bg-surface px-7 py-3.5 text-[15px] font-semibold text-ink transition hover:bg-surface-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Ver planos
              </Link>
            </div>
            <p className="mt-4 text-sm text-faint">Assinatura mensal, sem fidelidade. Cancele pelo painel quando quiser.</p>
          </div>

          {/* Palco escuro com a conversa — sangra na borda direita no desktop */}
          <figure className="relative lg:-mr-[max(1.5rem,calc((100vw_-_72rem)/2_+_1.5rem))]">
            <div className="stage-glow relative flex justify-center rounded-[32px] bg-stage px-5 py-10 sm:px-10 sm:py-14 lg:justify-start lg:rounded-r-none lg:pl-14">
              <ConversaDemo />
            </div>
            <figcaption className="mt-3 max-w-md text-xs text-faint lg:pl-2">
              Conversa de demonstração. O atendimento aconteceu às 22h41, o vendedor assumiu na manhã seguinte.
            </figcaption>
          </figure>
        </div>
      </section>

      {/* ---------- Como funciona ---------- */}
      <section id="como-funciona" className="border-t bg-surface">
        <div className="mx-auto w-full max-w-6xl px-6 py-20">
          <div className="max-w-2xl">
            <h2 className="site-display site-h2 text-ink">No ar no mesmo dia</h2>
            <p className="mt-3 text-lg text-muted">
              Sem integração complicada e sem ninguém instalar app novo. Três passos no painel.
            </p>
          </div>
          <ol className="mt-12 grid gap-10 md:grid-cols-3 md:gap-8">
            {PASSOS.map((p, i) => (
              <li key={p.t} className="border-t-2 border-ink pt-5">
                <span className="flex items-center justify-between">
                  <span className="site-display text-3xl text-faint">{i + 1}</span>
                  <p.icon size={22} className="text-accent" aria-hidden />
                </span>
                <h3 className="mt-4 text-lg font-semibold text-ink">{p.t}</h3>
                <p className="mt-2 leading-relaxed text-muted">{p.d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---------- Recursos ---------- */}
      <section id="recursos" className="border-t">
        <div className="mx-auto w-full max-w-6xl px-6 py-20">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
            <div className="lg:sticky lg:top-28 lg:self-start">
              <h2 className="site-display site-h2 text-balance text-ink">
                Conversa como gente, sem hora para acabar
              </h2>
              <p className="mt-4 text-lg leading-relaxed text-muted">
                O AtentBot não é um menu de opções com "digite 1". Ele entende a pergunta,
                consulta o seu material e conversa. E sabe a hora de chamar uma pessoa.
              </p>
            </div>
            <div className="grid gap-x-10 gap-y-10 sm:grid-cols-2">
              {RECURSOS.map((r) => (
                <div key={r.t}>
                  <r.icon size={22} className="text-accent" aria-hidden />
                  <h3 className="mt-3 text-base font-semibold text-ink">{r.t}</h3>
                  <p className="mt-1.5 leading-relaxed text-muted">{r.d}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---------- Painel ---------- */}
      <section className="bg-stage">
        <div className="stage-glow">
          <div className="mx-auto w-full max-w-6xl px-6 pb-16 pt-20">
            <div className="grid gap-6 md:grid-cols-2 md:items-end">
              <h2 className="site-display site-h2 text-balance text-stage-fg">
                Tudo o que o agente faz, você acompanha
              </h2>
              <p className="text-lg leading-relaxed text-stage-muted">
                Conversas, fila humana, orçamentos, catálogo e o consumo do mês em um painel só.
                Dá para entrar em qualquer conversa e assumir o atendimento na hora.
              </p>
            </div>
            <div className="mt-12">
              <PainelDemo />
            </div>
            <p className="mt-3 text-xs text-stage-muted">Tela do painel com dados de exemplo.</p>

            <div className="mt-14 grid gap-8 border-t border-stage-line pt-10 sm:grid-cols-3">
              <div className="flex gap-3">
                <BarChart3 size={20} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                <p className="text-stage-muted">
                  <span className="font-semibold text-stage-fg">Métricas do atendimento.</span>{" "}
                  Conversas, conversão e tempo de resposta por período.
                </p>
              </div>
              <div className="flex gap-3">
                <Lock size={20} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                <p className="text-stage-muted">
                  <span className="font-semibold text-stage-fg">Dados isolados por empresa.</span>{" "}
                  Seu catálogo e suas conversas não se misturam com os de ninguém.
                </p>
              </div>
              <div className="flex gap-3">
                <Hand size={20} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                <p className="text-stage-muted">
                  <span className="font-semibold text-stage-fg">Suporte de gente.</span>{" "}
                  Abra um chamado pelo painel e acompanhe a resposta por lá e por e-mail.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- Planos ---------- */}
      <section id="planos" className="scroll-mt-20">
        <div className="mx-auto w-full max-w-6xl px-6 py-20">
          <div className="max-w-2xl">
            <h2 className="site-display site-h2 text-ink">Planos</h2>
            <p className="mt-3 text-lg text-muted">
              Escolha pelo tamanho da sua operação. Você paga a mensalidade do plano mais o
              consumo da IA, e muda de plano quando precisar.
            </p>
          </div>

          <PlanosCards />

          {/* Como o consumo é cobrado — transparência que costuma decidir a compra */}
          <div className="mt-12 grid gap-6 rounded-3xl border bg-surface p-7 md:grid-cols-[minmax(0,4fr)_minmax(0,5fr)] md:gap-10">
            <div>
              <h3 className="text-lg font-semibold text-ink">Todos os planos incluem</h3>
              <p className="mt-2 leading-relaxed text-muted">
                Painel completo, importação de catálogo, base de conhecimento com seus documentos,
                fila humana e suporte por chamados.
              </p>
            </div>
            <div className="md:border-l md:pl-10">
              <h3 className="text-lg font-semibold text-ink">Como o consumo é cobrado</h3>
              <p className="mt-2 leading-relaxed text-muted">
                Você paga pelo que a IA usa de fato: as conversas com seus clientes e os documentos
                que ela lê para aprender sobre o seu negócio. O
                valor acumulado aparece no painel ao longo do mês.
              </p>
              <p className="mt-3 text-sm text-faint">
                Detalhes nas{" "}
                <Link href="/cobranca" className="text-accent-ink underline-offset-2 hover:underline">regras de cobrança</Link>{" "}
                e na{" "}
                <Link href="/confidencialidade" className="text-accent-ink underline-offset-2 hover:underline">política de confidencialidade</Link>.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- Perguntas ---------- */}
      <section id="perguntas" className="border-t bg-surface">
        <div className="mx-auto grid w-full max-w-6xl gap-10 px-6 py-20 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] lg:gap-16">
          <div>
            <h2 className="site-display site-h2 text-ink">Antes de assinar</h2>
            <p className="mt-3 text-lg text-muted">
              Ficou alguma dúvida? Escreva para{" "}
              <a href="mailto:contato@dewconsultoria.com.br" className="text-accent-ink underline-offset-2 hover:underline">
                contato@dewconsultoria.com.br
              </a>.
            </p>
          </div>
          <div className="border-t">
            {PERGUNTAS.map((f) => (
              <details key={f.q} className="group border-b">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-left text-[17px] font-medium text-ink outline-none focus-visible:text-accent-ink [&::-webkit-details-marker]:hidden">
                  {f.q}
                  <Plus size={18} className="shrink-0 text-muted transition-transform group-open:rotate-45" aria-hidden />
                </summary>
                <p className="max-w-[60ch] pb-6 leading-relaxed text-muted">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- CTA final ---------- */}
      <section className="mx-auto w-full max-w-6xl px-6 py-20">
        <div className="stage-glow overflow-hidden rounded-[32px] bg-stage px-8 py-16 md:px-16">
          <div className="max-w-2xl">
            <h2 className="site-display site-h2 text-balance text-stage-fg">
              A próxima mensagem do seu cliente pode ser respondida em segundos
            </h2>
            <p className="mt-4 text-lg text-stage-muted">
              Crie a conta, conecte o número e importe o catálogo. O resto o AtentBot faz.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link
                href="/cadastro"
                className="rounded-full bg-cta px-7 py-3.5 text-[15px] font-semibold text-cta-fg transition hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stage-fg"
              >
                Criar conta
              </Link>
              <a
                href="mailto:contato@dewconsultoria.com.br?subject=Quero%20conhecer%20o%20AtentBot"
                className="rounded-full border border-stage-line px-7 py-3.5 text-[15px] font-semibold text-stage-fg transition hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-stage-fg"
              >
                Falar com a equipe
              </a>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
