"use client";

import { PlanosGrid } from "@/components/planos-grid";
import { api } from "@/lib/api";
import type { Me, Plano } from "@/lib/types";
import { Loader2, Lock } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const STATUS_LABEL: Record<string, string> = {
  past_due: "com pagamento pendente",
  canceled: "cancelada",
  unpaid: "não paga",
  incomplete: "com pagamento incompleto",
  incomplete_expired: "expirada",
};

// Parede de pagamento: todo acesso ao painel exige plano ativo (cartão no
// Stripe). Quem está logado sem assinatura ativa cai aqui (ver AccountGate).
export default function AtivarPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [planos, setPlanos] = useState<Plano[] | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [suporte, setSuporte] = useState<string | null>(null);

  useEffect(() => {
    api
      .me()
      .then((m) => {
        if (m.assinatura.ativa || m.is_staff) {
          router.replace("/painel");
          return;
        }
        if (!m.verificacoes.whatsapp) {
          router.replace("/verificar-whatsapp");
          return;
        }
        setMe(m);
      })
      .catch(() => router.replace("/login?next=/ativar"));
    api.planos().then(setPlanos).catch(() => setPlanos([]));
    api.suporteEmail().then((c) => setSuporte(c.email)).catch(() => {});
  }, [router]);

  async function assinar(id: string) {
    setOcupado(id);
    setErro(null);
    try {
      const { url } = await api.checkout(id);
      window.location.href = url;
    } catch (e) {
      setErro(
        e instanceof Error && e.message.includes("403")
          ? "Apenas o responsável pela conta pode assinar."
          : "Não foi possível iniciar o pagamento. Tente novamente.",
      );
      setOcupado(null);
    }
  }

  if (!me) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-muted">
        <Loader2 size={16} className="animate-spin" /> Carregando…
      </div>
    );
  }

  const lapsada = me.assinatura.tem_assinatura && me.assinatura.status !== "sem_assinatura";

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-14">
      <div className="mx-auto max-w-2xl text-center">
        <Lock size={36} className="mx-auto text-accent-ink" />
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink">
          {lapsada ? "Reative sua assinatura" : "Escolha seu plano para começar"}
        </h1>
        <p className="mt-2 text-muted">
          {lapsada
            ? `A assinatura de ${me.tenant.nome || "sua empresa"} está ${STATUS_LABEL[me.assinatura.status] || "inativa"}. Escolha um plano para voltar a usar o painel.`
            : `Olá${me.nome ? `, ${me.nome}` : ""}! O acesso ao AtentBot é liberado assim que a assinatura de ${me.tenant.nome || "sua empresa"} for ativada.`}
        </p>
        <p className="mt-1 text-sm text-faint">
          Pagamento com cartão pelo Stripe. A mensalidade inclui as mensagens da IA do mês; pacotes extras só se você quiser. Sem
          fidelidade. Veja as{" "}
          <Link href="/cobranca" target="_blank" className="text-accent-ink hover:underline">regras de cobrança</Link>.
        </p>
      </div>

      {erro && <p className="mt-6 text-center text-sm text-danger">{erro}</p>}

      <div className="mt-10">
        {planos === null ? (
          <p className="text-center text-sm text-muted">Carregando planos…</p>
        ) : planos.length === 0 ? (
          <p className="text-center text-sm text-muted">Não foi possível carregar os planos agora.</p>
        ) : (
          <PlanosGrid planos={planos} ocupado={ocupado} onAssinar={assinar} />
        )}
      </div>

      {suporte && (
        <p className="mt-10 text-center text-sm text-muted">
          Dúvidas sobre cobrança? Fale com{" "}
          <a href={`mailto:${suporte}`} className="font-medium text-accent-ink hover:underline">{suporte}</a>.
        </p>
      )}
    </main>
  );
}
