"use client";

import { Card } from "@/components/ui";
import { OfflineNotice } from "@/components/offline-notice";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { RelatorioResumo } from "@/lib/types";
import {
  CircleCheck,
  ClipboardList,
  Download,
  Headset,
  Megaphone,
  MessagesSquare,
  Printer,
  UserMinus,
  UserPlus,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

const iso = (d: Date) => d.toISOString().slice(0, 10);
function diasAtras(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return iso(d);
}

const PRESETS = [
  { label: "7 dias", dias: 7 },
  { label: "30 dias", dias: 30 },
  { label: "90 dias", dias: 90 },
];

export default function RelatoriosPage() {
  const [desde, setDesde] = useState(diasAtras(30));
  const [ate, setAte] = useState(iso(new Date()));
  const [preset, setPreset] = useState(30);
  const [resumo, setResumo] = useState<RelatorioResumo | null>(null);
  const [offline, setOffline] = useState(false);
  const [carregando, setCarregando] = useState(true);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setResumo(await api.relatorioResumo(desde, ate));
      setOffline(false);
    } catch {
      setOffline(true);
      setResumo(null);
    } finally {
      setCarregando(false);
    }
  }, [desde, ate]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function aplicarPreset(dias: number) {
    setPreset(dias);
    setDesde(diasAtras(dias));
    setAte(iso(new Date()));
  }

  const cards: { icon: React.ReactNode; label: string; value: number }[] = [
    { icon: <MessagesSquare size={18} />, label: "Atendimentos", value: resumo?.atendimentos ?? 0 },
    { icon: <CircleCheck size={18} />, label: "Resolvidas", value: resumo?.resolvidas ?? 0 },
    { icon: <Headset size={18} />, label: "Encaminhados a humano", value: resumo?.handoffs ?? 0 },
    { icon: <UserPlus size={18} />, label: "Novos clientes", value: resumo?.novos_clientes ?? 0 },
    { icon: <ClipboardList size={18} />, label: "Orçamentos", value: resumo?.orcamentos ?? 0 },
    { icon: <Megaphone size={18} />, label: "Campanhas", value: resumo?.campanhas ?? 0 },
    { icon: <UserMinus size={18} />, label: "Opt-outs", value: resumo?.opt_outs ?? 0 },
  ];

  return (
    <div className="flex flex-col gap-5 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      <div className="print-only mb-2 border-b pb-2">
        <p className="text-xl font-bold text-ink">Relatório · Paratec Atendimentos</p>
        <p className="text-sm text-muted">Período: {desde} até {ate}</p>
      </div>

      <div className="no-print flex justify-end">
        <button
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium text-ink transition hover:bg-surface-2"
        >
          <Printer size={14} /> Baixar PDF
        </button>
      </div>

      {/* Período */}
      <Card className="p-4 no-print">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p.dias}
                onClick={() => aplicarPreset(p.dias)}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-xs font-medium transition",
                  preset === p.dias
                    ? "bg-accent-soft text-accent-ink"
                    : "text-muted hover:bg-surface-2 hover:text-ink",
                )}
              >
                Últimos {p.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted">
            <input
              type="date"
              value={desde}
              onChange={(e) => {
                setDesde(e.target.value);
                setPreset(-1);
              }}
              className="rounded-lg border bg-surface px-2 py-1.5 text-ink outline-none focus:ring-2 focus:ring-accent/40"
            />
            <span>até</span>
            <input
              type="date"
              value={ate}
              onChange={(e) => {
                setAte(e.target.value);
                setPreset(-1);
              }}
              className="rounded-lg border bg-surface px-2 py-1.5 text-ink outline-none focus:ring-2 focus:ring-accent/40"
            />
          </div>
        </div>
      </Card>

      {/* Indicadores do período */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
        {cards.map((c) => (
          <div key={c.label} className="rounded-2xl border bg-surface p-4 shadow-card">
            <div className="flex items-start justify-between">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent-soft text-accent-ink">
                {c.icon}
              </span>
            </div>
            <p
              className={cn(
                "tnum mt-3 text-2xl font-semibold text-ink",
                carregando && "animate-pulse text-faint",
              )}
            >
              {carregando ? "—" : c.value}
            </p>
            <p className="text-xs text-muted">{c.label}</p>
          </div>
        ))}
      </div>

      {/* Exportações */}
      <Card className="p-5 no-print">
        <p className="mb-3 text-sm font-semibold text-ink">Exportar (CSV)</p>
        <div className="flex flex-wrap gap-2.5">
          <a
            href={api.relatorioConversasCsvUrl(desde, ate)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-feature px-3.5 py-2 text-xs font-medium text-feature-fg transition hover:opacity-90"
          >
            <Download size={14} /> Atendimentos do período
          </a>
          <a
            href={api.clientesCsvUrl()}
            className="inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-xs font-medium text-ink transition hover:bg-surface-2"
          >
            <Download size={14} /> Clientes (todos)
          </a>
          <a
            href={api.filaCsvUrl()}
            className="inline-flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-xs font-medium text-ink transition hover:bg-surface-2"
          >
            <Download size={14} /> Fila humana (todos)
          </a>
        </div>
        <p className="mt-3 text-[11px] text-faint">
          Período selecionado: {desde} até {ate}. Os arquivos abrem no Excel/Planilhas.
        </p>
      </Card>
    </div>
  );
}
