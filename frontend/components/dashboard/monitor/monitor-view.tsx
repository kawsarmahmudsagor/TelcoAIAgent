'use client';

import { useState } from 'react';
import {
  GaugeIcon,
  MessagesSquareIcon,
  ShieldCheckIcon,
  TimerIcon,
  WrenchIcon,
} from 'lucide-react';
import { SegmentedFilter } from '@/components/dashboard/list-controls';
import { AuditTable } from '@/components/dashboard/monitor/audit-table';
import { useUrlParams } from '@/components/dashboard/use-url-param';
import { PortalButton, SmallLink } from '@/components/portal/ui/link-button';
import { MetricTile } from '@/components/portal/ui/metric-tile';
import { Panel, PanelHeader } from '@/components/portal/ui/panel';
import { ProgressBar } from '@/components/portal/ui/progress-bar';
import { Bone, LoadError } from '@/components/portal/ui/query-states';
import { StatusChip, type StatusTone } from '@/components/portal/ui/status-chip';
import { adminApi } from '@/lib/admin-api';
import { useAdminQuery } from '@/lib/admin-query';
import { cn } from '@/lib/shadcn/utils';
import { formatDayTime } from '@/lib/telco-format';
import type { AiMonitorWindow } from '@/lib/types/admin';

const AUDIT_PREVIEW = 10;
const nf = new Intl.NumberFormat('en-IN');
const WINDOWS: { value: AiMonitorWindow; label: string }[] = [
  { value: '24h', label: '24 h' },
  { value: '7d', label: '7 d' },
];

const percent = (rate: number) => `${Math.round(rate * 1000) / 10}%`;
const seconds = (s: number | null) => (s === null ? '—' : `${s.toFixed(1)} s`);

const GUARDRAILS: { title: string; note: string; tone: StatusTone; state: string }[] = [
  {
    title: 'OTP required for writes',
    note: 'Purchases, recharges and redemptions need a one-time code from the subscriber.',
    tone: 'success',
    state: 'On',
  },
  {
    title: 'Payments',
    note: 'Demo transaction flow; no real payment gateway is connected.',
    tone: 'pending',
    state: 'Simulated',
  },
  {
    title: 'Support case creation',
    note: 'The assistant opens a case with an audit event.',
    tone: 'success',
    state: 'On',
  },
  {
    title: 'Human hand-off',
    note: 'Opens a support case for staff; there is no live transfer.',
    tone: 'open',
    state: 'Case only',
  },
];

export function MonitorView() {
  const [params, setParams] = useUrlParams();
  const range: AiMonitorWindow = params.get('window') === '7d' ? '7d' : '24h';
  const { data, error, loading, reload } = useAdminQuery(
    'monitor',
    () => adminApi.aiMonitor(range),
    [range]
  );
  const [showAllAudit, setShowAllAudit] = useState(false);
  const m = data?.metrics;
  const label = range === '24h' ? '24 hours' : '7 days';
  const stale = loading && data !== undefined;

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="phone:text-[23px] text-[25px] font-bold tracking-[-0.8px]">AI monitor</h1>
          <p className="text-muted-foreground mt-1 text-xs">
            How the assistant is doing: quality, speed, the tools it used and what it changed.
          </p>
        </div>
        <SegmentedFilter
          label="Time window"
          value={range}
          options={WINDOWS}
          onChange={(v) => setParams({ window: v === '24h' ? null : v })}
        />
      </div>

      {error && !data ? (
        <Panel>
          <LoadError what="The AI monitor" error={error} onRetry={reload} />
        </Panel>
      ) : (
        <div className={cn(stale && 'opacity-60 motion-safe:transition-opacity')} aria-busy={stale}>
          <div className="tablet:grid-cols-2 mb-4 grid grid-cols-4 gap-4">
            <MetricTile
              icon={MessagesSquareIcon}
              tone="purple"
              label={`Chats · ${label}`}
              value={m ? nf.format(m.chats) : <Bone className="h-7 w-16" />}
              foot={m && `${nf.format(m.turns)} ${m.turns === 1 ? 'turn' : 'turns'}`}
            />
            <MetricTile
              icon={ShieldCheckIcon}
              tone="green"
              label="Resolution rate"
              value={
                m ? m.chats === 0 ? '—' : percent(m.resolution_rate) : <Bone className="h-7 w-16" />
              }
              foot={m && 'Chats that did not need a human'}
            />
            <MetricTile
              icon={TimerIcon}
              tone="orange"
              label="Median first response"
              value={m ? seconds(m.median_first_response_s) : <Bone className="h-7 w-16" />}
              foot={m && `p95: ${seconds(m.p95_first_response_s)}`}
            />
            <MetricTile
              icon={WrenchIcon}
              tone="pink"
              label="Fallback rate"
              value={
                m ? m.turns === 0 ? '—' : percent(m.fallback_rate) : <Bone className="h-7 w-16" />
              }
              foot={m && 'Turns answered without a tool'}
            />
          </div>

          <div className="tablet:grid-cols-1 mb-4 grid grid-cols-2 gap-4">
            <Panel>
              <PanelHeader
                title="Most common intents"
                description="Share of the assistant's tool calls"
              />
              {!m ? (
                <Bone className="h-32 w-full" />
              ) : m.intents.length === 0 ? (
                <p className="text-muted-foreground text-xs">
                  No tool calls in this window yet. Intents appear once subscribers chat.
                </p>
              ) : (
                <ul className="space-y-3.5">
                  {m.intents.map((i) => (
                    <li key={i.label}>
                      <div className="flex items-baseline justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-xs font-bold">{i.label}</p>
                          <p className="text-muted-foreground text-[11px]">
                            {nf.format(i.count)} {i.count === 1 ? 'call' : 'calls'}
                          </p>
                        </div>
                        <p className="text-sm font-extrabold tabular-nums">{percent(i.share)}</p>
                      </div>
                      <ProgressBar value={i.share * 100} label={`${i.label} share`} />
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel>
              <PanelHeader
                title="Quality review queue"
                description="Chats with two or more turns answered without a tool"
              />
              {!data ? (
                <Bone className="h-32 w-full" />
              ) : data.review_queue.length === 0 ? (
                <p className="text-muted-foreground text-xs">Nothing to review in this window.</p>
              ) : (
                <ul>
                  {data.review_queue.map((r) => (
                    <li
                      key={r.conversation_id}
                      className="border-line border-b py-3 first:pt-0 last:border-b-0 last:pb-0"
                    >
                      <p className="text-xs font-bold">
                        {r.subscriber_name ?? 'Anonymous visitor'} · {r.no_tool_turns} turns without
                        a tool
                      </p>
                      <p className="text-muted-foreground mt-0.5 line-clamp-2 text-[11px]">
                        “{r.preview}”
                      </p>
                      <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                        <span className="text-muted-foreground text-[10px]">
                          {formatDayTime(r.started_at)}
                        </span>
                        <SmallLink href={`/dashboard/conversations/${r.conversation_id}`}>
                          Review transcript
                        </SmallLink>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <Panel className="mb-4">
            <PanelHeader
              title="Audit trail"
              description="Everything the assistant, subscribers and admins changed, newest first"
            />
            {!data ? (
              <div className="space-y-3" aria-busy="true">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Bone key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : data.audit_trail.length === 0 ? (
              <p className="text-muted-foreground text-xs">No activity recorded yet.</p>
            ) : (
              <>
                <AuditTable
                  items={showAllAudit ? data.audit_trail : data.audit_trail.slice(0, AUDIT_PREVIEW)}
                />
                {data.audit_trail.length > AUDIT_PREVIEW && (
                  <PortalButton
                    variant="outline"
                    className="mt-4"
                    aria-expanded={showAllAudit}
                    onClick={() => setShowAllAudit((v) => !v)}
                  >
                    {showAllAudit ? 'Show fewer' : `Show all ${data.audit_trail.length} events`}
                  </PortalButton>
                )}
              </>
            )}
          </Panel>

          <Panel>
            <PanelHeader
              title="Guardrails & tools"
              description="How this environment limits what the assistant can do"
              action={<GaugeIcon className="text-muted-foreground size-4" aria-hidden="true" />}
            />
            <ul>
              {GUARDRAILS.map((g) => (
                <li
                  key={g.title}
                  className="border-line flex items-center justify-between gap-3 border-b py-3 first:pt-0 last:border-b-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-bold">{g.title}</p>
                    <p className="text-muted-foreground text-[11px]">{g.note}</p>
                  </div>
                  <StatusChip tone={g.tone}>{g.state}</StatusChip>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      )}
    </>
  );
}
