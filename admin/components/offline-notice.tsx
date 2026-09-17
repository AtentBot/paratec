"use client";

import { AlertTriangle, Loader2, LogIn, WifiOff } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Causa = "verificando" | "offline" | "sessao" | "assinatura" | "erro";

/**
 * Exibido quando uma tela não conseguiu carregar seus dados — não inventamos
 * dados. As telas usam `tryApi`, que engole qualquer falha (rede, 401, 402,
 * 5xx); aqui descobrimos a causa real sondando /health e /auth/me, para não
 * culpar a conexão quando o problema é sessão expirada ou erro do backend.
 */
export function OfflineNotice({ base }: { base: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const [causa, setCausa] = useState<Causa>("verificando");

  useEffect(() => {
    let vivo = true;
    (async () => {
      // Atrás do proxy do Next, agente inalcançável vira 500 (não erro de rede):
      // só consideramos "no ar" se o /health responder o JSON esperado.
      const health = await fetch(`${base}/health`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
      if (!vivo) return;
      if (health?.status !== "ok") return setCausa("offline");

      const me = await fetch(`${base}/auth/me`, { cache: "no-store", credentials: "include" })
        .then(async (r) => ({ status: r.status, data: r.ok ? await r.json() : null }))
        .catch(() => null);
      if (!vivo) return;
      if (me?.status === 401) {
        setCausa("sessao");
        router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      } else if (me?.data && !me.data.is_staff && !me.data.assinatura?.ativa) {
        setCausa("assinatura");
      } else {
        setCausa("erro");
      }
    })();
    return () => {
      vivo = false;
    };
  }, [base, router, pathname]);

  if (causa === "verificando") {
    return (
      <Aviso tom="muted" icone={<Loader2 size={14} className="shrink-0 animate-spin" />}>
        Não foi possível carregar os dados. Verificando o motivo…
      </Aviso>
    );
  }
  if (causa === "offline") {
    return (
      <Aviso icone={<WifiOff size={14} className="shrink-0" />}>
        Sem conexão com o agent-service ({base}). Suba o backend para ver os dados.
      </Aviso>
    );
  }
  if (causa === "sessao") {
    return (
      <Aviso icone={<LogIn size={14} className="shrink-0" />}>
        Sua sessão expirou. Redirecionando para o login…
      </Aviso>
    );
  }
  // Backend devolve 402: o AccountGate já avisa/redireciona sobre a assinatura
  // inativa — repetir aqui só polui a tela.
  if (causa === "assinatura") return null;
  return (
    <Aviso icone={<AlertTriangle size={14} className="shrink-0" />}>
      O agent-service está no ar, mas respondeu com erro ao carregar esta tela.
      Recarregue a página; se persistir, verifique os logs do backend.
    </Aviso>
  );
}

function Aviso({ icone, tom = "danger", children }: {
  icone: React.ReactNode; tom?: "danger" | "muted"; children: React.ReactNode;
}) {
  const cores = tom === "danger"
    ? "border-danger/40 bg-danger/5 text-danger"
    : "bg-surface-2 text-muted";
  return (
    <div className={`flex items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-xs ${cores}`}>
      {icone}
      <span>{children}</span>
    </div>
  );
}

/** Estado vazio genérico (backend online, porém ainda sem registros). */
export function VazioNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed bg-surface-2 px-3 py-2 text-xs text-muted">
      {children}
    </div>
  );
}
