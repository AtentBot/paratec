"use client";

import { Badge, Card, EmptyState } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { WhatsappConfig, WhatsappEstado, WhatsappInstancia, WhatsappQrCode } from "@/lib/types";
import {
  CheckCircle2,
  Loader2,
  Plus,
  Power,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Trash2,
  TriangleAlert,
  WifiOff,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

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

type QrView = { nome: string; qrcode: WhatsappQrCode; conectado: boolean };

export default function ConfiguracoesPage() {
  const [config, setConfig] = useState<WhatsappConfig | null>(null);
  const [lista, setLista] = useState<WhatsappInstancia[]>([]);
  const [offline, setOffline] = useState(false);
  const [carregando, setCarregando] = useState(true);

  // Formulário de novo número.
  const [formAberto, setFormAberto] = useState(false);
  const [nome, setNome] = useState("");
  const [criando, setCriando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Painel do QR Code (fluxo de pareamento).
  const [qr, setQr] = useState<QrView | null>(null);

  const carregar = useCallback(async () => {
    try {
      const cfg = await api.whatsappConfig();
      setConfig(cfg);
      setLista(cfg.configurado ? await api.whatsappInstancias() : []);
      setOffline(false);
    } catch {
      setOffline(true);
      setConfig(null);
      setLista([]);
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // Enquanto o QR está aberto e ainda não pareou, verifica o status a cada 3s.
  // Assim que a Evolution reporta "conectado", encerra o polling e recarrega.
  const qrNome = qr && !qr.conectado ? qr.nome : null;
  useEffect(() => {
    if (!qrNome) return;
    const id = setInterval(async () => {
      try {
        const st = await api.whatsappStatus(qrNome);
        if (st.estado === "conectado") {
          setQr((v) => (v && v.nome === qrNome ? { ...v, conectado: true } : v));
          carregar();
        }
      } catch {
        /* mantém o QR; a próxima iteração tenta de novo */
      }
    }, 3000);
    return () => clearInterval(id);
  }, [qrNome, carregar]);

  async function criar() {
    setCriando(true);
    setErro(null);
    try {
      const r = await api.whatsappCriar(nome);
      setFormAberto(false);
      setNome("");
      setQr({ nome: r.nome, qrcode: r.qrcode, conectado: false });
      carregar();
    } catch (e) {
      setErro(
        e instanceof Error && /422/.test(e.message)
          ? "Nome inválido: use de 2 a 40 caracteres (letras, números, - ou _)."
          : "Não foi possível criar a conexão. Verifique se o serviço está no ar.",
      );
    } finally {
      setCriando(false);
    }
  }

  async function renovarQr(inst: WhatsappInstancia) {
    try {
      const r = await api.whatsappQrcode(inst.nome);
      setQr({ nome: inst.nome, qrcode: r.qrcode, conectado: false });
    } catch {
      setErro("Não foi possível gerar o QR Code agora. Tente novamente.");
    }
  }

  async function desconectar(inst: WhatsappInstancia) {
    if (!confirm(`Desconectar o WhatsApp da conexão "${inst.nome}"?`)) return;
    setLista((l) =>
      l.map((x) => (x.nome === inst.nome ? { ...x, estado: "desconectado", numero: null } : x)),
    );
    try {
      await api.whatsappDesconectar(inst.nome);
    } finally {
      carregar();
    }
  }

  async function remover(inst: WhatsappInstancia) {
    if (!confirm(`Remover a conexão "${inst.nome}" da Evolution? Esta ação não pode ser desfeita.`))
      return;
    setLista((l) => l.filter((x) => x.nome !== inst.nome));
    if (qr?.nome === inst.nome) setQr(null);
    try {
      await api.whatsappRemover(inst.nome);
    } finally {
      carregar();
    }
  }

  const naoConfigurado = config != null && !config.configurado;
  const podeCriar = nome.trim().length >= 2;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      {/* Explicação da seção */}
      <Card className="flex items-start gap-3 p-4">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink">
          <ShieldCheck size={16} />
        </span>
        <div className="text-xs leading-relaxed text-muted">
          <p>
            Conecte um <strong className="text-ink">novo número de WhatsApp</strong> escaneando um QR
            Code — sem precisar acessar a Evolution. O painel fala com a Evolution por um canal
            interno seguro; a chave de acesso nunca sai do servidor.
          </p>
          {config?.webhook_automatico === false && config?.configurado && (
            <p className="mt-2 flex items-start gap-1.5 text-warning">
              <TriangleAlert size={13} className="mt-0.5 shrink-0" />
              O roteamento das mensagens ao assistente (webhook) não é automático nesta instalação —
              conecte o número aqui e peça ao time técnico para apontar o webhook ao fluxo do agente.
            </p>
          )}
        </div>
      </Card>

      {/* Evolution não configurada no backend */}
      {naoConfigurado && (
        <Card>
          <EmptyState
            icon={<WifiOff size={28} />}
            title="Integração de WhatsApp não configurada"
            hint="Defina EVOLUTION_API_URL e EVOLUTION_API_KEY no agent-service para habilitar a conexão de números por aqui."
          />
        </Card>
      )}

      {config?.configurado && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-ink">Conexões de WhatsApp</h2>
            <button
              onClick={() => {
                setFormAberto((v) => !v);
                setErro(null);
              }}
              className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-ink transition hover:opacity-90"
            >
              <Plus size={14} /> Conectar novo número
            </button>
          </div>

          {/* Form: nome da conexão */}
          {formAberto && (
            <Card className="p-5">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink">Nova conexão</h3>
                <button
                  onClick={() => setFormAberto(false)}
                  className="text-faint transition hover:text-ink"
                >
                  <X size={16} />
                </button>
              </div>
              <label className="flex flex-col gap-1.5">
                <span className="text-[11px] font-medium text-muted">
                  Identificador da conexão (só letras, números, - ou _)
                </span>
                <input
                  autoFocus
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && podeCriar && !criando && criar()}
                  placeholder="Ex.: paratec-comercial"
                  className={inputCls}
                />
                <span className="text-[11px] text-faint">
                  Use um nome curto para identificar este número (ex.: setor ou filial).
                </span>
              </label>
              {erro && <p className="mt-3 text-xs text-danger">{erro}</p>}
              <div className="mt-4 flex items-center gap-2">
                <button
                  disabled={!podeCriar || criando}
                  onClick={criar}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-xs font-medium text-accent-ink transition hover:opacity-90 disabled:opacity-40"
                >
                  {criando ? <Loader2 size={14} className="animate-spin" /> : <QrCode size={14} />}
                  Gerar QR Code
                </button>
                <button
                  onClick={() => setFormAberto(false)}
                  className="rounded-lg border px-3.5 py-2 text-xs font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
                >
                  Cancelar
                </button>
              </div>
            </Card>
          )}

          {/* Painel do QR Code */}
          {qr && (
            <QrPanel
              qr={qr}
              onFechar={() => setQr(null)}
              onRenovar={() => renovarQr({ nome: qr.nome } as WhatsappInstancia)}
            />
          )}

          {/* Lista de conexões */}
          {carregando ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-36 animate-pulse rounded-2xl border bg-surface-2" />
              ))}
            </div>
          ) : lista.length === 0 ? (
            <Card>
              <EmptyState
                icon={<Smartphone size={28} />}
                title="Nenhum número conectado"
                hint='Clique em "Conectar novo número" para parear um WhatsApp lendo o QR Code.'
              />
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {lista.map((inst) => (
                <Card key={inst.nome} className="p-4">
                  <div className="flex items-start gap-3">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-ink">
                      <Smartphone size={18} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-semibold text-ink">{inst.nome}</p>
                        <Badge tone={ESTADO_TONE[inst.estado]} dot>
                          {ESTADO_LABEL[inst.estado]}
                        </Badge>
                      </div>
                      <p className="mt-0.5 truncate text-[11px] text-faint">
                        {inst.numero ? `+${inst.numero}` : "sem número pareado"}
                        {inst.perfil ? ` · ${inst.perfil}` : ""}
                      </p>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t pt-3">
                    {inst.estado !== "conectado" ? (
                      <button
                        onClick={() => renovarQr(inst)}
                        className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-accent-ink transition hover:bg-accent-soft"
                      >
                        <QrCode size={12} /> Ver QR Code
                      </button>
                    ) : (
                      <button
                        onClick={() => desconectar(inst)}
                        className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
                      >
                        <Power size={12} /> Desconectar
                      </button>
                    )}
                    <button
                      onClick={() => remover(inst)}
                      className="ml-auto inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-muted transition hover:bg-danger/10 hover:text-danger"
                    >
                      <Trash2 size={12} /> Remover
                    </button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function QrPanel({
  qr,
  onFechar,
  onRenovar,
}: {
  qr: QrView;
  onFechar: () => void;
  onRenovar: () => void;
}) {
  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">
          Conectar <span className="font-mono text-accent-ink">{qr.nome}</span>
        </h3>
        <button onClick={onFechar} className="text-faint transition hover:text-ink">
          <X size={16} />
        </button>
      </div>

      {qr.conectado ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <CheckCircle2 size={40} className="text-success" />
          <p className="text-sm font-semibold text-ink">Número conectado com sucesso!</p>
          <p className="max-w-xs text-xs text-muted">
            O WhatsApp já está sincronizado com a Evolution e pronto para uso.
          </p>
          <button
            onClick={onFechar}
            className="mt-2 rounded-lg bg-accent px-3.5 py-2 text-xs font-medium text-accent-ink transition hover:opacity-90"
          >
            Concluir
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-4 md:flex-row md:items-start">
          <div className="grid h-52 w-52 shrink-0 place-items-center rounded-xl border bg-white p-2">
            {qr.qrcode.base64 ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={qr.qrcode.base64} alt="QR Code de conexão" className="h-full w-full" />
            ) : (
              <div className="flex flex-col items-center gap-2 text-faint">
                <Loader2 size={22} className="animate-spin" />
                <span className="text-[11px]">gerando QR…</span>
              </div>
            )}
          </div>
          <div className="flex-1 text-xs leading-relaxed text-muted">
            <p className="mb-2 flex items-center gap-1.5 font-medium text-ink">
              <Loader2 size={13} className="animate-spin text-warning" />
              Aguardando leitura…
            </p>
            <ol className="ml-4 list-decimal space-y-1.5">
              <li>Abra o WhatsApp no celular do número que quer conectar.</li>
              <li>
                Toque em <strong className="text-ink">Aparelhos conectados</strong> →{" "}
                <strong className="text-ink">Conectar um aparelho</strong>.
              </li>
              <li>Aponte a câmera para este QR Code.</li>
            </ol>
            {qr.qrcode.pairing_code && (
              <p className="mt-3">
                Ou use o código de pareamento:{" "}
                <code className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-ink ring-1 ring-inset ring-border">
                  {qr.qrcode.pairing_code}
                </code>
              </p>
            )}
            <button
              onClick={onRenovar}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
            >
              <RefreshCw size={12} /> Gerar novo QR Code
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}

const inputCls =
  "w-full rounded-lg border bg-surface px-3 py-2 text-sm text-ink outline-none transition placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/20";
