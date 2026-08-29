"use client";

import { Badge, Card, EmptyState } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { relativo } from "@/lib/format";
import type { FilaItem, FilaStatus, FilaTipo } from "@/lib/types";
import {
  Check,
  Download,
  FileText,
  Inbox,
  Phone,
  Receipt,
  Truck,
  UserCheck,
  WifiOff,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const tipoMeta: Record<
  FilaTipo,
  { label: string; icon: typeof FileText; tone: "info" | "success" | "warning" }
> = {
  pedido: { label: "Pedido", icon: FileText, tone: "info" },
  entrega: { label: "Entrega", icon: Truck, tone: "success" },
  boleto: { label: "Boleto", icon: Receipt, tone: "warning" },
};

const statusMeta: Record<
  FilaStatus,
  { label: string; tone: "accent" | "info" | "success" }
> = {
  novo: { label: "Novo", tone: "accent" },
  andamento: { label: "Em andamento", tone: "info" },
  concluido: { label: "Concluído", tone: "success" },
};

export default function FilaPage() {
  const [itens, setItens] = useState<FilaItem[]>([]);
  const [tipo, setTipo] = useState<"todos" | FilaTipo>("todos");
  const [offline, setOffline] = useState(false);
  const [carregando, setCarregando] = useState(true);

  const carregar = useCallback(async () => {
    try {
      setItens(await api.fila(tipo === "todos" ? {} : { tipo }));
      setOffline(false);
    } catch {
      setOffline(true);
      setItens([]);
    } finally {
      setCarregando(false);
    }
  }, [tipo]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function atualizar(id: number, patch: { status?: FilaStatus; responsavel?: string }) {
    try {
      const atualizado = await api.atualizarFila(id, patch);
      setItens((xs) => xs.map((x) => (x.id === id ? atualizado : x)));
    } catch {
      setOffline(true);
    }
  }

  const abertos = itens.filter((f) => f.status !== "concluido").length;
  const tabs: ("todos" | FilaTipo)[] = ["todos", "pedido", "entrega", "boleto"];

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1.5">
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setTipo(t)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition",
                tipo === t
                  ? "bg-accent-soft text-accent-ink"
                  : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              {t === "todos" ? "Todos" : tipoMeta[t].label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {itens.length > 0 && (
            <Badge tone="danger" dot>
              {abertos} aguardando atendimento
            </Badge>
          )}
          <a
            href={api.filaCsvUrl(tipo === "todos" ? {} : { tipo })}
            className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
          >
            <Download size={13} /> Exportar CSV
          </a>
        </div>
      </div>

      {carregando ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-36 animate-pulse rounded-2xl border bg-surface-2" />
          ))}
        </div>
      ) : itens.length === 0 ? (
        <Card>
          <EmptyState
            icon={offline ? <WifiOff size={28} /> : <Inbox size={28} />}
            title={offline ? "Backend offline" : "Fila vazia"}
            hint={
              offline
                ? "Suba o agent-service para ver a fila."
                : "Itens aparecem quando os agentes encaminham pedidos, entregas ou boletos a humano."
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {itens.map((f) => {
            const meta = tipoMeta[f.tipo];
            const Icon = meta.icon;
            return (
              <Card key={f.id} className="p-4">
                <div className="flex items-start gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-surface-2 text-muted">
                    <Icon size={18} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge tone={meta.tone}>{meta.label}</Badge>
                      <span className="font-mono text-[11px] text-faint">#{f.id}</span>
                      <span className="ml-auto text-[11px] text-faint">
                        {relativo(f.created_at)}
                      </span>
                    </div>
                    <p className="mt-2 text-sm font-medium text-ink">
                      {f.cliente ?? f.telefone ?? f.thread_id ?? "Cliente"}
                    </p>
                    {(f.telefone || f.thread_id) && (
                      <p className="flex items-center gap-1 text-xs text-muted">
                        <Phone size={11} /> {f.telefone ?? f.thread_id}
                      </p>
                    )}
                    <p className="mt-2 text-sm text-ink/90">{f.resumo}</p>

                    <div className="mt-3 flex items-center justify-between border-t pt-3">
                      <Badge tone={statusMeta[f.status].tone} dot>
                        {statusMeta[f.status].label}
                      </Badge>
                      <div className="flex items-center gap-2">
                        {f.responsavel && (
                          <span className="flex items-center gap-1 text-[11px] text-muted">
                            <UserCheck size={12} /> {f.responsavel}
                          </span>
                        )}
                        {f.status === "novo" && (
                          <button
                            onClick={() => atualizar(f.id, { status: "andamento" })}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-feature px-2.5 py-1.5 text-xs font-medium text-feature-fg transition hover:opacity-90"
                          >
                            <UserCheck size={13} /> Assumir
                          </button>
                        )}
                        {f.status === "andamento" && (
                          <button
                            onClick={() => atualizar(f.id, { status: "concluido" })}
                            className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium text-ink transition hover:bg-surface-2"
                          >
                            <Check size={13} /> Concluir
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
