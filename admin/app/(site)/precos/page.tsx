"use client";

import { api } from "@/lib/api";
import { precoPlano } from "@/lib/format";
import type { Plano } from "@/lib/types";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function PrecosPage() {
  const router = useRouter();
  const [planos, setPlanos] = useState<Plano[] | null>(null);
  const [falhou, setFalhou] = useState(false);
  const [ocupado, setOcupado] = useState<string | null>(null);

  useEffect(() => {
    // Preço vem sempre da API (parametrizado na central admin).
    api.planos().then(setPlanos).catch(() => setFalhou(true));
  }, []);

  async function assinar(id: string) {
    setOcupado(id);
    try {
      // Precisa estar logado para o checkout; se não estiver, manda ao cadastro.
      await api.me();
    } catch {
      router.push(`/cadastro?plano=${id}`);
      return;
    }
    try {
      const { url } = await api.checkout(id);
      window.location.href = url;
    } catch {
      setOcupado(null);
      router.push("/assinatura");
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-16">
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight text-ink">Planos</h1>
        <p className="mt-2 text-muted">Assinatura mensal via Stripe. Sem trial, sem fidelidade.</p>
        <p className="mx-auto mt-1 max-w-xl text-sm text-faint">
          Você paga a <strong className="text-muted">mensalidade do plano</strong> +{" "}
          <strong className="text-muted">consumo</strong> (indexação de documentos e conversas
          da IA), medido por uso. Veja as{" "}
          <Link href="/cobranca" className="text-accent-ink hover:underline">regras de cobrança</Link>.
        </p>
      </div>

      {!planos && (
        <p className="mt-10 text-center text-sm text-muted">
          {falhou ? "Não foi possível carregar os planos agora. Tente novamente em instantes." : "Carregando planos…"}
        </p>
      )}
      <div className="mt-10 grid gap-5 md:grid-cols-3">
        {planos?.map((p) => {
          const destaque = p.id === "profissional";
          return (
            <div
              key={p.id}
              className={"flex flex-col rounded-2xl border p-6 shadow-card " + (destaque ? "bg-feature text-feature-fg" : "bg-surface")}
            >
              {destaque && (
                <span className="mb-3 w-fit rounded-full bg-cta px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-cta-fg">
                  Mais vendido
                </span>
              )}
              <h3 className={"text-lg font-semibold " + (destaque ? "text-feature-fg" : "text-ink")}>{p.nome}</h3>
              <p className={"mt-1 text-sm " + (destaque ? "text-white/70" : "text-muted")}>{p.descricao}</p>
              <div className="mt-5 flex items-end gap-1">
                <span className={"text-4xl font-bold " + (destaque ? "text-feature-fg" : "text-ink")}>
                  R$ {precoPlano(p.preco)}
                </span>
                <span className={"pb-1 text-sm " + (destaque ? "text-white/70" : "text-muted")}>/mês</span>
              </div>
              <button
                onClick={() => assinar(p.id)}
                disabled={!p.disponivel || ocupado === p.id}
                className={
                  "mt-6 rounded-xl px-4 py-2.5 text-center text-sm font-semibold transition disabled:opacity-60 " +
                  (destaque ? "bg-cta text-cta-fg hover:opacity-90" : "bg-feature text-feature-fg hover:opacity-90")
                }
              >
                {ocupado === p.id ? "Redirecionando…" : p.disponivel ? `Assinar ${p.nome}` : "Em breve"}
              </button>
            </div>
          );
        })}
      </div>
    </main>
  );
}
