"use client";

import { api } from "@/lib/api";
import { useState } from "react";

/** Botão "reenviar e-mail de confirmação" (com limite por hora no backend). */
export function ReenviarVerificacao({ email, plano }: { email: string; plano?: string | null }) {
  const [estado, setEstado] = useState<"idle" | "enviando" | "enviado" | "limite" | "erro">("idle");

  async function reenviar() {
    setEstado("enviando");
    try {
      await api.reenviarVerificacao(email, plano || undefined);
      setEstado("enviado");
    } catch (e) {
      setEstado(e instanceof Error && e.message.includes("429") ? "limite" : "erro");
    }
  }

  return (
    <div className="flex flex-col items-center gap-2 text-sm">
      <button
        type="button"
        onClick={reenviar}
        disabled={estado === "enviando" || !email}
        className="rounded-xl border bg-surface px-4 py-2 font-semibold text-ink transition hover:bg-surface-2 disabled:opacity-60"
      >
        {estado === "enviando" ? "Reenviando…" : "Reenviar e-mail"}
      </button>
      {estado === "enviado" && <p className="text-success">E-mail reenviado. Confira também o spam.</p>}
      {estado === "limite" && <p className="text-danger">Muitos reenvios. Tente de novo em uma hora.</p>}
      {estado === "erro" && <p className="text-danger">Não foi possível reenviar agora.</p>}
    </div>
  );
}
