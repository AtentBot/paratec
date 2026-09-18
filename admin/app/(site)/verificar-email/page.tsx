"use client";

import { api } from "@/lib/api";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

// Destino do link enviado no cadastro. Confirma o e-mail (abre a sessão) e
// segue para a verificação do WhatsApp.
export default function VerificarEmailPage() {
  const router = useRouter();
  const [estado, setEstado] = useState<"verificando" | "ok" | "invalido">("verificando");
  const feito = useRef(false);

  useEffect(() => {
    if (feito.current) return; // token é de uso único: não repetir no StrictMode
    feito.current = true;
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const plano = params.get("plano");
    if (!token) {
      setEstado("invalido");
      return;
    }
    api
      .verificarEmail(token)
      .then(() => {
        setEstado("ok");
        // Próxima etapa: validar o WhatsApp (o plano escolhido segue junto).
        router.replace(`/verificar-whatsapp${plano ? `?plano=${encodeURIComponent(plano)}` : ""}`);
      })
      .catch(() => setEstado("invalido"));
  }, [router]);

  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center px-6 py-24 text-center">
      {estado === "verificando" && (
        <>
          <Loader2 size={48} className="animate-spin text-accent-ink" />
          <h1 className="mt-4 text-2xl font-bold text-ink">Confirmando seu e-mail…</h1>
        </>
      )}
      {estado === "ok" && (
        <>
          <CheckCircle2 size={48} className="text-success" />
          <h1 className="mt-4 text-2xl font-bold text-ink">E-mail confirmado!</h1>
          <p className="mt-2 text-muted">Agora vamos validar seu WhatsApp…</p>
        </>
      )}
      {estado === "invalido" && (
        <>
          <XCircle size={48} className="text-danger" />
          <h1 className="mt-4 text-2xl font-bold text-ink">Link inválido ou expirado</h1>
          <p className="mt-2 text-muted">
            Esse link já foi usado ou venceu. Entre com seu e-mail e senha para receber um novo.
          </p>
          <Link
            href="/login"
            className="mt-6 rounded-xl bg-feature px-5 py-3 text-sm font-semibold text-feature-fg transition hover:opacity-90"
          >
            Ir para o login
          </Link>
        </>
      )}
    </div>
  );
}
