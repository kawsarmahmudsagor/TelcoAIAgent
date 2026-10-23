'use client';

import { useId, useMemo, useState } from 'react';
import { PortalButton } from '@/components/portal/ui/link-button';
import { cn } from '@/lib/shadcn/utils';
import { formatDay, formatTaka } from '@/lib/telco-format';
import type { ActivityPoint } from '@/lib/types/admin';

// Two measures on different scales never share an axis: each gets its own plot under its own
// title, with the same days along the bottom.
const VB_W = 560;
const VB_H = 120;
const PAD = { top: 10, right: 10, bottom: 22, left: 46 };
const PLOT_W = VB_W - PAD.left - PAD.right;
const PLOT_H = VB_H - PAD.top - PAD.bottom;

function niceMax(max: number): number {
  if (max <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const r = max / magnitude;
  return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 5 ? 5 : 10) * magnitude;
}

/** 12000 -> "12k", so the axis stays narrow; the tooltip has the exact figure. */
function compact(n: number): string {
  if (n >= 100_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1000) return `${+(n / 1000).toFixed(1)}k`;
  return String(Math.round(n));
}

interface PlotProps {
  title: string;
  total: string;
  /** A CSS colour. */
  color: string;
  kind: 'area' | 'bars';
  values: number[];
  labels: string[];
  format: (n: number) => string;
  ariaLabel: string;
}

function Plot({ title, total, color, kind, values, labels, format, ariaLabel }: PlotProps) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);
  const n = values.length;

  const g = useMemo(() => {
    const max = niceMax(Math.max(0, ...values));
    const slot = PLOT_W / n;
    const xAt = (i: number) =>
      kind === 'bars'
        ? PAD.left + slot * (i + 0.5)
        : PAD.left + (n > 1 ? (i * PLOT_W) / (n - 1) : PLOT_W / 2);
    const yAt = (v: number) => PAD.top + (1 - v / max) * PLOT_H;
    const pts = values.map((v, i) => ({ x: xAt(i), y: yAt(v), v }));
    const line = pts.map((p, i) => `${i ? 'L' : 'M'} ${p.x},${p.y}`).join(' ');
    const base = yAt(0);
    const area = `${line} L ${pts[n - 1].x},${base} L ${pts[0].x},${base} Z`;
    return { max, slot, yAt, pts, line, area, base };
  }, [values, kind, n]);

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const rel = (e.clientX - rect.left) / rect.width;
    const idx = kind === 'bars' ? Math.floor(rel * n) : Math.round(rel * (n - 1));
    setHover(Math.min(n - 1, Math.max(0, idx)));
  }

  const h = hover !== null ? g.pts[hover] : null;
  const ticks = [0, g.max / 2, g.max];

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <p className="flex items-center gap-2 text-xs font-bold">
          <span
            aria-hidden="true"
            className="size-2.5 shrink-0 rounded-[3px]"
            style={{ backgroundColor: color }}
          />
          {title}
        </p>
        <p className="text-muted-foreground text-[11px] tabular-nums">{total}</p>
      </div>
      <div className="relative aspect-[560/120] w-full">
        <svg
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          className="size-full overflow-visible"
          role="img"
          aria-label={ariaLabel}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" style={{ stopColor: color, stopOpacity: 0.22 }} />
              <stop offset="100%" style={{ stopColor: color, stopOpacity: 0 }} />
            </linearGradient>
          </defs>
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={PAD.left}
                x2={VB_W - PAD.right}
                y1={g.yAt(t)}
                y2={g.yAt(t)}
                className="stroke-line"
                strokeWidth={1}
              />
              <text
                x={PAD.left - 8}
                y={g.yAt(t)}
                textAnchor="end"
                dominantBaseline="middle"
                className="fill-muted-foreground text-[10px] tabular-nums"
              >
                {compact(t)}
              </text>
            </g>
          ))}
          {labels.map((label, i) => (
            <text
              key={i}
              x={g.pts[i].x}
              y={VB_H - 5}
              textAnchor="middle"
              className="fill-muted-foreground text-[10px]"
            >
              {label}
            </text>
          ))}
          {kind === 'area' ? (
            <>
              <path d={g.area} fill={`url(#${gradientId})`} />
              <path
                d={g.line}
                fill="none"
                style={{ stroke: color }}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </>
          ) : (
            g.pts.map((p, i) => {
              const w = Math.min(26, g.slot - 8);
              const height = Math.max(0, g.base - p.y);
              return (
                <rect
                  key={i}
                  x={p.x - w / 2}
                  y={p.y}
                  width={w}
                  height={height}
                  rx={Math.min(4, height / 2)}
                  style={{ fill: color }}
                  opacity={hover === null || hover === i ? 1 : 0.45}
                />
              );
            })
          )}
          {h && kind === 'area' && (
            <g>
              <line
                x1={h.x}
                x2={h.x}
                y1={PAD.top}
                y2={g.base}
                className="stroke-line"
                strokeDasharray="3 3"
              />
              <circle cx={h.x} cy={h.y} r={5} className="fill-surface" />
              <circle cx={h.x} cy={h.y} r={3.5} style={{ fill: color }} />
            </g>
          )}
          <rect
            x={PAD.left}
            y={PAD.top}
            width={PLOT_W}
            height={PLOT_H}
            fill="transparent"
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
          />
        </svg>
        {h && hover !== null && (
          <div
            className="bg-popover text-popover-foreground border-line pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border px-2 py-1 text-[11px] whitespace-nowrap shadow-md"
            style={{ left: `${(h.x / VB_W) * 100}%`, top: `${(h.y / VB_H) * 100 - 4}%` }}
          >
            <span className="font-bold tabular-nums">{format(h.v)}</span>
            <span className="text-muted-foreground"> · {labels[hover]}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** Recharge value and new cases per day. The caller handles loading and error states. */
export function ActivityChart({
  points,
  className,
}: {
  points: ActivityPoint[];
  className?: string;
}) {
  const [table, setTable] = useState(false);
  const labels = points.map((p) => formatDay(p.date));
  const recharge = points.map((p) => p.recharge_amount);
  const cases = points.map((p) => p.cases_created);
  const rechargeTotal = recharge.reduce((a, b) => a + b, 0);
  const casesTotal = cases.reduce((a, b) => a + b, 0);

  if (points.length === 0) return null;
  return (
    <div className={cn('space-y-3', className)}>
      <Plot
        title="Recharge value"
        total={`${formatTaka(rechargeTotal)} in 7 days`}
        color="var(--primary)"
        kind="area"
        values={recharge}
        labels={labels}
        format={formatTaka}
        ariaLabel={`Recharge value per day, ${formatTaka(rechargeTotal)} in total.`}
      />
      <Plot
        title="Cases created"
        total={`${casesTotal} in 7 days`}
        color="var(--chart-2)"
        kind="bars"
        values={cases}
        labels={labels}
        format={(n) => `${n} ${n === 1 ? 'case' : 'cases'}`}
        ariaLabel={`Cases created per day, ${casesTotal} in total.`}
      />
      <PortalButton variant="soft" aria-pressed={table} onClick={() => setTable((t) => !t)}>
        {table ? 'Hide table' : 'View as table'}
      </PortalButton>
      {table && (
        <table className="w-full border-collapse text-left text-xs">
          <caption className="sr-only">Recharge value and cases created per day</caption>
          <thead>
            <tr className="text-muted-foreground border-line border-b text-[11px]">
              <th scope="col" className="py-2 pr-3 font-semibold">
                Day
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-semibold">
                Recharge
              </th>
              <th scope="col" className="py-2 text-right font-semibold">
                Cases
              </th>
            </tr>
          </thead>
          <tbody>
            {points.map((p, i) => (
              <tr key={p.date} className="border-line border-b last:border-b-0">
                <th scope="row" className="py-2 pr-3 font-medium">
                  {labels[i]}
                </th>
                <td className="py-2 pr-3 text-right tabular-nums">
                  {formatTaka(p.recharge_amount)}
                </td>
                <td className="py-2 text-right tabular-nums">{p.cases_created}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
