import { CheckCheck, Bot, Search } from "lucide-react";

/**
 * Mockups da landing. São peças de demonstração, renderizadas em HTML
 * (sem imagem) para acompanhar o tema e ficar nítidas em qualquer tela.
 * Conteúdo é ilustrativo — está rotulado como tal nas legendas da página.
 */

type Bolha = {
  de: "cliente" | "agente";
  texto: React.ReactNode;
  hora: string;
};

const CONVERSA: Bolha[] = [
  {
    de: "cliente",
    hora: "22:41",
    texto: "Boa noite. Vocês têm captor Franklin de 3 pontas?",
  },
  {
    de: "agente",
    hora: "22:41",
    texto: (
      <>
        Temos, sim. O <strong className="font-semibold">captor Franklin 3 pontas em latão
        niquelado (CF-3N)</strong> sai por R$ 189,90, e a versão em aço inox por R$ 214,00.
        A base é para mastro de 1/2" ou 3/4"?
      </>
    ),
  },
  {
    de: "cliente",
    hora: "22:43",
    texto: "3/4. Me manda o orçamento de 4 unidades com os mastros.",
  },
  {
    de: "agente",
    hora: "22:43",
    texto: (
      <>
        Orçamento 1042: 4× CF-3N + 4× mastro 3/4" de 2 m, total{" "}
        <strong className="font-semibold">R$ 1.436,60</strong>. Já registrei no seu cadastro e
        avisei o Rafael, do comercial. Ele te chama amanhã cedo com o prazo de entrega.
      </>
    ),
  },
];

export function ConversaDemo() {
  return (
    <div className="w-full max-w-[420px] overflow-hidden rounded-[22px] bg-surface shadow-[0_40px_80px_-30px_rgba(2,6,15,0.85)] ring-1 ring-black/10">
      {/* Cabeçalho do chat */}
      <div className="flex items-center gap-3 border-b bg-surface px-4 py-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent-ink">
          MF
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-ink">Marcos Ferreira</span>
          <span className="block truncate text-xs text-faint">+55 11 9 •••• 4417</span>
        </span>
        <span className="ml-auto inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent-ink">
          <Bot size={12} /> IA no comando
        </span>
      </div>

      {/* Thread */}
      <div className="flex flex-col gap-2.5 bg-surface-2 px-4 py-5">
        {CONVERSA.map((b, i) => (
          <div
            key={i}
            className={"msg flex " + (b.de === "agente" ? "justify-end" : "justify-start")}
            style={{ ["--d" as string]: `${0.25 + i * 0.45}s` }}
          >
            <div
              className={
                "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed shadow-sm " +
                (b.de === "agente"
                  ? "rounded-br-md bg-accent-soft text-accent-ink"
                  : "rounded-bl-md bg-surface text-ink")
              }
            >
              {b.texto}
              <span className="mt-1 flex items-center justify-end gap-1 text-[10px] text-faint">
                {b.hora}
                {b.de === "agente" && <CheckCheck size={12} className="text-tick" />}
              </span>
            </div>
          </div>
        ))}

        <div className="msg mt-1 flex justify-center" style={{ ["--d" as string]: "2.1s" }}>
          <span className="rounded-full bg-surface px-3 py-1.5 text-[11px] text-muted shadow-sm">
            Rafael, do comercial, assumiu a conversa às 07:58
          </span>
        </div>
      </div>
    </div>
  );
}

const TILES = [
  { rotulo: "Conversas hoje", valor: "38" },
  { rotulo: "Orçamentos", valor: "12" },
  { rotulo: "Resposta média", valor: "4 s" },
  { rotulo: "Consumo do mês", valor: "R$ 84,20" },
];

const LINHAS = [
  { nome: "Marcos Ferreira", ultima: "Orçamento 1042 enviado", tag: "Com o Rafael", quente: true },
  { nome: "Construtora Vega", ultima: "Qual o prazo do cabo de cobre 35 mm?", tag: "IA atendendo" },
  { nome: "Eletrocamp Materiais", ultima: "Pode faturar os 3 mastros", tag: "Na fila humana", quente: true },
  { nome: "Juliana Prado", ultima: "Obrigada! Já recebi a NF", tag: "Encerrada" },
];

export function PainelDemo() {
  return (
    <div className="overflow-hidden rounded-2xl bg-surface shadow-[0_40px_90px_-40px_rgba(2,6,15,0.9)] ring-1 ring-black/10">
      {/* Barra da janela */}
      <div className="flex items-center gap-2 border-b bg-surface-2 px-4 py-2.5">
        <span className="flex gap-1.5">
          <i className="h-2.5 w-2.5 rounded-full bg-border" />
          <i className="h-2.5 w-2.5 rounded-full bg-border" />
          <i className="h-2.5 w-2.5 rounded-full bg-border" />
        </span>
        <span className="mx-auto rounded-md bg-surface px-3 py-1 text-[11px] text-faint">
          atentbot.com/painel
        </span>
      </div>

      <div className="flex">
        {/* Menu */}
        <div className="hidden w-44 shrink-0 flex-col gap-1 border-r bg-surface-2 p-3 sm:flex">
          <span className="mb-2 flex items-center gap-2 px-2 text-sm font-semibold text-ink">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/simbolo.png" alt="" className="h-4 w-auto" /> AtentBot
          </span>
          {["Painel", "Atendimento", "Fila humana", "Orçamentos", "Catálogo", "Agentes"].map((m, i) => (
            <span
              key={m}
              className={
                "rounded-lg px-2.5 py-1.5 text-xs " +
                (i === 1 ? "bg-feature font-medium text-feature-fg" : "text-muted")
              }
            >
              {m}
            </span>
          ))}
        </div>

        {/* Conteúdo */}
        <div className="min-w-0 flex-1 p-4 sm:p-5">
          <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
            {TILES.map((t) => (
              <div key={t.rotulo} className="rounded-xl border bg-surface-2 p-3">
                <span className="block text-[11px] text-muted">{t.rotulo}</span>
                <span className="tnum mt-1 block text-xl font-semibold text-ink">{t.valor}</span>
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-xl border">
            <div className="flex items-center gap-2 border-b px-3 py-2 text-xs text-faint">
              <Search size={13} /> Buscar cliente ou telefone
            </div>
            {LINHAS.map((l) => (
              <div key={l.nome} className="flex items-center gap-3 border-b px-3 py-2.5 last:border-b-0">
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-surface-2 text-[10px] font-semibold text-muted">
                  {l.nome.slice(0, 2).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium text-ink">{l.nome}</span>
                  <span className="block truncate text-[11px] text-muted">{l.ultima}</span>
                </span>
                <span
                  className={
                    "hidden shrink-0 rounded-full px-2 py-0.5 text-[10px] sm:inline " +
                    (l.quente ? "bg-accent-soft text-accent-ink" : "bg-surface-2 text-muted")
                  }
                >
                  {l.tag}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
