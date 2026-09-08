"use client";

import { Badge, Card, CardHeader, EmptyState } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativo } from "@/lib/format";
import type { Broadcast, Cliente } from "@/lib/types";
import {
  AlertTriangle,
  Image as ImageIcon,
  Megaphone,
  Search,
  Send,
  Target,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const SEGMENTOS = [
  { key: "todos", label: "Todos os ativos" },
  { key: "com_orcamento", label: "Com orçamento aberto" },
  { key: "novos", label: "Novos (30 dias)" },
  { key: "recentes", label: "Ativos recentemente" },
];

type Modo = "segmento" | "manual";

export default function PromocoesPage() {
  const [texto, setTexto] = useState("");
  const [imagem, setImagem] = useState<{ url: string; arquivo: string } | null>(null);
  const [subindoImg, setSubindoImg] = useState(false);
  const imgInputRef = useRef<HTMLInputElement>(null);

  const [modo, setModo] = useState<Modo>("segmento");
  const [segmento, setSegmento] = useState("todos");
  const [segmentos, setSegmentos] = useState<Record<string, number>>({});

  // Seleção manual de clientes.
  const [clientes, setClientes] = useState<Cliente[] | null>(null);
  const [busca, setBusca] = useState("");
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());

  const [enviando, setEnviando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [lista, setLista] = useState<Broadcast[]>([]);

  const carregar = useCallback(async () => {
    try {
      const [segs, bcs] = await Promise.all([api.broadcastSegmentos(), api.broadcasts()]);
      setSegmentos(segs);
      setLista(bcs);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  // Poll enquanto houver campanha "enviando".
  useEffect(() => {
    if (!lista.some((b) => b.status === "enviando")) return;
    const id = setInterval(carregar, 5000);
    return () => clearInterval(id);
  }, [lista, carregar]);

  // Carrega clientes elegíveis (ativos, sem opt-out) ao entrar no modo manual.
  useEffect(() => {
    if (modo !== "manual" || clientes !== null) return;
    api
      .clientes("ativo")
      .then((cs) => setClientes(cs.filter((c) => !c.opt_out)))
      .catch(() => setClientes([]));
  }, [modo, clientes]);

  const filtrados = useMemo(() => {
    if (!clientes) return [];
    const q = busca.trim().toLowerCase();
    if (!q) return clientes;
    return clientes.filter((c) =>
      [c.razao_social, c.nome_contato, c.cnpj, c.telefone]
        .filter(Boolean)
        .some((v) => v!.toLowerCase().includes(q)),
    );
  }, [clientes, busca]);

  const elegiveis =
    modo === "manual" ? selecionados.size : (segmentos[segmento] ?? null);

  function toggleCliente(tel: string) {
    setSelecionados((prev) => {
      const next = new Set(prev);
      next.has(tel) ? next.delete(tel) : next.add(tel);
      return next;
    });
  }

  function toggleTodosFiltrados() {
    const tels = filtrados.map((c) => c.telefone);
    const todosMarcados = tels.every((t) => selecionados.has(t));
    setSelecionados((prev) => {
      const next = new Set(prev);
      for (const t of tels) todosMarcados ? next.delete(t) : next.add(t);
      return next;
    });
  }

  async function onEscolherImagem(file: File) {
    setSubindoImg(true);
    setMsg(null);
    try {
      const r = await api.uploadPromocaoImagem(file);
      setImagem({ url: r.url, arquivo: r.arquivo });
    } catch {
      setMsg("Falha no upload da imagem. Use JPG, PNG ou WEBP (até 5 MB).");
    } finally {
      setSubindoImg(false);
      if (imgInputRef.current) imgInputRef.current.value = "";
    }
  }

  async function enviar() {
    const t = texto.trim();
    if ((!t && !imagem) || enviando) return;
    if (!elegiveis) return;

    const alvo =
      modo === "manual"
        ? `${selecionados.size} clientes selecionados`
        : `${elegiveis ?? "?"} clientes (${
            SEGMENTOS.find((s) => s.key === segmento)?.label ?? segmento
          })`;
    if (
      !window.confirm(
        `Enviar ${imagem ? "o banner + mensagem" : "a mensagem"} para ${alvo} pelo WhatsApp?\n\n` +
          "⚠️ Disparo em massa pode levar ao bloqueio do número. O envio é espaçado (anti-bloqueio).",
      )
    )
      return;

    setEnviando(true);
    setMsg(null);
    try {
      const r = await api.enviarBroadcast({
        texto: t,
        imagem: imagem?.url,
        ...(modo === "manual"
          ? { telefones: Array.from(selecionados) }
          : { segmento }),
      });
      setMsg(`Campanha #${r.id} iniciada para ${r.total} clientes.`);
      setTexto("");
      setImagem(null);
      setSelecionados(new Set());
      carregar();
    } catch {
      setMsg("Não foi possível iniciar o envio. Verifique a Evolution API / destinatários.");
    } finally {
      setEnviando(false);
    }
  }

  const tone = (s: Broadcast["status"]) =>
    s === "concluido" ? "success" : s === "erro" ? "danger" : "info";

  const podeEnviar = !enviando && (texto.trim() || imagem) && !!elegiveis;

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      <div className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/5 px-3 py-2.5 text-xs text-warning">
        <AlertTriangle size={15} className="mt-0.5 shrink-0" />
        <span>
          Disparo em massa por WhatsApp não-oficial pode <b>bloquear o número</b>. O envio é
          espaçado automaticamente e clientes que responderem <b>“sair”</b> deixam de receber
          (opt-out). Use com moderação e conteúdo relevante.
        </span>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.3fr_1fr]">
        <div className="flex flex-col gap-5">
          {/* Compor promoção */}
          <Card>
            <CardHeader title="Nova promoção" subtitle="mensagem + banner (opcional)" />
            <div className="flex flex-col gap-3 p-5">
              <textarea
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                rows={5}
                placeholder="Escreva a mensagem da promoção… (ex: Oferta especial em captores Franklin esta semana! ⚡)"
                className="w-full resize-y rounded-lg border bg-surface p-3 text-sm text-ink outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/40"
              />

              {/* Banner / imagem */}
              {imagem ? (
                <div className="relative overflow-hidden rounded-xl border">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={api.mediaUrl(imagem.url)}
                    alt="Banner da promoção"
                    className="max-h-52 w-full object-contain bg-surface-2"
                  />
                  <button
                    onClick={() => setImagem(null)}
                    title="Remover banner"
                    className="absolute right-2 top-2 grid h-8 w-8 place-items-center rounded-lg bg-black/60 text-white transition hover:bg-black/80"
                  >
                    <X size={16} />
                  </button>
                </div>
              ) : (
                <label
                  className={cn(
                    "flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-5 text-center text-sm text-muted transition hover:bg-surface-2",
                    subindoImg && "pointer-events-none opacity-60",
                  )}
                >
                  <ImageIcon size={18} className="text-accent" />
                  {subindoImg ? "Enviando imagem…" : "Adicionar banner (JPG, PNG ou WEBP · até 5 MB)"}
                  <input
                    ref={imgInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    disabled={subindoImg}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) onEscolherImagem(f);
                    }}
                    className="hidden"
                  />
                </label>
              )}

              <div className="flex items-center justify-between border-t pt-3">
                <span className="text-xs text-faint">{texto.length} caracteres</span>
                <button
                  onClick={enviar}
                  disabled={!podeEnviar}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:opacity-90 disabled:opacity-50"
                >
                  <Send size={15} />
                  {enviando ? "Enviando…" : `Enviar para ${elegiveis ?? 0}`}
                </button>
              </div>
              {msg && <p className="text-xs text-accent-ink">{msg}</p>}
            </div>
          </Card>

          {/* Destinatários */}
          <Card>
            <CardHeader
              title="Destinatários"
              subtitle={
                modo === "manual"
                  ? `${selecionados.size} selecionados`
                  : elegiveis === null
                    ? "selecione um segmento"
                    : `${elegiveis} clientes elegíveis`
              }
            />
            <div className="flex flex-col gap-3 p-5">
              {/* Alternador de modo */}
              <div className="flex gap-1.5">
                <ModoBtn ativo={modo === "segmento"} onClick={() => setModo("segmento")} icon={<Target size={13} />}>
                  Por segmento
                </ModoBtn>
                <ModoBtn ativo={modo === "manual"} onClick={() => setModo("manual")} icon={<Users size={13} />}>
                  Escolher clientes
                </ModoBtn>
              </div>

              {modo === "segmento" ? (
                <div className="flex flex-wrap gap-1.5">
                  {SEGMENTOS.map((s) => (
                    <button
                      key={s.key}
                      onClick={() => setSegmento(s.key)}
                      className={cn(
                        "rounded-lg px-3 py-1.5 text-xs font-medium transition",
                        segmento === s.key
                          ? "bg-accent-soft text-accent-ink"
                          : "bg-surface text-muted ring-1 ring-inset ring-border hover:text-ink",
                      )}
                    >
                      {s.label}
                      <span className="ml-1.5 text-faint">{segmentos[s.key] ?? "…"}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <Search
                        size={14}
                        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint"
                      />
                      <input
                        value={busca}
                        onChange={(e) => setBusca(e.target.value)}
                        placeholder="Buscar por nome, CNPJ ou telefone…"
                        className="w-full rounded-lg border bg-surface py-1.5 pl-8 pr-3 text-xs text-ink outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/40"
                      />
                    </div>
                    <button
                      onClick={toggleTodosFiltrados}
                      disabled={filtrados.length === 0}
                      className="shrink-0 rounded-lg border px-2.5 py-1.5 text-xs font-medium text-muted transition hover:bg-surface-2 hover:text-ink disabled:opacity-50"
                    >
                      {filtrados.length > 0 && filtrados.every((c) => selecionados.has(c.telefone))
                        ? "Limpar"
                        : "Todos"}
                    </button>
                  </div>

                  <div className="max-h-72 divide-y overflow-y-auto rounded-lg border">
                    {clientes === null ? (
                      <p className="p-4 text-center text-xs text-faint">Carregando clientes…</p>
                    ) : filtrados.length === 0 ? (
                      <p className="p-4 text-center text-xs text-faint">
                        {clientes.length === 0
                          ? "Nenhum cliente ativo elegível."
                          : "Nenhum cliente para esta busca."}
                      </p>
                    ) : (
                      filtrados.map((c) => {
                        const marcado = selecionados.has(c.telefone);
                        return (
                          <label
                            key={c.telefone}
                            className="flex cursor-pointer items-center gap-3 px-3 py-2 text-xs transition hover:bg-surface-2"
                          >
                            <input
                              type="checkbox"
                              checked={marcado}
                              onChange={() => toggleCliente(c.telefone)}
                              className="h-4 w-4 shrink-0 accent-accent"
                            />
                            <div className="min-w-0 flex-1">
                              <p className="truncate font-medium text-ink">
                                {c.razao_social ?? c.nome_contato ?? c.telefone}
                              </p>
                              <p className="truncate text-[11px] text-faint">
                                {c.telefone}
                                {c.cnpj ? ` · ${c.cnpj}` : ""}
                              </p>
                            </div>
                          </label>
                        );
                      })
                    )}
                  </div>
                  <p className="text-[11px] text-faint">
                    Só clientes <b>ativos</b> e sem opt-out aparecem aqui.
                  </p>
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Histórico de campanhas */}
        <Card>
          <CardHeader title="Campanhas" subtitle="Histórico de disparos" />
          {lista.length === 0 ? (
            <EmptyState icon={<Megaphone size={24} />} title="Nenhuma campanha ainda" />
          ) : (
            <ul className="divide-y">
              {lista.map((b) => (
                <li key={b.id} className="px-5 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] text-faint">#{b.id}</span>
                    <Badge tone={tone(b.status)} dot>
                      {b.status}
                    </Badge>
                  </div>
                  <div className="mt-1 flex gap-2">
                    {b.imagem && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={api.mediaUrl(b.imagem)}
                        alt="Banner"
                        className="h-12 w-12 shrink-0 rounded-md border object-cover"
                      />
                    )}
                    <p className="line-clamp-2 text-xs text-ink">
                      {b.texto || <span className="text-faint">(somente banner)</span>}
                    </p>
                  </div>
                  <div className="mt-1.5 flex items-center gap-3 text-[11px] text-muted">
                    <span className="tnum">
                      {b.enviados}/{b.total} enviados
                    </span>
                    {b.falhas > 0 && <span className="tnum text-danger">{b.falhas} falhas</span>}
                    <span className="ml-auto">{relativo(b.created_at)}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        b.status === "erro" ? "bg-danger" : "bg-accent",
                      )}
                      style={{
                        width: `${b.total ? Math.round(((b.enviados + b.falhas) / b.total) * 100) : 0}%`,
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function ModoBtn({
  ativo,
  onClick,
  icon,
  children,
}: {
  ativo: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition",
        ativo
          ? "bg-accent-soft text-accent-ink"
          : "bg-surface text-muted ring-1 ring-inset ring-border hover:text-ink",
      )}
    >
      {icon}
      {children}
    </button>
  );
}
