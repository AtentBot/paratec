"use client";

import { api } from "@/lib/api";
import { CheckCircle2, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

// Após o checkout, a ativação real vem pelo webhook do Stripe (assíncrono).
// Aqui fazemos poll de /billing/status até ficar ativa e então vamos ao painel.
export default function CheckoutSucesso() {
  const router = useRouter();
  const [ativa, setAtiva] = useState(false);

  useEffect(() => {
    let tentativas = 0;
    const id = setInterval(async () => {
      tentativas++;
      try {
        const s = await api.assinaturaStatus();
        if (s.ativa) {
          setAtiva(true);
          clearInterval(id);
          setTimeout(() => router.push("/painel"), 1200);
        }
      } catch {
        /* ainda não */
      }
      if (tentativas > 20) clearInterval(id); // ~1 min
    }, 3000);
    return () => clearInterval(id);
  }, [router]);

  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center px-6 py-24 text-center">
      {ativa ? (
        <>
          <CheckCircle2 size={48} className="text-success" />
          <h1 className="mt-4 text-2xl font-bold text-ink">Assinatura ativa!</h1>
          <p className="mt-2 text-muted">Redirecionando para o seu painel…</p>
        </>
      ) : (
        <>
          <Loader2 size={48} className="animate-spin text-accent-ink" />
          <h1 className="mt-4 text-2xl font-bold text-ink">Confirmando o pagamento…</h1>
          <p className="mt-2 text-muted">
            Estamos ativando sua conta. Isso leva alguns segundos.
          </p>
        </>
      )}
    </div>
  );
}
