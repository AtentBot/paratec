"use client";

import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Verifica a sessão no cliente (rede de segurança além do middleware) e mostra
 * um aviso quando a assinatura NÃO está ativa — com atalho para /assinatura.
 * Se a sessão expirou (401), redireciona ao /login.
 */
export function AccountGate() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    let vivo = true;
    api
      .me()
      .then((m) => vivo && setMe(m))
      .catch(() => router.replace("/login"));
    return () => {
      vivo = false;
    };
  }, [router]);

  if (!me || me.assinatura.ativa) return null;

  return (
    <div className="mb-5 flex items-center gap-3 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm">
      <AlertTriangle size={18} className="shrink-0 text-warning" />
      <div className="flex-1">
        <p className="font-semibold text-ink">Assinatura inativa</p>
        <p className="text-muted">
          Seu acesso ao atendimento está limitado. Ative um plano para voltar a operar.
        </p>
      </div>
      <Link
        href="/assinatura"
        className="rounded-lg bg-feature px-3 py-2 text-xs font-semibold text-feature-fg"
      >
        Ver planos
      </Link>
    </div>
  );
}
