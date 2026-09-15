"use client";

import { Restrito } from "@/components/restrito";
import { api } from "@/lib/api";
import type { AdminTenant } from "@/lib/types";
import { Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";

const SUB_STATUS: Record<string, { label: string; cls: string }> = {
  active: { label: "Ativa", cls: "bg-surface-2 text-success" },
  trialing: { label: "Em teste", cls: "bg-surface-2 text-info" },
  past_due: { label: "Pendente", cls: "bg-warning/10 text-warning" },
  unpaid: { label: "Não paga", cls: "bg-warning/10 text-warning" },
  canceled: { label: "Cancelada", cls: "bg-surface-2 text-muted" },
  incomplete: { label: "Incompleta", cls: "bg-surface-2 text-muted" },
};
const STATUS_OPCOES = Object.keys(SUB_STATUS);
const PLANOS = ["essencial", "profissional", "escala"];

function data(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString("pt-BR") : "—";
}

export default function AdminAssinaturas() {
  const [rows, setRows] = useState<AdminTenant[] | null>(null);
  const [restrito, setRestrito] = useState(false);
  const [edit, setEdit] = useState<AdminTenant | null>(null);

  async function carregar() {
    try {
      setRows(await api.adminTenants());
    } catch {
      setRestrito(true);
    }
  }
  useEffect(() => { carregar(); }, []);

  if (restrito) return <Restrito />;
  if (!rows) return <div className="flex items-center gap-2 text-muted"><Loader2 size={16} className="animate-spin" /> Carregando…</div>;

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <div className="overflow-x-auto rounded-2xl border bg-surface shadow-card">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b text-left text-[11px] uppercase tracking-wider text-faint">
              <th className="px-4 py-3">Cliente</th>
              <th className="px-4 py-3">Plano</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Renova/expira</th>
              <th className="px-4 py-3 text-center">Usuários</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => {
              const s = t.sub_status ? (SUB_STATUS[t.sub_status] ?? { label: t.sub_status, cls: "bg-surface-2 text-muted" }) : null;
              return (
                <tr key={t.id} className="border-b last:border-0">
                  <td className="px-4 py-3">
                    <p className="font-medium text-ink">{t.nome}</p>
                    <p className="text-[11px] text-faint">{t.slug} · desde {data(t.created_at)}</p>
                  </td>
                  <td className="px-4 py-3 capitalize text-muted">{t.plan ?? "—"}</td>
                  <td className="px-4 py-3">
                    {s ? (
                      <span className={"rounded-full px-2.5 py-1 text-[11px] font-semibold " + s.cls}>{s.label}</span>
                    ) : <span className="text-faint">sem assinatura</span>}
                    {t.cancel_at_period_end && <span className="ml-1 text-[10px] text-warning">(cancela)</span>}
                  </td>
                  <td className="px-4 py-3 text-muted">{data(t.current_period_end)}</td>
                  <td className="px-4 py-3 text-center tabular-nums text-muted">{t.usuarios}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => setEdit(t)} className="rounded-lg border px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-2">
                      Editar
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {edit && <EditarAssinatura t={edit} onClose={() => setEdit(null)} onDone={carregar} />}
    </div>
  );
}

function EditarAssinatura({ t, onClose, onDone }: { t: AdminTenant; onClose: () => void; onDone: () => void }) {
  const [status, setStatus] = useState(t.sub_status ?? "active");
  const [plan, setPlan] = useState(t.plan ?? "profissional");
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar() {
    setBusy(true); setErro(null);
    try {
      await api.adminSetAssinatura(t.id, { status, plan });
      onDone();
      onClose();
    } catch {
      setErro("Não foi possível salvar.");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-2xl border bg-surface p-6 shadow-lift">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-semibold text-ink">Assinatura — {t.nome}</h2>
            <p className="text-xs text-muted">Ajuste manual (comp/suspensão). Espelha na fatura só via Stripe.</p>
          </div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink"><X size={16} /></button>
        </div>
        <div className="mt-4 flex flex-col gap-3">
          <label className="text-sm">
            <span className="font-medium text-ink">Status</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)}
              className="mt-1 w-full rounded-lg border bg-surface px-3 py-2.5 text-ink outline-none focus:ring-2 focus:ring-accent/40">
              {STATUS_OPCOES.map((s) => <option key={s} value={s}>{SUB_STATUS[s].label}</option>)}
            </select>
          </label>
          <label className="text-sm">
            <span className="font-medium text-ink">Plano</span>
            <select value={plan} onChange={(e) => setPlan(e.target.value)}
              className="mt-1 w-full rounded-lg border bg-surface px-3 py-2.5 capitalize text-ink outline-none focus:ring-2 focus:ring-accent/40">
              {PLANOS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          {erro && <p className="text-sm text-danger">{erro}</p>}
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="rounded-lg border px-4 py-2 text-sm font-medium text-muted hover:text-ink">Cancelar</button>
            <button onClick={salvar} disabled={busy}
              className="inline-flex items-center gap-2 rounded-lg bg-feature px-4 py-2 text-sm font-semibold text-feature-fg transition hover:opacity-90 disabled:opacity-50">
              {busy && <Loader2 size={15} className="animate-spin" />} Salvar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
