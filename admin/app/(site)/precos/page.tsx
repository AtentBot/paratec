"use client";

import { api } from "@/lib/api";
import type { Plano } from "@/lib/types";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const FALLBACK: Plano[] = [
  { id: "essencial", nome: "Essencial", preco: 690, descricao: "1 número · 1 agente · catálogo até 500 SKUs · 3 usuários.", disponivel: true },
  { id: "profissional", nome: "Profissional", preco: 1690, descricao: "Até 3 números · multi-agente · equipe · broadcast · 8 usuários.", disponivel: true },
  { id: "escala", nome: "Escala", preco: 3900, descricao: "Números ilimitados · WhatsApp API oficial · ERP · SLA.", disponivel: true },
];

export default function PrecosPage() {
  const router = useRouter();
  const [planos, setPlanos] = useState<Plano[]>(FALLBACK);
  const [ocupado, setOcupado] = useState<string | null>(null);

  useEffect(() => {
    api.planos().then((p) => p?.length && setPlanos(p)).catch(() => {});
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

      <div className="mt-10 grid gap-5 md:grid-cols-3">
        {planos.map((p) => {
          const destaque = p.id === "profissional";
          return (
            <div
              key={p.id}
              className={"flex flex-col rounded-2xl border p-6 shadow-card " + (destaque ? "bg-feature text-feature-fg" : "bg-surface")}
            >
              {destaque && (
                <span className="mb-3 w-fit rounded-full bg-accent px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#3a2500]">
                  Mais vendido
                </span>
              )}
              <h3 className={"text-lg font-semibold " + (destaque ? "text-feature-fg" : "text-ink")}>{p.nome}</h3>
              <p className={"mt-1 text-sm " + (destaque ? "text-white/70" : "text-muted")}>{p.descricao}</p>
              <div className="mt-5 flex items-end gap-1">
                <span className={"text-4xl font-bold " + (destaque ? "text-feature-fg" : "text-ink")}>
                  R$ {p.preco.toLocaleString("pt-BR")}
                </span>
                <span className={"pb-1 text-sm " + (destaque ? "text-white/70" : "text-muted")}>/mês</span>
              </div>
              <button
                onClick={() => assinar(p.id)}
                disabled={!p.disponivel || ocupado === p.id}
                className={
                  "mt-6 rounded-xl px-4 py-2.5 text-center text-sm font-semibold transition disabled:opacity-60 " +
                  (destaque ? "bg-accent text-[#3a2500] hover:opacity-90" : "bg-feature text-feature-fg hover:opacity-90")
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
