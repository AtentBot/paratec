"use client";

import { api } from "@/lib/api";
import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ReenviarVerificacao } from "../_components/reenviar-verificacao";

export default function CadastroPage() {
  const [enviadoPara, setEnviadoPara] = useState<string | null>(null);
  const [empresa, setEmpresa] = useState("");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
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
      // Plano escolhido na landing (?plano=) segue no link do e-mail → checkout.
      const plano = new URLSearchParams(window.location.search).get("plano") || undefined;
      const r = await api.signup({ empresa, email, senha, whatsapp, nome: nome || undefined, plano });
      setEnviadoPara(r.email);
      setCarregando(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      setErro(
        msg.includes("409") ? "Já existe uma conta com este e-mail."
          : msg.includes("400") ? "Verifique os dados: e-mail válido, WhatsApp com DDD e senha de 8+ caracteres."
          : "Não foi possível criar a conta. Tente novamente.",
      );
      setCarregando(false);
    }
  }

  if (enviadoPara) {
    const plano = new URLSearchParams(window.location.search).get("plano");
    return (
      <div className="mx-auto flex w-full max-w-md flex-col items-center px-6 py-20 text-center">
        <MailCheck size={48} className="text-accent-ink" />
        <h1 className="mt-4 text-2xl font-bold tracking-tight text-ink">Confirme seu e-mail</h1>
        <p className="mt-2 text-muted">
          Enviamos um link de confirmação para <span className="font-medium text-ink">{enviadoPara}</span>.
          Abra o e-mail e clique no link para continuar: em seguida você valida seu WhatsApp,
          escolhe o plano e cadastra o cartão para liberar o painel.
        </p>
        <div className="mt-6">
          <ReenviarVerificacao email={enviadoPara} plano={plano} />
        </div>
        <p className="mt-6 text-sm text-muted">
          Já confirmou?{" "}
          <Link href="/login" className="font-semibold text-accent-ink hover:underline">Entrar</Link>
        </p>
      </div>
    );
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
          <span className="font-medium text-ink">WhatsApp</span>
          <input
            type="tel" required inputMode="tel" autoComplete="tel" value={whatsapp}
            onChange={(e) => setWhatsapp(e.target.value)}
            className="rounded-lg border bg-surface px-3 py-2.5 text-ink outline-none focus:ring-2 focus:ring-accent/40"
            placeholder="(11) 98765-4321"
          />
          <span className="text-xs text-faint">Vamos enviar um código para confirmar este número.</span>
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
