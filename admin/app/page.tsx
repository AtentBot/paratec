import { Card, CardHeader, Badge } from "@/components/ui";
import { StatCard } from "@/components/stat-card";
import { OfflineNotice } from "@/components/offline-notice";
import { WeeklyBars, SpecialistBars, ResolutionRing } from "@/components/charts";
import { api, tryApi } from "@/lib/api";
import { diaSemana, especialistaLabel, iniciais, relativo } from "@/lib/format";
import { MessagesSquare, Headset, Package, Gauge, ArrowRight } from "lucide-react";
import Link from "next/link";

const CORES = ["var(--accent)", "var(--info)", "var(--success)", "var(--warning)"];

export default async function DashboardPage() {
  const [metrics, stats, conversas] = await Promise.all([
    tryApi(api.metrics),
    tryApi(api.stats),
    tryApi(() => api.conversas()),
  ]);

  const offline = metrics === null && stats === null;

  const totais = metrics?.totais ?? {
    conversas: 0,
    atendimentos: 0,
    handoffs: 0,
    na_fila: 0,
    resolvidos_pct: 0,
  };
  const semana = (metrics?.semana ?? []).map((d) => ({
    dia: diaSemana(d.dia),
    atendimentos: d.atendimentos,
    humano: d.humano,
  }));
  const especialistas = (metrics?.especialistas ?? []).map((e, i) => ({
    nome: especialistaLabel[e.nome] ?? e.nome,
    valor: e.valor,
    cor: CORES[i % CORES.length],
  }));
  const recentes = (conversas ?? []).slice(0, 4);

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      {offline && <OfflineNotice base={api.base} />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Atendimentos (7 dias)"
          value={totais.atendimentos}
          icon={<MessagesSquare size={18} />}
          hint={`${totais.conversas} conversas no total`}
          accent
        />
        <StatCard
          label="Resolvidos pela IA"
          value={`${totais.resolvidos_pct}%`}
          icon={<Gauge size={18} />}
          hint={`${totais.handoffs} encaminhados a humano`}
        />
        <StatCard
          label="Na fila humana"
          value={totais.na_fila}
          icon={<Headset size={18} />}
          hint="Aguardando atendente"
        />
        <StatCard
          label="Produtos no catálogo"
          value={stats?.produtos ?? "—"}
          icon={<Package size={18} />}
          hint={
            stats
              ? `${stats.variantes} variantes · ${stats.categorias} categorias`
              : "catálogo indisponível"
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Volume de atendimento"
            subtitle="Últimos 7 dias"
            action={
              <div className="flex items-center gap-4 text-xs text-muted">
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm bg-accent" /> Total
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-sm bg-ink/30" /> Humano
                </span>
              </div>
            }
          />
          <div className="p-4">
            <WeeklyBars data={semana} />
          </div>
        </Card>

        <Card>
          <CardHeader title="Resolução automática" subtitle="Média da semana" />
          <div className="flex flex-col items-center gap-4 p-6">
            <ResolutionRing pct={totais.resolvidos_pct} />
            <p className="text-center text-xs text-muted">
              {totais.atendimentos - totais.handoffs} de {totais.atendimentos}{" "}
              atendimentos concluídos sem intervenção humana.
            </p>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Uso por especialista" subtitle="Roteamento do supervisor" />
          <div className="p-5">
            {especialistas.length ? (
              <SpecialistBars data={especialistas} />
            ) : (
              <p className="py-8 text-center text-xs text-muted">
                Sem roteamento registrado ainda.
              </p>
            )}
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Conversas recentes"
            action={
              <Link
                href="/conversas"
                className="inline-flex items-center gap-1 text-xs font-medium text-accent-ink hover:underline"
              >
                Ver todas <ArrowRight size={13} />
              </Link>
            }
          />
          {recentes.length ? (
            <ul className="divide-y">
              {recentes.map((c) => (
                <li
                  key={c.thread_id}
                  className="flex items-center gap-3 px-5 py-3 transition hover:bg-surface-2"
                >
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent-ink">
                    {iniciais(c.cliente, c.telefone ?? c.thread_id)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium text-ink">
                        {c.cliente ?? c.telefone ?? c.thread_id}
                      </p>
                      <span className="text-[11px] text-faint">
                        {relativo(c.updated_at)}
                      </span>
                    </div>
                    <p className="truncate text-xs text-muted">
                      {c.last_preview ?? "—"}
                    </p>
                  </div>
                  <Badge
                    tone={
                      c.status === "humano"
                        ? "danger"
                        : c.status === "resolvida"
                          ? "success"
                          : "accent"
                    }
                    dot
                  >
                    {c.status === "humano"
                      ? "Humano"
                      : c.status === "resolvida"
                        ? "Resolvida"
                        : "IA"}
                  </Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 py-8 text-center text-xs text-muted">
              Nenhuma conversa registrada ainda.
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
