"use client";

import { StatCard } from "@/components/stat-card";
import { Restrito } from "@/components/restrito";
import { api } from "@/lib/api";
import type { AdminOverview } from "@/lib/types";
import { Building2, CheckCircle2, Gauge, LifeBuoy, Loader2, Tags } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export default function AdminHome() {
  const [o, setO] = useState<AdminOverview | null>(null);
  const [restrito, setRestrito] = useState(false);

  useEffect(() => {
    api.adminOverview().then(setO).catch(() => setRestrito(true));
  }, []);

  if (restrito) return <Restrito />;
  if (!o) return <div className="flex items-center gap-2 text-muted"><Loader2 size={16} className="animate-spin" /> Carregando…</div>;

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Clientes (tenants)" value={o.tenants} icon={<Building2 size={18} />} accent />
        <StatCard label="Assinaturas ativas" value={o.ativos} icon={<CheckCircle2 size={18} />} />
        <StatCard label="Chamados abertos" value={o.chamados_abertos} icon={<LifeBuoy size={18} />} hint="aberto + em andamento" />
        <StatCard label="Consumo do mês" value={brl(o.consumo_mes)} icon={<Gauge size={18} />} hint="todos os clientes" />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Link href="/admin/chamados" className="rounded-2xl border bg-surface p-5 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift">
          <LifeBuoy size={20} className="text-accent-ink" />
          <p className="mt-3 text-sm font-semibold text-ink">Chamados</p>
          <p className="text-xs text-muted">Fila, prioridade e status de todos os clientes.</p>
        </Link>
        <Link href="/admin/assinaturas" className="rounded-2xl border bg-surface p-5 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift">
          <CheckCircle2 size={20} className="text-accent-ink" />
          <p className="mt-3 text-sm font-semibold text-ink">Assinaturas</p>
          <p className="text-xs text-muted">Planos e status por cliente; ajustes manuais.</p>
        </Link>
        <Link href="/admin/planos" className="rounded-2xl border bg-surface p-5 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift">
          <Tags size={20} className="text-accent-ink" />
          <p className="mt-3 text-sm font-semibold text-ink">Planos e preços</p>
          <p className="text-xs text-muted">Preço base de cada plano, aplicado ao Stripe e ao site.</p>
        </Link>
        <Link href="/admin/consumo" className="rounded-2xl border bg-surface p-5 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift">
          <Gauge size={20} className="text-accent-ink" />
          <p className="mt-3 text-sm font-semibold text-ink">Consumo</p>
          <p className="text-xs text-muted">Tokens e custo estimado por cliente no mês.</p>
        </Link>
      </div>
    </div>
  );
}
