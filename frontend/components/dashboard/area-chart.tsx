'use client';

import { useId, useMemo, useState } from 'react';
import { cn } from '@/lib/shadcn/utils';

export interface AreaPoint {
  /** Axis and tooltip label, e.g. "Oct 9". */
  label: string;
  value: number;
}

// viewBox units. The wrapper gets the same aspect ratio, so the SVG never letterboxes and the
// hover tooltip can be placed with plain percentages.
const VB_W = 640;
const VB_H = 220;
const PAD = { top: 14, right: 12, bottom: 24, left: 34 };
const PLOT_W = VB_W - PAD.left - PAD.right;
const PLOT_H = VB_H - PAD.top - PAD.bottom;

/** Rounds a max up to a "nice" gridline value (1/2/5 × 10^n). */
function niceMax(max: number): number {
  if (max <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const residual = max / magnitude;
  const nice = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
  return nice * magnitude;
}

function tickIndices(n: number): number[] {
  if (n <= 7) return Array.from({ length: n }, (_, i) => i);
  const step = Math.ceil(n / 6);
  const ticks = new Set<number>();
  for (let i = 0; i < n; i += step) ticks.add(i);
  ticks.add(n - 1);
  return Array.from(ticks).sort((a, b) => a - b);
}

interface AreaChartProps {
  points: AreaPoint[];
  /** Accessible summary of what the chart shows. */
  ariaLabel: string;
  /** Tooltip unit, singular and plural, e.g. ['conversation', 'conversations']. */
  unit: [string, string];
  /** A CSS colour; defaults to the main chart series. */
  color?: string;
  className?: string;
}

/**
 * Single-series area chart in inline SVG — no chart library. The caller handles loading, error
 * and empty states; this only draws data. Hovering shows the value for the nearest day.
 */
export function AreaChart({
  points,
  ariaLabel,
  unit,
  color = 'var(--chart-1)',
  className,
}: AreaChartProps) {
  const gradientId = useId();
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const geometry = useMemo(() => {
    const n = points.length;
    if (n === 0) return null;
    const max = niceMax(Math.max(...points.map((p) => p.value)));
    const stepX = n > 1 ? PLOT_W / (n - 1) : 0;
    const xAt = (i: number) => PAD.left + (n > 1 ? i * stepX : PLOT_W / 2);
    const yAt = (v: number) => PAD.top + (1 - v / max) * PLOT_H;
    const baselineY = yAt(0);
    const coords = points.map((p, i) => ({ x: xAt(i), y: yAt(p.value), ...p }));
    const linePath = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x},${c.y}`).join(' ');
    const areaPath = `${linePath} L ${coords[n - 1].x},${baselineY} L ${coords[0].x},${baselineY} Z`;
    return { max, yAt, baselineY, coords, linePath, areaPath, stepX };
  }, [points]);

  if (!geometry) return null;

  function handleMove(e: React.MouseEvent<SVGRectElement>) {
    if (!geometry) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const relX = ((e.clientX - rect.left) / rect.width) * PLOT_W;
    const n = geometry.coords.length;
    const idx = geometry.stepX ? Math.round(relX / geometry.stepX) : 0;
    setHoverIndex(Math.min(n - 1, Math.max(0, idx)));
  }

  const hovered = hoverIndex !== null ? geometry.coords[hoverIndex] : null;
  const yTicks = [0, geometry.max / 2, geometry.max];

  return (
    <div className={cn('relative aspect-[640/220] w-full', className)}>
      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        className="size-full overflow-visible"
        role="img"
        aria-label={ariaLabel}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" style={{ stopColor: color, stopOpacity: 0.28 }} />
            <stop offset="100%" style={{ stopColor: color, stopOpacity: 0 }} />
          </linearGradient>
        </defs>

        {yTicks.map((t) => {
          const y = geometry.yAt(t);
          return (
            <g key={t}>
              <line
                x1={PAD.left}
                x2={VB_W - PAD.right}
                y1={y}
                y2={y}
                className="stroke-border"
                strokeWidth={1}
              />
              <text
                x={PAD.left - 8}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                className="fill-muted-foreground text-[11px] tabular-nums"
              >
                {Math.round(t)}
              </text>
            </g>
          );
        })}

        {tickIndices(geometry.coords.length).map((i) => {
          const c = geometry.coords[i];
          return (
            <text
              key={i}
              x={c.x}
              y={VB_H - 6}
              textAnchor="middle"
              className="fill-muted-foreground text-[11px]"
            >
              {c.label}
            </text>
          );
        })}

        <path d={geometry.areaPath} fill={`url(#${gradientId})`} stroke="none" />
        <path
          d={geometry.linePath}
          fill="none"
          style={{ stroke: color }}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {hovered && (
          <g>
            <line
              x1={hovered.x}
              x2={hovered.x}
              y1={PAD.top}
              y2={geometry.baselineY}
              className="stroke-border"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <circle cx={hovered.x} cy={hovered.y} r={5} className="fill-card" />
            <circle cx={hovered.x} cy={hovered.y} r={3.5} style={{ fill: color }} />
          </g>
        )}

        <rect
          x={PAD.left}
          y={PAD.top}
          width={PLOT_W}
          height={PLOT_H}
          fill="transparent"
          onMouseMove={handleMove}
          onMouseLeave={() => setHoverIndex(null)}
        />
      </svg>

      {hovered && (
        <div
          className="bg-popover text-popover-foreground pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border px-2 py-1 text-xs whitespace-nowrap shadow-md"
          style={{
            left: `${(hovered.x / VB_W) * 100}%`,
            top: `${(hovered.y / VB_H) * 100 - 3}%`,
          }}
        >
          <span className="font-medium tabular-nums">{hovered.value}</span>{' '}
          <span className="text-muted-foreground">{hovered.value === 1 ? unit[0] : unit[1]}</span>
          <div className="text-muted-foreground">{hovered.label}</div>
        </div>
      )}
    </div>
  );
}
