"use client";

import { Badge, Card, CardHeader, EmptyState } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { relativo } from "@/lib/format";
import type { RagFonte, RagStatus } from "@/lib/types";
import {
  BookOpen,
  FileText,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

export default function ConhecimentoPage() {
  const [status, setStatus] = useState<RagStatus | null>(null);
  const [fontes, setFontes] = useState<RagFonte[]>([]);
  const [offline, setOffline] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [reindexando, setReindexando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const carregar = useCallback(async () => {
    try {
      const [st, fs] = await Promise.all([api.ragStatus(), api.ragFontes()]);
      setStatus(st);
      setFontes(fs);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function enviar(file: File) {
    setEnviando(true);
    setMsg(null);
    try {
      const r = await api.ragUpload(file);
      setMsg(`"${r.fonte}" ingerido — ${r.chunks} trechos adicionados à base.`);
      carregar();
    } catch {
      setMsg("Falha no upload. Verifique o arquivo (PDF/TXT/MD) e se o RAG está ativo.");
    } finally {
      setEnviando(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function reindexar() {
    setReindexando(true);
    setMsg(null);
    try {
      const r = await api.ragReindexarCatalogo();
      setMsg(`Catálogo reindexado — ${r.ingeridos} trechos.`);
      carregar();
    } catch {
      setMsg("Falha ao reindexar o catálogo.");
    } finally {
      setReindexando(false);
    }
  }

  async function remover(source: string) {
    if (!window.confirm(`Remover a fonte "${source}" da base de conhecimento?`)) return;
    try {
      await api.ragRemoverFonte(source);
      carregar();
    } catch {
      setMsg("Falha ao remover a fonte.");
    }
  }

  const desativado = status && !status.enabled;

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      {desativado && (
        <div className="rounded-lg border border-dashed bg-surface-2 px-3 py-2 text-xs text-muted">
          RAG desativado (sem banco vetorial configurado). O agente funciona normalmente,
          mas a busca em documentos fica indisponível.
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1.2fr]">
        {/* Upload */}
        <Card>
          <CardHeader
            title="Adicionar documento"
            subtitle="PDF, TXT ou Markdown (normas, manuais, tabelas)"
          />
          <div className="flex flex-col gap-3 p-5">
            <label
              className={
                "flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition hover:bg-surface-2 " +
                (enviando ? "pointer-events-none opacity-60" : "")
              }
            >
              <Upload size={22} className="text-accent" />
              <span className="text-sm font-medium text-ink">
                {enviando ? "Enviando e indexando…" : "Clique para escolher um arquivo"}
              </span>
              <span className="text-[11px] text-faint">.pdf · .txt · .md</span>
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,.txt,.md,text/plain,application/pdf"
                disabled={enviando || !!desativado}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) enviar(f);
                }}
                className="hidden"
              />
            </label>
            {msg && <p className="text-xs text-accent-ink">{msg}</p>}
            <div className="flex items-center justify-between border-t pt-3">
              <p className="text-xs text-muted">
                Reconstruir a base do catálogo (produtos/SKUs):
              </p>
              <button
                onClick={reindexar}
                disabled={reindexando || !!desativado}
                className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium text-ink transition hover:bg-surface-2 disabled:opacity-50"
              >
                <RefreshCw size={13} className={reindexando ? "animate-spin" : ""} />
                {reindexando ? "Reindexando…" : "Reindexar catálogo"}
              </button>
            </div>
          </div>
        </Card>

        {/* Fontes */}
        <Card>
          <CardHeader
            title="Fontes na base"
            subtitle={
              status?.enabled
                ? `${status.chunks ?? 0} trechos · ${status.fontes ?? 0} fontes`
                : "—"
            }
          />
          {fontes.length === 0 ? (
            <EmptyState
              icon={<BookOpen size={26} />}
              title="Nenhuma fonte ainda"
              hint="Envie um documento ou reindexe o catálogo para alimentar o agente."
            />
          ) : (
            <ul className="divide-y">
              {fontes.map((f) => (
                <li key={f.source} className="flex items-center gap-3 px-5 py-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-ink">
                    <FileText size={16} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{f.source}</p>
                    <p className="text-[11px] text-faint">
                      atualizado {relativo(f.atualizado)}
                    </p>
                  </div>
                  <Badge tone="neutral">{f.chunks} trechos</Badge>
                  <button
                    onClick={() => remover(f.source)}
                    title="Remover fonte"
                    className="grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-danger/10 hover:text-danger"
                  >
                    <Trash2 size={15} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
