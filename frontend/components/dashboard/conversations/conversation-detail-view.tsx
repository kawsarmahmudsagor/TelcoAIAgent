'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeftIcon, ChevronRightIcon, Trash2Icon, WrenchIcon } from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/dashboard/confirm-dialog';
import { PageHeader } from '@/components/dashboard/page-header';
import { SectionCard } from '@/components/dashboard/section-card';
import { StatusPill } from '@/components/dashboard/status-pill';
import { CONVERSATION_STATUS, styleOf } from '@/components/dashboard/status-tones';
import { Panel, TableState } from '@/components/dashboard/table-state';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useLoad } from '@/hooks/useLoad';
import { ApiError, type ConversationDetail, type ConversationMessage, api } from '@/lib/api-client';
import { formatDateTime, formatDuration } from '@/lib/format';
import { cn } from '@/lib/shadcn/utils';
import { ChannelLabel } from './conversations-view';

const LIVE_POLL_MS = 4000;

const timeOnly = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });

export function ConversationDetailView({ id }: { id: string }) {
  const router = useRouter();
  const [live, setLive] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [notFound, setNotFound] = useState(false);

  const detail = useLoad(
    async () => {
      try {
        const result = await api.conversations.get(id);
        // Follow a live conversation as it happens.
        setLive(result.status === 'active');
        return result;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) setNotFound(true);
        throw err;
      }
    },
    [id],
    { pollMs: live ? LIVE_POLL_MS : null, fallbackError: 'Could not load this conversation.' }
  );

  async function remove() {
    setDeleting(true);
    try {
      await api.conversations.delete(id);
      toast.success('Conversation deleted');
      router.push('/dashboard/conversations');
    } catch (err) {
      toast.error('Could not delete', {
        description: err instanceof Error ? err.message : undefined,
      });
      setDeleting(false);
    }
  }

  const back = (
    <Link
      href="/dashboard/conversations"
      className="text-muted-foreground hover:text-foreground mb-3 inline-flex items-center gap-1.5 text-sm"
    >
      <ArrowLeftIcon className="size-4" aria-hidden="true" />
      All conversations
    </Link>
  );

  if (detail.loading) {
    return (
      <>
        {back}
        <div className="grid gap-6 lg:grid-cols-3" aria-busy="true" aria-label="Loading">
          <Skeleton className="h-96 lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </>
    );
  }

  if (!detail.data) {
    return (
      <>
        {back}
        <PageHeader title="Conversation" />
        <Panel>
          {notFound ? (
            <TableState
              empty={
                <>
                  <p className="text-foreground font-medium">This conversation doesn’t exist</p>
                  <p>It may have been deleted.</p>
                </>
              }
            />
          ) : (
            <TableState error={detail.error} onRetry={() => void detail.retry()} />
          )}
        </Panel>
      </>
    );
  }

  const c = detail.data;
  const name = c.client_name ?? 'Visitor';

  return (
    <>
      {back}
      <PageHeader
        title={`Conversation with ${name}`}
        description={formatDateTime(c.started_at)}
        actions={
          <Button variant="outline" onClick={() => setConfirming(true)}>
            <Trash2Icon aria-hidden="true" />
            Delete
          </Button>
        }
      />

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-3">
        <MetaCard c={c} className="lg:order-2 lg:self-start" />
        <SectionCard
          title="Transcript"
          className="lg:order-1 lg:col-span-2"
          action={
            c.status === 'active' ? (
              <StatusPill tone="success" pulse>
                Live, updating
              </StatusPill>
            ) : undefined
          }
        >
          {c.messages.length === 0 ? (
            <p className="text-muted-foreground py-8 text-center text-sm">
              Nothing was said in this conversation.
            </p>
          ) : (
            <ol className="grid gap-3" aria-label="Messages, oldest first">
              {c.messages.map((m) => (
                <Message key={m.id} m={m} agentLabel="Agent" customerLabel={name} />
              ))}
            </ol>
          )}
        </SectionCard>
      </div>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Delete this conversation?"
        description="The transcript is removed for good. The lead and any booking stay."
        confirmLabel="Delete conversation"
        onConfirm={remove}
        busy={deleting}
      />
    </>
  );
}

function Message({
  m,
  agentLabel,
  customerLabel,
}: {
  m: ConversationMessage;
  agentLabel: string;
  customerLabel: string;
}) {
  if (m.role === 'tool') return <ToolRow m={m} />;
  const fromAgent = m.role === 'assistant';
  return (
    <li className={cn('flex flex-col gap-1', fromAgent ? 'items-end' : 'items-start')}>
      <span className="text-muted-foreground px-1 text-xs">
        {fromAgent ? agentLabel : customerLabel}
        <span className="sr-only">, </span>
        <time dateTime={m.created_at} className="ml-2 tabular-nums">
          {timeOnly.format(new Date(m.created_at))}
        </time>
      </span>
      <p
        className={cn(
          'max-w-[85%] rounded-xl px-3.5 py-2 text-sm leading-relaxed whitespace-pre-wrap sm:max-w-[75%]',
          fromAgent
            ? 'bg-primary text-primary-foreground rounded-br-sm'
            : 'bg-secondary text-secondary-foreground rounded-bl-sm'
        )}
      >
        {m.text}
      </p>
    </li>
  );
}

/** A tool the agent ran, collapsed to one line; expands to its arguments and result. */
function ToolRow({ m }: { m: ConversationMessage }) {
  const args = m.tool_args && Object.keys(m.tool_args).length > 0 ? m.tool_args : null;
  return (
    <li>
      <details className="group bg-muted/40 rounded-md border border-dashed text-sm">
        <summary className="focus-visible:ring-ring/50 flex cursor-pointer list-none items-center gap-2 rounded-md px-3 py-1.5 outline-none focus-visible:ring-[3px] [&::-webkit-details-marker]:hidden">
          <ChevronRightIcon
            className="text-muted-foreground size-3.5 shrink-0 transition-transform group-open:rotate-90"
            aria-hidden="true"
          />
          <WrenchIcon className="text-muted-foreground size-3.5 shrink-0" aria-hidden="true" />
          <span className="text-muted-foreground">Used</span>
          <span className="truncate font-mono text-xs">{m.tool_name ?? 'a tool'}</span>
          <time
            dateTime={m.created_at}
            className="text-muted-foreground ml-auto shrink-0 text-xs tabular-nums"
          >
            {timeOnly.format(new Date(m.created_at))}
          </time>
        </summary>
        <div className="grid gap-2 border-t border-dashed px-3 py-2">
          {args && (
            <div>
              <p className="text-muted-foreground mb-1 text-xs">Arguments</p>
              <pre className="bg-card overflow-x-auto rounded border p-2 font-mono text-xs">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}
          {m.text && (
            <div>
              <p className="text-muted-foreground mb-1 text-xs">Result</p>
              <pre className="bg-card max-h-48 overflow-auto rounded border p-2 font-mono text-xs whitespace-pre-wrap">
                {m.text}
              </pre>
            </div>
          )}
          {!args && !m.text && (
            <p className="text-muted-foreground text-xs">No details recorded.</p>
          )}
        </div>
      </details>
    </li>
  );
}

function MetaCard({ c, className }: { c: ConversationDetail; className?: string }) {
  const st = styleOf(CONVERSATION_STATUS, c.status);
  const toolCount = c.messages.filter((m) => m.role === 'tool').length;
  return (
    <SectionCard title="Details" className={className}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm lg:grid-cols-1">
        <Item label="Status">
          <StatusPill tone={st.tone} pulse={st.pulse}>
            {st.label}
          </StatusPill>
        </Item>
        <Item label="Channel">
          <ChannelLabel c={c} />
        </Item>
        <Item label="Started">{formatDateTime(c.started_at)}</Item>
        <Item label="Length">
          {c.ended_at ? formatDuration(c.started_at, c.ended_at) : 'Still going'}
        </Item>
        <Item label="Messages">
          {/* message_count includes tool rows; count what was said. */}
          {Math.max(0, c.message_count - toolCount)}
          {toolCount > 0 && (
            <span className="text-muted-foreground">
              {' '}
              and {toolCount} tool {toolCount === 1 ? 'call' : 'calls'}
            </span>
          )}
        </Item>
        {c.room_name && (
          <Item label="Room">
            <span className="font-mono text-xs break-all">{c.room_name}</span>
          </Item>
        )}
      </dl>

      <div className="mt-4 border-t pt-4">
        <h3 className="mb-2 text-sm font-semibold">Lead</h3>
        {c.client_id ? (
          <div className="grid gap-1 text-sm">
            <p className="font-medium">{c.client_name ?? 'Unnamed lead'}</p>
            {c.client_phone && (
              <p className="text-muted-foreground tabular-nums">{c.client_phone}</p>
            )}
            {c.client_email && <p className="text-muted-foreground break-all">{c.client_email}</p>}
            <div className="mt-2 flex flex-wrap gap-2">
              <Button asChild size="sm" variant="outline">
                <Link href={`/dashboard/leads#lead-${c.client_id}`}>Open lead</Link>
              </Button>
              <Button asChild size="sm" variant="ghost">
                <Link href={`/dashboard/conversations?client_id=${c.client_id}`}>
                  Their conversations
                </Link>
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">
            Not linked to a lead. A lead is linked when the agent books a viewing.
          </p>
        )}
      </div>
    </SectionCard>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}
