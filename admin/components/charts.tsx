import type { MetricaDia } from "@/lib/types";

/**
 * Gráfico de barras semanal (atendimentos totais x encaminhados p/ humano).
 * SVG puro, responsivo via viewBox — sem dependências de terceiros.
 */
export function WeeklyBars({ data }: { data: MetricaDia[] }) {
  const W = 640;
  const H = 220;
  const pad = { t: 16, r: 8, b: 28, l: 28 };
  const max = Math.max(...data.map((d) => d.atendimentos), 10);
  const bw = (W - pad.l - pad.r) / data.length;
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const gridVals = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-56 w-full" role="img">
      {gridVals.map((v) => (
        <g key={v}>
          <line
            x1={pad.l}
            x2={W - pad.r}
            y1={y(v)}
            y2={y(v)}
            stroke="var(--border)"
            strokeDasharray="2 4"
          />
          <text x={4} y={y(v) + 3} fontSize="10" fill="var(--faint)">
            {v}
          </text>
        </g>
      ))}
      {data.map((d, i) => {
        const cx = pad.l + i * bw + bw / 2;
        const full = 18;
        return (
          <g key={d.dia}>
            <rect
              x={cx - full / 2}
              y={y(d.atendimentos)}
              width={full}
              height={y(0) - y(d.atendimentos)}
              rx={4}
              fill="var(--accent)"
            />
            <rect
              x={cx - full / 2}
              y={y(d.humano)}
              width={full}
              height={y(0) - y(d.humano)}
              rx={4}
              fill="var(--ink)"
              opacity={0.28}
            />
            <text
              x={cx}
              y={H - 10}
              fontSize="11"
              textAnchor="middle"
              fill="var(--muted)"
            >
              {d.dia}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Barras horizontais para uso por especialista. */
export function SpecialistBars({
  data,
}: {
  data: { nome: string; valor: number; cor: string }[];
}) {
  const max = Math.max(...data.map((d) => d.valor), 1);
  return (
    <div className="flex flex-col gap-4">
      {data.map((d) => (
        <div key={d.nome}>
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <span className="font-medium text-ink">{d.nome}</span>
            <span className="tnum text-muted">{d.valor}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${(d.valor / max) * 100}%`, background: d.cor }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Anel de resolução (percentual resolvido pela IA). */
export function ResolutionRing({ pct }: { pct: number }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const off = c * (1 - pct / 100);
  return (
    <div className="relative grid place-items-center">
      <svg viewBox="0 0 128 128" className="h-32 w-32 -rotate-90">
        <circle cx="64" cy="64" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="12" />
        <circle
          cx="64"
          cy="64"
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={off}
        />
      </svg>
      <div className="absolute text-center">
        <p className="tnum text-2xl font-semibold text-ink">{pct}%</p>
        <p className="text-[10px] uppercase tracking-wide text-muted">pela IA</p>
      </div>
    </div>
  );
}
