"use client";

import { Badge, Card, EmptyState, Pill } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { iniciais, relativo } from "@/lib/format";
import type { Cliente, ClienteStatus } from "@/lib/types";
import {
  AtSign,
  Building2,
  Phone,
  User,
  Users,
  WifiOff,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const statusMeta: Record<ClienteStatus, { label: string; tone: "success" | "warning" }> = {
  ativo: { label: "Ativo", tone: "success" },
  pendente: { label: "Cadastro pendente", tone: "warning" },
};

export default function ClientesPage() {
  const [lista, setLista] = useState<Cliente[]>([]);
  const [filtro, setFiltro] = useState<"todos" | ClienteStatus>("todos");
  const [offline, setOffline] = useState(false);
  const [carregando, setCarregando] = useState(true);

  const carregar = useCallback(async () => {
    try {
      setLista(await api.clientes(filtro === "todos" ? undefined : filtro));
      setOffline(false);
    } catch {
      setOffline(true);
      setLista([]);
    } finally {
      setCarregando(false);
    }
  }, [filtro]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const ativos = lista.filter((c) => c.status === "ativo").length;
  const tabs: ("todos" | ClienteStatus)[] = ["todos", "ativo", "pendente"];

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1.5">
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setFiltro(t)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition",
                filtro === t
                  ? "bg-accent-soft text-accent-ink"
                  : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              {t}
            </button>
          ))}
        </div>
        {lista.length > 0 && (
          <Badge tone="success" dot>
            {ativos} {ativos === 1 ? "cliente ativo" : "clientes ativos"}
          </Badge>
        )}
      </div>

      {carregando ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-2xl border bg-surface-2" />
          ))}
        </div>
      ) : lista.length === 0 ? (
        <Card>
          <EmptyState
            icon={offline ? <WifiOff size={28} /> : <Users size={28} />}
            title={offline ? "Backend offline" : "Nenhum cliente ainda"}
            hint={
              offline
                ? "Suba o agent-service para ver os cadastros."
                : "Clientes são cadastrados automaticamente no primeiro contato pelo WhatsApp."
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {lista.map((c) => (
            <Card key={c.telefone} className="p-4">
              <div className="flex items-start gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-sm font-semibold text-accent-ink">
                  {iniciais(c.razao_social ?? c.nome_contato, c.telefone)}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-semibold text-ink">
                      {c.razao_social ?? c.nome_contato ?? c.telefone}
                    </p>
                    <Badge tone={statusMeta[c.status].tone} dot>
                      {statusMeta[c.status].label}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-[11px] text-faint">
                    cadastrado {relativo(c.created_at)}
                  </p>
                </div>
              </div>

              <dl className="mt-3 space-y-1.5 border-t pt-3 text-xs">
                <Campo icon={<Building2 size={13} />} label="CNPJ">
                  {c.cnpj ? <Pill>{c.cnpj}</Pill> : <Falta />}
                </Campo>
                <Campo icon={<User size={13} />} label="Contato">
                  {c.nome_contato ?? <Falta />}
                </Campo>
                <Campo icon={<AtSign size={13} />} label="E-mail">
                  {c.email ?? <Falta />}
                </Campo>
                <Campo icon={<Phone size={13} />} label="WhatsApp">
                  {c.telefone}
                </Campo>
              </dl>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function Campo({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex w-20 shrink-0 items-center gap-1.5 text-muted">
        {icon} {label}
      </span>
      <span className="min-w-0 flex-1 truncate text-ink">{children}</span>
    </div>
  );
}

function Falta() {
  return <span className="text-faint">—</span>;
}
