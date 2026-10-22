'use client';

import Link from 'next/link';
import {
  BuildingIcon,
  CalendarCheckIcon,
  LibraryBigIcon,
  MessagesSquareIcon,
  PhoneIcon,
  PhoneOutgoingIcon,
  UsersIcon,
} from 'lucide-react';
import { KpiTile, KpiTileSkeleton } from '@/components/dashboard/kpi-tile';
import { ConversationsChartPanel } from '@/components/dashboard/overview/conversations-chart-panel';
import { KbStatusPanel } from '@/components/dashboard/overview/kb-status-panel';
import { PageHeader } from '@/components/dashboard/page-header';
import { SectionCard } from '@/components/dashboard/section-card';
import { StatusPill } from '@/components/dashboard/status-pill';
import {
  BOOKING_STATUS,
  CONVERSATION_CHANNEL,
  CONVERSATION_STATUS,
  styleOf,
} from '@/components/dashboard/status-tones';
import { TableState } from '@/components/dashboard/table-state';
import { useLoad } from '@/hooks/useLoad';
import { api } from '@/lib/api-client';
import { formatDateTime, formatRelative } from '@/lib/format';

export function OverviewView() {
  return (
    <>
      <PageHeader title="Overview" description="What the agent and your team have on today." />
      <div className="space-y-4 sm:space-y-6">
        <KpiRow />
        <div className="grid gap-4 sm:gap-6 lg:grid-cols-3">
          <ConversationsChartPanel className="lg:col-span-2" />
          <KbStatusPanel />
        </div>
        <div className="grid gap-4 sm:gap-6 lg:grid-cols-2">
          <RecentConversationsPanel />
          <RecentBookingsPanel />
        </div>
      </div>
    </>
  );
}

function KpiRow() {
  const {
    data: summary,
    error,
    loading,
    retry,
  } = useLoad(() => api.dashboard.summary(), [], {
    fallbackError: 'Could not load the numbers.',
  });

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <KpiTileSkeleton key={i} />
        ))}
      </div>
    );
  }

  const value = (pick: (s: NonNullable<typeof summary>) => number | string) =>
    summary && !error ? pick(summary) : null;

  return (
    <div>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3">
        <KpiTile
          label="Leads"
          icon={UsersIcon}
          value={value((s) => s.total_leads)}
          href="/dashboard/leads"
        />
        <KpiTile
          label="Conversations today"
          icon={MessagesSquareIcon}
          value={value((s) => s.conversations_today)}
          href="/dashboard/conversations"
        />
        <KpiTile
          label="Calls left today"
          icon={PhoneOutgoingIcon}
          value={value((s) => s.pending_calls_today)}
          href="/dashboard/schedule"
        />
        <KpiTile
          label="Bookings this week"
          icon={CalendarCheckIcon}
          value={value((s) => s.bookings_this_week)}
          href="/dashboard/bookings"
        />
        <KpiTile
          label="Active listings"
          icon={BuildingIcon}
          value={value((s) => s.active_listings)}
          href="/dashboard/properties"
        />
        <KpiTile
          label="Knowledge sources"
          icon={LibraryBigIcon}
          value={value((s) => `${s.kb_sources_ready}/${s.kb_sources_total}`)}
          sublabel="ready to search"
          href="/dashboard/knowledge"
          emphasize={!!summary && !error && summary.kb_sources_ready < summary.kb_sources_total}
        />
      </div>
      {error && (
        <p className="text-muted-foreground mt-2 text-sm" role="alert">
          {error}{' '}
          <button
            type="button"
            onClick={() => void retry()}
            className="text-primary font-medium underline-offset-2 hover:underline"
          >
            Try again
          </button>
        </p>
      )}
    </div>
  );
}

function RecentConversationsPanel() {
  const { data, error, loading, retry } = useLoad(() => api.dashboard.recentConversations(6), [], {
    fallbackError: 'Could not load recent conversations.',
  });

  return (
    <SectionCard
      title="Recent conversations"
      action={<ViewAll href="/dashboard/conversations" label="View all conversations" />}
      bodyClassName="px-0 sm:px-0 pb-1 sm:pb-1"
    >
      {loading || error || !data || data.length === 0 ? (
        <TableState
          loading={loading}
          error={error}
          onRetry={() => void retry()}
          rows={4}
          empty={
            <>
              <p className="text-foreground font-medium">No conversations yet</p>
              <p>Chats and calls show up here as soon as someone talks to the agent.</p>
            </>
          }
        />
      ) : (
        <ul className="divide-y">
          {data.map((c) => {
            const status = styleOf(CONVERSATION_STATUS, c.status);
            return (
              <li key={c.id}>
                <Link
                  href={`/dashboard/conversations/${c.id}`}
                  className="hover:bg-accent/60 focus-visible:bg-accent/60 flex items-start gap-3 px-4 py-3 outline-none sm:px-5"
                >
                  <span className="bg-secondary text-secondary-foreground mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full">
                    {c.is_phone_call ? (
                      <PhoneIcon className="size-4" aria-hidden="true" />
                    ) : (
                      <MessagesSquareIcon className="size-4" aria-hidden="true" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">
                        {c.client_name ?? 'Visitor'}
                      </span>
                      {c.status === 'active' && (
                        <StatusPill tone={status.tone} pulse={status.pulse}>
                          {status.label}
                        </StatusPill>
                      )}
                    </span>
                    <span className="text-muted-foreground block truncate text-sm">
                      {c.preview ?? 'No messages yet'}
                    </span>
                  </span>
                  <span className="text-muted-foreground shrink-0 text-right text-xs">
                    <span className="block">{formatRelative(c.started_at)}</span>
                    <span className="block">{CONVERSATION_CHANNEL[c.channel] ?? c.channel}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}

function RecentBookingsPanel() {
  const { data, error, loading, retry } = useLoad(() => api.dashboard.recentBookings(6), [], {
    fallbackError: 'Could not load recent bookings.',
  });

  return (
    <SectionCard
      title="Recent bookings"
      action={<ViewAll href="/dashboard/bookings" label="View all bookings" />}
      bodyClassName="px-0 sm:px-0 pb-1 sm:pb-1"
    >
      {loading || error || !data || data.length === 0 ? (
        <TableState
          loading={loading}
          error={error}
          onRetry={() => void retry()}
          rows={4}
          empty={
            <>
              <p className="text-foreground font-medium">No viewings booked yet</p>
              <p>When a lead agrees to a viewing, the agent records it here.</p>
            </>
          }
        />
      ) : (
        <ul className="divide-y">
          {data.map((b) => {
            const status = styleOf(BOOKING_STATUS, b.status);
            return (
              <li key={b.id} className="flex items-start gap-3 px-4 py-3 sm:px-5">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {b.client_name ?? 'Unknown lead'}
                  </span>
                  <span className="text-muted-foreground block truncate text-sm">
                    {b.property_title ?? 'No listing picked'}
                  </span>
                </span>
                <span className="flex shrink-0 flex-col items-end gap-1">
                  <StatusPill tone={status.tone}>{status.label}</StatusPill>
                  <span className="text-muted-foreground text-xs tabular-nums">
                    {formatDateTime(b.proposed_datetime)}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}

function ViewAll({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      aria-label={label}
      className="text-primary focus-visible:ring-ring/50 rounded-sm text-sm font-medium underline-offset-4 outline-none hover:underline focus-visible:ring-[3px]"
    >
      View all
    </Link>
  );
}
