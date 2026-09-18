"use client";

import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

export default function ContaPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [conf, setConf] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);

  useEffect(() => {
    api.me().then(setMe).catch(() => {});
  }, []);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (nova.length < 8) return setMsg({ tipo: "erro", texto: "A nova senha deve ter ao menos 8 caracteres." });
    if (nova !== conf) return setMsg({ tipo: "erro", texto: "A confirmação não confere." });
    setBusy(true);
    try {
      await api.trocarSenha(atual, nova);
      setMsg({ tipo: "ok", texto: "Senha alterada com sucesso." });
      setAtual(""); setNova(""); setConf("");
    } catch (err) {
      const s = err instanceof Error ? err.message : "";
      setMsg({ tipo: "erro", texto: s.includes("401") ? "Senha atual incorreta." : "Não foi possível alterar a senha." });
    }
    setBusy(false);
  }

  return (
    <div className="flex max-w-lg flex-col gap-6 animate-fade-in">
      <section className="rounded-2xl border bg-surface p-6 shadow-card">
        <p className="text-xs font-semibold uppercase tracking-wider text-faint">Conta</p>
        <h2 className="mt-1 text-lg font-semibold text-ink">{me?.nome || me?.email || "—"}</h2>
        <p className="text-sm text-muted">{me?.email}</p>
        <p className="mt-2 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-muted">
            {me?.role === "owner" ? "Responsável" : "Atendente"} · {me?.tenant?.nome ?? "—"}
          </span>
          {me?.is_staff && (
            <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-accent-ink">
              <ShieldCheck size={11} /> Administração
            </span>
          )}
        </p>
      </section>

      <section className="rounded-2xl border bg-surface p-6 shadow-card">
        <h3 className="text-base font-semibold text-ink">Trocar senha</h3>
        <form onSubmit={salvar} className="mt-4 flex flex-col gap-3">
          <input type="password" value={atual} onChange={(e) => setAtual(e.target.value)}
            placeholder="Senha atual" autoComplete="current-password" required
            className="rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40" />
          <input type="password" value={nova} onChange={(e) => setNova(e.target.value)}
            placeholder="Nova senha (mín. 8)" autoComplete="new-password" required minLength={8}
            className="rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40" />
          <input type="password" value={conf} onChange={(e) => setConf(e.target.value)}
            placeholder="Confirmar nova senha" autoComplete="new-password" required
            className="rounded-lg border bg-surface px-3 py-2.5 text-sm text-ink outline-none focus:ring-2 focus:ring-accent/40" />
          {msg && <p className={"text-sm " + (msg.tipo === "ok" ? "text-success" : "text-danger")}>{msg.texto}</p>}
          <button type="submit" disabled={busy}
            className="mt-1 inline-flex w-fit items-center gap-2 rounded-xl bg-feature px-4 py-2.5 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-60">
            {busy && <Loader2 size={15} className="animate-spin" />} Salvar nova senha
          </button>
        </form>
      </section>
    </div>
  );
}
