"use client";

import { api } from "@/lib/api";
import { CheckCircle2, Loader2, MessageCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/** 5511987654321 → +55 (11) 98765-4321 */
function formatarWhatsapp(n: string | null): string {
  if (!n) return "—";
  const m = n.match(/^55(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `+55 (${m[1]}) ${m[2]}-${m[3]}` : `+${n}`;
}

const input =
  "rounded-lg border bg-surface px-3 py-2.5 text-ink outline-none focus:ring-2 focus:ring-accent/40";

// Etapa 2 do onboarding: confirmar o WhatsApp com um código de 6 dígitos.
// Depois segue para o checkout do plano escolhido ou para a escolha de plano.
export default function VerificarWhatsappPage() {
  const router = useRouter();
  const [numero, setNumero] = useState<string | null>(null);
  const [trocando, setTrocando] = useState(false);
  const [novoNumero, setNovoNumero] = useState("");
  const [enviado, setEnviado] = useState(false);
  const [codigo, setCodigo] = useState("");
  const [espera, setEspera] = useState(0);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  async function seguir() {
    const plano = new URLSearchParams(window.location.search).get("plano");
    if (plano) {
      try {
        const { url } = await api.checkout(plano);
        window.location.href = url;
        return;
      } catch {
        /* cai na escolha de plano */
      }
    }
    router.replace("/ativar");
  }

  useEffect(() => {
    api
      .me()
      .then((m) => {
        if (m.is_staff || m.assinatura.ativa) return router.replace("/painel");
        if (m.verificacoes.whatsapp) return seguir();
        setNumero(m.whatsapp);
        if (!m.whatsapp) setTrocando(true);
      })
      .catch(() => router.replace("/login?next=/verificar-whatsapp"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (espera <= 0) return;
    const id = setTimeout(() => setEspera((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [espera]);

  async function enviar() {
    setOcupado(true);
    setErro(null);
    try {
      const r = await api.whatsappEnviarCodigo(trocando ? novoNumero : undefined);
      setNumero(r.whatsapp);
      setTrocando(false);
      setEnviado(true);
      setCodigo("");
      setEspera(60);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível enviar o código.");
    }
    setOcupado(false);
  }

  async function confirmar(e: React.FormEvent) {
    e.preventDefault();
    setOcupado(true);
    setErro(null);
    try {
      await api.whatsappVerificar(codigo);
      setOk(true);
      await seguir();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Código incorreto.");
      setOcupado(false);
    }
  }

  if (ok) {
    return (
      <div className="mx-auto flex w-full max-w-md flex-col items-center px-6 py-24 text-center">
        <CheckCircle2 size={48} className="text-success" />
        <h1 className="mt-4 text-2xl font-bold text-ink">WhatsApp confirmado!</h1>
        <p className="mt-2 text-muted">Agora escolha seu plano…</p>
      </div>
    );
  }

  if (numero === null && !trocando) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-muted">
        <Loader2 size={16} className="animate-spin" /> Carregando…
      </div>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-md flex-col px-6 py-16">
      <MessageCircle size={40} className="text-accent-ink" />
      <h1 className="mt-3 text-2xl font-bold tracking-tight text-ink">Confirme seu WhatsApp</h1>
      <p className="mt-1 text-sm text-muted">
        O WhatsApp é o canal principal do AtentBot com você. Enviaremos um código de 6 dígitos.
      </p>

      <div className="mt-8 flex flex-col gap-4">
        {trocando ? (
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-ink">Número do WhatsApp</span>
            <input
              type="tel" inputMode="tel" autoComplete="tel" value={novoNumero}
              onChange={(e) => setNovoNumero(e.target.value)}
              className={input} placeholder="(11) 98765-4321"
            />
          </label>
        ) : (
          <div className="flex items-center justify-between rounded-lg border bg-surface px-3 py-2.5 text-sm">
            <span className="font-medium text-ink">{formatarWhatsapp(numero)}</span>
            <button
              type="button" onClick={() => { setTrocando(true); setEnviado(false); }}
              className="text-xs font-semibold text-accent-ink hover:underline"
            >
              Trocar número
            </button>
          </div>
        )}

        <button
          type="button" onClick={enviar}
          disabled={ocupado || espera > 0 || (trocando && !novoNumero)}
          className={
            "rounded-xl px-4 py-2.5 text-sm font-semibold transition disabled:opacity-60 " +
            (enviado ? "border bg-surface text-ink hover:bg-surface-2" : "bg-feature text-feature-fg hover:opacity-90")
          }
        >
          {espera > 0 ? `Reenviar em ${espera}s` : enviado ? "Reenviar código" : "Enviar código"}
        </button>

        {enviado && (
          <form onSubmit={confirmar} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium text-ink">Código recebido</span>
              <input
                required inputMode="numeric" autoComplete="one-time-code" maxLength={7}
                value={codigo} onChange={(e) => setCodigo(e.target.value)}
                className={input + " text-center text-lg tracking-[0.4em]"} placeholder="000000"
              />
            </label>
            <button
              type="submit" disabled={ocupado || codigo.replace(/\D/g, "").length !== 6}
              className="rounded-xl bg-feature px-4 py-2.5 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-60"
            >
              {ocupado ? "Confirmando…" : "Confirmar"}
            </button>
          </form>
        )}

        {erro && <p className="text-sm text-danger">{erro}</p>}
      </div>
    </main>
  );
}
