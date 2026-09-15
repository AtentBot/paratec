"use client";

import { api } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function CadastroPage() {
  const router = useRouter();
  const [empresa, setEmpresa] = useState("");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [aceite, setAceite] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!aceite) {
      setErro("É preciso aceitar as Regras de Cobrança e a Confidencialidade.");
      return;
    }
    setErro(null);
    setCarregando(true);
    try {
      await api.signup({ empresa, email, senha, nome: nome || undefined });
      // Se veio de um plano (?plano=), já manda pro checkout; senão, pro painel.
      const plano = new URLSearchParams(window.location.search).get("plano");
      if (plano) {
        try {
          const { url } = await api.checkout(plano);
          window.location.href = url;
          return;
        } catch {
          router.push("/assinatura");
          return;
        }
      }
      router.push("/painel");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      setErro(
        msg.includes("409") ? "Já existe uma conta com este e-mail."
          : msg.includes("400") ? "Verifique os dados: e-mail válido e senha de 8+ caracteres."
          : "Não foi possível criar a conta. Tente novamente.",
      );
      setCarregando(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-md flex-col px-6 py-16">
      <h1 className="text-2xl font-bold tracking-tight text-ink">Criar conta</h1>
      <p className="mt-1 text-sm text-muted">Comece a atender no WhatsApp com IA.</p>

      <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-ink">Nome da empresa</span>
          <input
            required value={empresa} onChange={(e) => setEmpresa(e.target.value)}
            className="rounded-lg border bg-surface px-3 py-2.5 text-ink outline-none focus:ring-2 focus:ring-accent/40"
            placeholder="Minha Distribuidora Ltda"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-ink">Seu nome</span>
          <input
            value={nome} onChange={(e) => setNome(e.target.value)}
            className="rounded-lg border bg-surface px-3 py-2.5 text-ink outline-none focus:ring-2 focus:ring-accent/40"
            placeholder="Como podemos te chamar"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-ink">E-mail</span>
          <input
            type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="rounded-lg border bg-surface px-3 py-2.5 text-ink outline-none focus:ring-2 focus:ring-accent/40"
            placeholder="voce@empresa.com"
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-ink">Senha</span>
          <input
            type="password" required minLength={8} value={senha} onChange={(e) => setSenha(e.target.value)}
            className="rounded-lg border bg-surface px-3 py-2.5 text-ink outline-none focus:ring-2 focus:ring-accent/40"
            placeholder="Ao menos 8 caracteres"
          />
        </label>

        <label className="flex items-start gap-2 text-xs text-muted">
          <input
            type="checkbox"
            checked={aceite}
            onChange={(e) => setAceite(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-[color:var(--accent)]"
          />
          <span>
            Li e aceito as{" "}
            <Link href="/cobranca" target="_blank" className="font-medium text-accent-ink hover:underline">Regras de Cobrança</Link>{" "}
            (mensalidade + consumo) e os{" "}
            <Link href="/confidencialidade" target="_blank" className="font-medium text-accent-ink hover:underline">Termos de Confidencialidade</Link>.
          </span>
        </label>

        {erro && <p className="text-sm text-danger">{erro}</p>}

        <button
          type="submit" disabled={carregando || !aceite}
          className="mt-2 rounded-xl bg-feature px-4 py-2.5 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-60"
        >
          {carregando ? "Criando…" : "Criar conta"}
        </button>
      </form>

      <p className="mt-6 text-sm text-muted">
        Já tem conta?{" "}
        <Link href="/login" className="font-semibold text-accent-ink hover:underline">Entrar</Link>
      </p>
    </div>
  );
}
