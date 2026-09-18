"use client";

import { api } from "@/lib/api";
import { PlanosGrid } from "@/components/planos-grid";
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
      router.push("/ativar");
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-16">
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight text-ink">Planos</h1>
        <p className="mt-2 text-muted">Assinatura mensal via Stripe. Sem trial, sem fidelidade.</p>
        <p className="mx-auto mt-1 max-w-xl text-sm text-faint">
          A <strong className="text-muted">mensalidade</strong> já inclui as mensagens da IA do
          mês. Precisou de mais? Compre um <strong className="text-muted">pacote extra</strong>{" "}
          no painel, com pagamento único. Veja as{" "}
          <Link href="/cobranca" className="text-accent-ink hover:underline">regras de cobrança</Link>.
        </p>
      </div>

      {!planos && (
        <p className="mt-10 text-center text-sm text-muted">
          {falhou ? "Não foi possível carregar os planos agora. Tente novamente em instantes." : "Carregando planos…"}
        </p>
      )}
      {planos && (
        <div className="mt-10">
          <PlanosGrid planos={planos} ocupado={ocupado} onAssinar={assinar} />
        </div>
      )}
    </main>
  );
}
