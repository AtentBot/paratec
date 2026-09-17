"use client";

import { api } from "@/lib/api";
import { precoPlano } from "@/lib/format";
import type { Plano } from "@/lib/types";
import { Check, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

/**
 * Cards de planos da landing. Nome, preço e disponibilidade vêm SEMPRE da API
 * (parametrizados na central admin) — aqui só mora o texto de venda de cada plano.
 */
const COPY: Record<string, { para: string; itens: string[] }> = {
  essencial: {
    para: "Para quem quer tirar o WhatsApp do sufoco.",
    itens: ["1 número de WhatsApp", "1 agente de IA", "Catálogo de até 500 produtos", "3 usuários no painel", "Fila humana e orçamentos"],
  },
  profissional: {
    para: "Para equipes comerciais que vendem pelo WhatsApp todo dia.",
    itens: ["Até 3 números", "Vários agentes, um por número", "Alerta para a equipe de vendas", "Promoções em massa", "8 usuários no painel"],
  },
  escala: {
    para: "Para operações com volume alto e integração.",
    itens: ["Números ilimitados", "API oficial do WhatsApp", "Integração com ERP", "SLA de atendimento do suporte"],
  },
};

const DESTAQUE = "profissional";

const focus =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export function PlanosCards() {
  const [planos, setPlanos] = useState<Plano[] | null>(null);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    api.planos().then(setPlanos).catch(() => setFalhou(true));
  }, []);

  if (falhou) {
    return (
      <p className="mt-12 rounded-3xl border bg-surface p-7 text-muted">
        Não foi possível carregar os planos agora. Atualize a página em instantes ou{" "}
        <Link href="/precos" className="text-accent-ink underline-offset-2 hover:underline">abra a página de planos</Link>.
      </p>
    );
  }

  // Enquanto carrega, desenha os cards com a mesma altura para a página não pular.
  const lista: (Plano | null)[] = planos ?? [null, null, null];

  return (
    <div className="mt-12 grid gap-5 lg:grid-cols-3" aria-busy={!planos}>
      {lista.map((p, i) => {
        const d = p ? p.id === DESTAQUE : i === 1;
        const copy = p ? COPY[p.id] : undefined;
        return (
          <div
            key={p?.id ?? i}
            className={
              "relative flex flex-col rounded-3xl p-7 " +
              (d ? "bg-stage text-stage-fg lg:-my-4 lg:py-11" : "border bg-surface")
            }
          >
            <div className="flex items-baseline justify-between gap-3">
              <h3 className={"site-display text-2xl " + (d ? "text-stage-fg" : "text-ink")}>
                {p ? p.nome : <span className="inline-block h-7 w-32 animate-pulse rounded-lg bg-current opacity-10" />}
              </h3>
              {d && p && (
                <span className="rounded-full bg-cta px-3 py-1 text-xs font-semibold text-cta-fg">
                  Mais escolhido
                </span>
              )}
            </div>
            <p className={"mt-2 min-h-[3rem] " + (d ? "text-stage-muted" : "text-muted")}>
              {copy?.para ?? p?.descricao}
            </p>

            <p className="mt-7 flex items-baseline gap-1.5">
              <span className={"text-sm " + (d ? "text-stage-muted" : "text-muted")}>R$</span>
              <span className={"site-display tnum text-5xl " + (d ? "text-stage-fg" : "text-ink")}>
                {p ? precoPlano(p.preco) : <span className="inline-block h-10 w-28 animate-pulse rounded-lg bg-current align-middle opacity-10" />}
              </span>
              <span className={"text-sm " + (d ? "text-stage-muted" : "text-muted")}>por mês</span>
            </p>
            <p className={"mt-1 flex items-center gap-1 text-xs " + (d ? "text-stage-muted" : "text-faint")}>
              <Plus size={12} aria-hidden /> consumo da IA
            </p>

            <ul className={"mt-7 flex flex-1 flex-col gap-3 border-t pt-6 " + (d ? "border-stage-line" : "")}>
              {(copy?.itens ?? []).map((it) => (
                <li key={it} className={"flex gap-2.5 text-[15px] " + (d ? "text-stage-fg" : "text-ink")}>
                  <Check size={18} className={"mt-0.5 shrink-0 " + (d ? "text-accent" : "text-tick")} aria-hidden />
                  {it}
                </li>
              ))}
            </ul>

            {p && p.disponivel ? (
              <Link
                href={`/cadastro?plano=${p.id}`}
                className={
                  "mt-8 rounded-full px-5 py-3.5 text-center text-[15px] font-semibold transition hover:opacity-90 " + focus + " " +
                  (d ? "bg-cta text-cta-fg" : "bg-feature text-feature-fg")
                }
              >
                Assinar o {p.nome}
              </Link>
            ) : (
              <span
                className={
                  "mt-8 rounded-full px-5 py-3.5 text-center text-[15px] font-semibold " +
                  (d ? "bg-white/10 text-stage-muted" : "bg-surface-2 text-faint")
                }
              >
                {p ? "Em breve" : "Carregando…"}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
