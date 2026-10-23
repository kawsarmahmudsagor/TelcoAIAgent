'use client';

import { useId, useState } from 'react';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { portalApi } from '@/lib/portal-api';
import { usePortalQuery } from '@/lib/portal-sync';
import { cn } from '@/lib/shadcn/utils';
import { formatData, formatDay } from '@/lib/telco-format';

type Period = 7 | 30;

// The plot's own coordinate space; the SVG stretches it to the panel (strokes don't scale).
const W = 560;
const H = 160;

const weekday = new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: 'UTC' });

/** A round step that splits `max` into about three bands (0.2, 0.25, 0.5, 1, 2 …). */
function niceStep(max: number): number {
  if (max <= 0) return 0.5;
  const raw = max / 3;
  const pow = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? 10 * pow;
}

function gbLabel(gb: number): string {
  return gb === 0 ? '0' : `${Number(gb.toFixed(2))} GB`;
}

/** A smooth line through the points that never overshoots them (monotone cubic). */
function smoothPath(points: [number, number][]): string {
  const n = points.length;
  if (n === 0) return '';
  if (n === 1) return `M${points[0][0]} ${points[0][1]}`;
  const slopes = points
    .slice(0, -1)
    .map(([x, y], i) => (points[i + 1][1] - y) / (points[i + 1][0] - x));
  const tangents = points.map((_, i) => {
    if (i === 0) return slopes[0];
    if (i === n - 1) return slopes[n - 2];
    const a = slopes[i - 1];
    const b = slopes[i];
    return a * b <= 0 ? 0 : (2 * a * b) / (a + b);
  });
  let d = `M${points[0][0]} ${points[0][1]}`;
  for (let i = 0; i < n - 1; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[i + 1];
    const dx = (x1 - x0) / 3;
    d += ` C${x0 + dx} ${y0 + tangents[i] * dx},${x1 - dx} ${y1 - tangents[i + 1] * dx},${x1} ${y1}`;
  }
  return d;
}

/** "Your usage at a glance": daily data use over the last 7 or 30 days, in GB. */
export function UsageChart() {
  const [period, setPeriod] = useState<Period>(7);
  const usage = usePortalQuery('usage', () => portalApi.usage(period), period);
  // useId's punctuation would break the `url(#…)` gradient reference, so keep it to word characters.
  const ids = `usage${useId().replace(/\W/g, '')}`;

  return (
    <Panel>
      <PanelHeader
        title="Your usage at a glance"
        description={`Daily data usage · Last ${period} days`}
        action={
          <>
            <label htmlFor={`${ids}-period`} className="sr-only">
              Period
            </label>
            <select
              id={`${ids}-period`}
              value={period}
              onChange={(e) => setPeriod(Number(e.target.value) as Period)}
              className="bg-surface text-foreground border-line focus-visible:ring-ring/60 min-h-9 shrink-0 rounded-[9px] border px-[9px] py-[7px] text-[11px] outline-none focus-visible:ring-[3px]"
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
            </select>
          </>
        }
      />
      {usage.data ? (
        <Chart
          daily={usage.data.daily}
          period={usage.data.period_days}
          titleId={`${ids}-title`}
          refreshing={usage.loading}
        />
      ) : usage.error && !usage.loading ? (
        <LoadError
          what="Your usage"
          error={usage.error}
          onRetry={usage.reload}
          className="h-[200px]"
        />
      ) : (
        <Bone className="mt-[18px] h-[200px] w-full" />
      )}
    </Panel>
  );
}

function Chart({
  daily,
  period,
  titleId,
  refreshing,
}: {
  daily: [string, number][];
  period: number;
  titleId: string;
  refreshing: boolean;
}) {
  const gb = daily.map(([, mb]) => mb / 1024);
  const step = niceStep(Math.max(0, ...gb));
  const top = Math.max(step, step * Math.ceil(Math.max(0, ...gb) / step));
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const y = (v: number) => H - (v / top) * H;
  const x = (i: number) => (daily.length > 1 ? (i / (daily.length - 1)) * W : W / 2);

  const line = smoothPath(gb.map((v, i) => [x(i), y(v)]));
  const area = `${line} L${x(daily.length - 1)} ${H} L${x(0)} ${H} Z`;
  const averageMb = daily.reduce((sum, [, mb]) => sum + mb, 0) / Math.max(1, daily.length);
  const peak = daily.reduce((best, d) => (d[1] > best[1] ? d : best), daily[0]);

  // Every day on a week; every fifth day (counting back from today) on a month.
  const labelled = daily
    .map(([date], i) => ({ date, i }))
    .filter(({ i }) => period <= 7 || (daily.length - 1 - i) % 5 === 0);
  const xLabel = (date: string) =>
    period <= 7 ? weekday.format(new Date(`${date}T00:00:00Z`)) : formatDay(date);

  return (
    <div className={cn('motion-safe:transition-opacity', refreshing && 'opacity-60')}>
      <div className="mt-[18px] grid h-[200px] grid-cols-[auto_minmax(0,1fr)] grid-rows-[minmax(0,1fr)_auto] gap-x-2.5">
        <div className="relative w-9" aria-hidden="true">
          {ticks.map((t) => (
            <span
              key={t}
              className="text-muted-foreground absolute right-0 -translate-y-1/2 text-[10px] whitespace-nowrap"
              style={{ top: `${(1 - t / top) * 100}%` }}
            >
              {gbLabel(t)}
            </span>
          ))}
        </div>
        <div className="relative">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            role="img"
            aria-labelledby={titleId}
            className="absolute inset-0 size-full overflow-visible"
          >
            <title id={titleId}>
              {`Daily data used over the last ${period} days: ${formatData(averageMb)} a day on average, peaking at ${formatData(peak?.[1] ?? 0)} on ${peak ? formatDay(peak[0]) : '—'}.`}
            </title>
            <defs>
              <linearGradient id={`${titleId}-area`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#655cf2" stopOpacity="0.22" />
                <stop offset="1" stopColor="#655cf2" stopOpacity="0" />
              </linearGradient>
            </defs>
            {ticks.map((t) => (
              <line
                key={t}
                x1={0}
                x2={W}
                y1={y(t)}
                y2={y(t)}
                className="stroke-line"
                strokeWidth={1}
                strokeDasharray="4 5"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            <path d={area} fill={`url(#${titleId}-area)`} />
            <line
              x1={0}
              x2={W}
              y1={y(averageMb / 1024)}
              y2={y(averageMb / 1024)}
              className="stroke-mint"
              strokeWidth={2}
              strokeDasharray="6 5"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
            <path
              d={line}
              fill="none"
              stroke="#655cf2"
              strokeWidth={3}
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        </div>
        <div />
        <div className="relative mt-2 h-4" aria-hidden="true">
          {labelled.map(({ date, i }) => (
            <span
              key={date}
              className={cn(
                'text-muted-foreground absolute top-0 text-[10px] whitespace-nowrap',
                i === 0 ? '' : i === daily.length - 1 ? '-translate-x-full' : '-translate-x-1/2'
              )}
              style={{ left: `${(x(i) / W) * 100}%` }}
            >
              {xLabel(date)}
            </span>
          ))}
        </div>
      </div>

      <div className="text-muted-foreground mt-2 flex gap-3.5 text-[10px]" aria-hidden="true">
        <span className="flex items-center gap-[5px]">
          <i className="bg-brand inline-block size-[7px] rounded-full" />
          Data used
        </span>
        <span className="flex items-center gap-[5px]">
          <i className="bg-mint inline-block size-[7px] rounded-full" />
          Daily average
        </span>
      </div>

      <table className="sr-only">
        <caption>Data used per day, last {period} days</caption>
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">Data used</th>
          </tr>
        </thead>
        <tbody>
          {daily.map(([date, mb]) => (
            <tr key={date}>
              <th scope="row">{formatDay(date)}</th>
              <td>{formatData(mb)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
