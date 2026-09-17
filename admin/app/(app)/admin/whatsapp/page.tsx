"use client";

import { Carregando } from "@/components/admin-ui";
import { Restrito } from "@/components/restrito";
import { Badge, Card } from "@/components/ui";
import { QrPanel, type QrView } from "@/components/whatsapp-qr-panel";
import { api } from "@/lib/api";
import type { AdminWhatsappVerificacao, WhatsappEstado } from "@/lib/types";
import { AlertTriangle, Power, QrCode, Send, Smartphone, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const ESTADO_TONE: Record<WhatsappEstado, "success" | "warning" | "neutral"> = {
  conectado: "success",
  conectando: "warning",
  desconectado: "neutral",
};
const ESTADO_LABEL: Record<WhatsappEstado, string> = {
  conectado: "Conectado",
  conectando: "Aguardando leitura",
  desconectado: "Desconectado",
};

const inputCls =
  "w-full rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none transition placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/20";
const btnCls =
  "inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium text-ink transition hover:bg-surface-2 disabled:opacity-60";

function formatarNumero(n: string | null): string {
  if (!n) return "—";
  const m = n.match(/^55(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `+55 (${m[1]}) ${m[2]}-${m[3]}` : `+${n}`;
}

// Número DA PLATAFORMA que envia os códigos de verificação do cadastro.
// Sincronizado por QR Code; não tem webhook (respostas não vão a nenhum agente).
export default function AdminWhatsappVerificacaoPage() {
  const [dados, setDados] = useState<AdminWhatsappVerificacao | null>(null);
  const [restrito, setRestrito] = useState(false);
  const [nome, setNome] = useState("atentbot-verificacao");
  const [qr, setQr] = useState<QrView | null>(null);
  const [teste, setTeste] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);

  const carregar = useCallback(async () => {
    try {
      setDados(await api.adminWaVerificacao());
    } catch {
      setRestrito(true);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // Enquanto o QR está aberto e não pareou, consulta o status a cada 3s.
  const aguardando = qr && !qr.conectado;
  useEffect(() => {
    if (!aguardando) return;
    const id = setInterval(async () => {
      try {
        const st = await api.adminWaVerificacaoStatus();
        if (st.estado === "conectado") {
          setQr((v) => (v ? { ...v, conectado: true } : v));
          carregar();
        }
      } catch {
        /* tenta de novo */
      }
    }, 3000);
    return () => clearInterval(id);
  }, [aguardando, carregar]);

  async function executar(fn: () => Promise<void>) {
    setOcupado(true);
    setAviso(null);
    try {
      await fn();
    } catch (e) {
      setAviso({ tipo: "erro", texto: e instanceof Error ? e.message : "Operação falhou." });
    }
    setOcupado(false);
  }

  const sincronizar = () =>
    executar(async () => {
      const r = await api.adminWaVerificacaoSincronizar(nome);
      setQr({ nome: r.nome, qrcode: r.qrcode, conectado: false });
      await carregar();
    });

  const novoQr = () =>
    executar(async () => {
      const r = await api.adminWaVerificacaoQrcode();
      setQr({ nome: r.nome, qrcode: r.qrcode, conectado: false });
    });

  const enviarTeste = () =>
    executar(async () => {
      const r = await api.adminWaVerificacaoTeste(teste);
      setAviso({ tipo: "ok", texto: `Mensagem de teste enviada para ${formatarNumero(r.whatsapp)}.` });
    });

  const desconectar = () => {
    if (!confirm("Desconectar o número? Novos cadastros não conseguirão validar o WhatsApp até sincronizar de novo.")) return;
    executar(async () => {
      await api.adminWaVerificacaoDesconectar();
      await carregar();
    });
  };

  const remover = () => {
    if (!confirm("Remover a instância da Evolution? Novos cadastros ficam sem verificação de WhatsApp até configurar outro número.")) return;
    executar(async () => {
      await api.adminWaVerificacaoRemover();
      setQr(null);
      await carregar();
    });
  };

  if (restrito) return <Restrito />;
  if (!dados) return <Carregando />;

  const conectado = dados.estado === "conectado";

  return (
    <div className="flex max-w-3xl flex-col gap-5 animate-fade-in">
      <div>
        <h2 className="text-lg font-semibold text-ink">WhatsApp de verificação</h2>
        <p className="mt-1 text-sm text-muted">
          Número do AtentBot que envia o código de confirmação para quem cria conta. Use um número
          exclusivo da plataforma, nunca o de um cliente.
        </p>
      </div>

      {!dados.evolution_configurada && (
        <p className="flex items-center gap-2 rounded-xl border bg-warning/10 px-4 py-3 text-sm text-warning">
          <AlertTriangle size={16} /> Evolution API não configurada no servidor.
        </p>
      )}
      {dados.evolution_configurada && !conectado && (
        <p className="flex items-center gap-2 rounded-xl border bg-danger/10 px-4 py-3 text-sm text-danger">
          <AlertTriangle size={16} />
          Sem número conectado: novos cadastros não conseguem validar o WhatsApp e ficam travados.
        </p>
      )}
      {aviso && (
        <p className={"rounded-xl border px-4 py-3 text-sm " + (aviso.tipo === "ok" ? "bg-surface-2 text-ink" : "bg-danger/10 text-danger")}>
          {aviso.texto}
        </p>
      )}

      {dados.instancia ? (
        <Card className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-surface-2 text-accent-ink">
                <Smartphone size={18} />
              </div>
              <div>
                <p className="font-mono text-sm font-semibold text-ink">{dados.instancia}</p>
                <p className="text-xs text-muted">
                  {formatarNumero(dados.numero)}
                  {dados.perfil ? ` · ${dados.perfil}` : ""}
                  {dados.origem === "ambiente" ? " · definido por variável de ambiente" : ""}
                </p>
              </div>
            </div>
            {dados.estado && <Badge tone={ESTADO_TONE[dados.estado]}>{ESTADO_LABEL[dados.estado]}</Badge>}
          </div>
          {dados.erro && <p className="mt-3 text-xs text-danger">{dados.erro}</p>}

          <div className="mt-4 flex flex-wrap gap-2">
            {!conectado && (
              <button onClick={novoQr} disabled={ocupado} className={btnCls}>
                <QrCode size={13} /> Gerar QR Code
              </button>
            )}
            {conectado && (
              <button onClick={desconectar} disabled={ocupado} className={btnCls}>
                <Power size={13} /> Desconectar
              </button>
            )}
            {dados.origem === "painel" && (
              <button onClick={remover} disabled={ocupado} className={btnCls + " hover:text-danger"}>
                <Trash2 size={13} /> Remover
              </button>
            )}
          </div>

          {conectado && (
            <div className="mt-5 border-t pt-4">
              <p className="mb-2 text-xs font-medium text-ink">Enviar mensagem de teste</p>
              <div className="flex gap-2">
                <input value={teste} onChange={(e) => setTeste(e.target.value)} type="tel"
                  placeholder="(11) 98765-4321" className={inputCls} />
                <button onClick={enviarTeste} disabled={ocupado || !teste} className={btnCls + " shrink-0"}>
                  <Send size={13} /> Enviar
                </button>
              </div>
            </div>
          )}
        </Card>
      ) : (
        <Card className="p-5">
          <p className="text-sm font-medium text-ink">Sincronizar um número</p>
          <p className="mt-1 text-xs text-muted">
            Dê um nome à conexão e leia o QR Code com o WhatsApp do número da plataforma.
          </p>
          <div className="mt-3 flex gap-2">
            <input value={nome} onChange={(e) => setNome(e.target.value)} className={inputCls}
              placeholder="atentbot-verificacao" />
            <button onClick={sincronizar} disabled={ocupado || !nome || !dados.evolution_configurada}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-feature px-3.5 py-2 text-xs font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-60">
              <QrCode size={13} /> Sincronizar
            </button>
          </div>
        </Card>
      )}

      {qr && <QrPanel qr={qr} onFechar={() => setQr(null)} onRenovar={novoQr} />}
    </div>
  );
}
