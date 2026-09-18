"use client";

import { api } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ReenviarVerificacao } from "../_components/reenviar-verificacao";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [naoVerificado, setNaoVerificado] = useState(false);
  const [carregando, setCarregando] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setNaoVerificado(false);
    setCarregando(true);
    try {
      await api.login(email, senha);
      const next = new URLSearchParams(window.location.search).get("next");
      router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/painel");
    } catch (e) {
      if (e instanceof Error && e.message.includes("403")) {
        setNaoVerificado(true);
        setErro("Confirme seu e-mail antes de entrar. Procure o link que enviamos no cadastro.");
      } else {
        setErro("E-mail ou senha inválidos.");
      }
      setCarregando(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-md flex-col px-6 py-16">
      <h1 className="text-2xl font-bold tracking-tight text-ink">Entrar</h1>
      <p className="mt-1 text-sm text-muted">Acesse o painel do seu atendimento.</p>

      <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
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
            type="password" required value={senha} onChange={(e) => setSenha(e.target.value)}
            className="rounded-lg border bg-surface px-3 py-2.5 text-ink outline-none focus:ring-2 focus:ring-accent/40"
            placeholder="••••••••"
          />
        </label>

        {erro && <p className="text-sm text-danger">{erro}</p>}
        {naoVerificado && <ReenviarVerificacao email={email} />}

        <button
          type="submit" disabled={carregando}
          className="mt-2 rounded-xl bg-feature px-4 py-2.5 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-60"
        >
          {carregando ? "Entrando…" : "Entrar"}
        </button>
      </form>

      <p className="mt-6 text-sm text-muted">
        Ainda não tem conta?{" "}
        <Link href="/cadastro" className="font-semibold text-accent-ink hover:underline">Criar conta</Link>
      </p>
    </div>
  );
}
