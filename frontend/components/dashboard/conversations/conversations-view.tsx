'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  GlobeIcon,
  MessagesSquareIcon,
  PhoneIcon,
  Trash2Icon,
  XIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/dashboard/confirm-dialog';
import { PageHeader } from '@/components/dashboard/page-header';
import { StatusPill } from '@/components/dashboard/status-pill';
import {
  CONVERSATION_CHANNEL,
  CONVERSATION_STATUS,
  styleOf,
} from '@/components/dashboard/status-tones';
import { Panel, TableState } from '@/components/dashboard/table-state';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useLoad } from '@/hooks/useLoad';
import {
  type ConversationChannel,
  type ConversationListItem,
  type ConversationStatus,
  api,
} from '@/lib/api-client';
import { formatDateTime, formatDuration, formatRelative } from '@/lib/format';

const PAGE_SIZE = 25;

/** Icon + words for how a conversation happened: browser chat/voice or a real phone call. */
export function ChannelLabel({
  c,
}: {
  c: Pick<ConversationListItem, 'channel' | 'is_phone_call'>;
}) {
  const Icon = c.is_phone_call
    ? PhoneIcon
    : c.channel === 'inbound_chat'
      ? MessagesSquareIcon
      : GlobeIcon;
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <Icon className="text-muted-foreground size-3.5" aria-hidden="true" />
      {CONVERSATION_CHANNEL[c.channel] ?? c.channel}
      {c.is_phone_call && <span className="text-muted-foreground">(phone)</span>}
    </span>
  );
}

/** /dashboard/conversations. `?subscriber_id=` (from a subscriber's link) narrows it to one subscriber. */
export function ConversationsView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const subscriberId = searchParams.get('subscriber_id');

  const [channel, setChannel] = useState<ConversationChannel | 'all'>('all');
  const [status, setStatus] = useState<ConversationStatus | 'all'>('all');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const page = useLoad(
    () =>
      api.conversations.list({
        channel: channel === 'all' ? undefined : channel,
        status: status === 'all' ? undefined : status,
        subscriber_id: subscriberId ?? undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [channel, status, subscriberId, offset],
    { fallbackError: 'Could not load conversations.' }
  );
  const items = page.data?.items ?? [];
  const total = page.data?.total ?? 0;
  const filtered = channel !== 'all' || status !== 'all' || subscriberId !== null;
  const allOnPage = items.length > 0 && items.every((c) => selected.has(c.id));
  const someOnPage = items.some((c) => selected.has(c.id));

  function changeFilter(apply: () => void) {
    apply();
    setOffset(0);
    setSelected(new Set());
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function togglePage() {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const c of items) {
        if (allOnPage) next.delete(c.id);
        else next.add(c.id);
      }
      return next;
    });
  }

  async function bulkDelete() {
    setDeleting(true);
    try {
      const { deleted } = await api.conversations.bulkDelete(Array.from(selected));
      toast.success(deleted === 1 ? 'Conversation deleted' : `${deleted} conversations deleted`);
      setSelected(new Set());
      setConfirming(false);
      // Step back a page if this one is now empty.
      if (deleted >= items.length && offset > 0) setOffset(Math.max(0, offset - PAGE_SIZE));
      else void page.reload();
    } catch (err) {
      toast.error('Could not delete', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setDeleting(false);
    }
  }

  const subscriberName = subscriberId ? items[0]?.subscriber_name : null;

  return (
    <>
      <PageHeader
        title="Conversations"
        description="Every chat and call the agent has had, with full transcripts."
      />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          value={channel}
          onValueChange={(v) => changeFilter(() => setChannel(v as typeof channel))}
        >
          <SelectTrigger className="w-40" aria-label="Channel">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All channels</SelectItem>
            <SelectItem value="inbound_chat">Inbound chat</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={status}
          onValueChange={(v) => changeFilter(() => setStatus(v as typeof status))}
        >
          <SelectTrigger className="w-36" aria-label="Status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any status</SelectItem>
            <SelectItem value="active">Live</SelectItem>
            <SelectItem value="ended">Ended</SelectItem>
          </SelectContent>
        </Select>
        {subscriberId && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => changeFilter(() => router.replace(pathname, { scroll: false }))}
          >
            {subscriberName ? `Only ${subscriberName}` : 'One subscriber only'}
            <XIcon aria-hidden="true" />
            <span className="sr-only">Show everyone</span>
          </Button>
        )}

        {selected.size > 0 && (
          <div className="ml-auto flex items-center gap-2">
            <span className="text-muted-foreground text-sm">{selected.size} selected</span>
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
              Clear
            </Button>
            <Button variant="destructive" size="sm" onClick={() => setConfirming(true)}>
              <Trash2Icon aria-hidden="true" />
              Delete
            </Button>
          </div>
        )}
      </div>

      <Panel>
        {page.loading || page.error || items.length === 0 ? (
          <TableState
            loading={page.loading}
            error={page.error}
            onRetry={() => void page.retry()}
            empty={
              filtered ? (
                <>
                  <p className="text-foreground font-medium">No conversations match</p>
                  <p>Try another channel or status.</p>
                </>
              ) : (
                <>
                  <p className="text-foreground font-medium">No conversations yet</p>
                  <p>
                    Start a chat in the{' '}
                    <Link href="/" className="text-primary underline underline-offset-2">
                      customer portal
                    </Link>{' '}
                    and its transcript appears here.
                  </p>
                </>
              )
            }
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    checked={allOnPage ? true : someOnPage ? 'indeterminate' : false}
                    onCheckedChange={togglePage}
                    aria-label="Select every conversation on this page"
                  />
                </TableHead>
                <TableHead className="w-full min-w-60">Who</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead className="text-right">Messages</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Length</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((c) => {
                const st = styleOf(CONVERSATION_STATUS, c.status);
                return (
                  <TableRow key={c.id} data-state={selected.has(c.id) ? 'selected' : undefined}>
                    <TableCell>
                      <Checkbox
                        checked={selected.has(c.id)}
                        onCheckedChange={() => toggle(c.id)}
                        aria-label={`Select conversation with ${c.subscriber_name ?? 'Guest'}`}
                      />
                    </TableCell>
                    <TableCell className="max-w-0 py-2.5">
                      <Link
                        href={`/dashboard/conversations/${c.id}`}
                        className="group focus-visible:ring-ring/50 block min-w-0 rounded-sm outline-none focus-visible:ring-[3px]"
                      >
                        <span className="block truncate font-medium group-hover:underline group-hover:underline-offset-2">
                          {c.subscriber_name ?? 'Guest'}
                        </span>
                        <span className="text-muted-foreground block truncate text-xs">
                          {c.preview ?? 'No messages'}
                        </span>
                      </Link>
                    </TableCell>
                    <TableCell>
                      <ChannelLabel c={c} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{c.message_count}</TableCell>
                    <TableCell
                      className="text-muted-foreground whitespace-nowrap"
                      title={formatDateTime(c.started_at)}
                    >
                      {formatRelative(c.started_at)}
                    </TableCell>
                    <TableCell className="text-muted-foreground whitespace-nowrap tabular-nums">
                      {c.ended_at ? formatDuration(c.started_at, c.ended_at) : '—'}
                    </TableCell>
                    <TableCell>
                      <StatusPill tone={st.tone} pulse={st.pulse}>
                        {st.label}
                      </StatusPill>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Panel>

      {total > PAGE_SIZE && (
        <nav
          aria-label="Pages"
          className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm"
        >
          <p className="text-muted-foreground tabular-nums">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0 || page.loading}
            >
              <ChevronLeftIcon aria-hidden="true" />
              Newer
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total || page.loading}
            >
              Older
              <ChevronRightIcon aria-hidden="true" />
            </Button>
          </div>
        </nav>
      )}

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={
          selected.size === 1
            ? 'Delete this conversation?'
            : `Delete ${selected.size} conversations?`
        }
        description="Their transcripts are removed for good. Cases and transactions stay."
        confirmLabel={selected.size === 1 ? 'Delete conversation' : 'Delete conversations'}
        onConfirm={bulkDelete}
        busy={deleting}
      />
    </>
  );
}
