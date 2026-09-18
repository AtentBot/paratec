"use client";

import { api } from "@/lib/api";
import { Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Parede do painel: nada do painel é renderizado até confirmar, no backend,
 * que há sessão válida E assinatura ativa. Sem sessão → /login; WhatsApp não
 * verificado → /verificar-whatsapp; sem plano ativo → /ativar (plano + cartão).
 * Staff da plataforma passa.
 * O backend continua barrando por conta própria (401/402) — isto evita que o
 * usuário sequer veja o painel sem pagar.
 */
export function AccountGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [liberado, setLiberado] = useState(false);

  useEffect(() => {
    let vivo = true;
    api
      .me()
      .then((m) => {
        if (!vivo) return;
        if (m.assinatura.ativa || m.is_staff) setLiberado(true);
        else if (!m.verificacoes.whatsapp) router.replace("/verificar-whatsapp");
        else router.replace("/ativar");
      })
      .catch(() => vivo && router.replace(`/login?next=${encodeURIComponent(pathname)}`));
    return () => {
      vivo = false;
    };
  }, [router, pathname]);

  if (!liberado) {
    return (
      <div className="flex min-h-dvh items-center justify-center gap-2 text-muted">
        <Loader2 size={16} className="animate-spin" /> Carregando…
      </div>
    );
  }
  return <>{children}</>;
}
