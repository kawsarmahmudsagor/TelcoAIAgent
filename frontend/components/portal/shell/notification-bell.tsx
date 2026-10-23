'use client';

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { useRouter } from 'next/navigation';
import {
  BellIcon,
  CheckCheckIcon,
  GaugeIcon,
  LifeBuoyIcon,
  PackageIcon,
  WalletIcon,
} from 'lucide-react';
import { Popover } from 'radix-ui';
import { toast } from 'sonner';
import { useOptionalChatBubble } from '@/components/chat-bubble/chat-bubble-context';
import { IconTile, type IconTileTone } from '@/components/portal/ui/icon-tile';
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet';
import { portalApi } from '@/lib/portal-api';
import { invalidatePortal, usePortalQuery } from '@/lib/portal-sync';
import { cn } from '@/lib/shadcn/utils';
import { formatAge } from '@/lib/telco-format';
import type { NotificationKind, NotificationView } from '@/lib/types/portal';

const POLL_MS = 60_000;
const PHONE_QUERY = '(max-width: 760px)';

const KINDS: Record<NotificationKind, { icon: typeof PackageIcon; tone: IconTileTone }> = {
  pack_expiring: { icon: PackageIcon, tone: 'orange' },
  low_balance: { icon: WalletIcon, tone: 'pink' },
  low_data: { icon: GaugeIcon, tone: 'purple' },
  case_update: { icon: LifeBuoyIcon, tone: 'green' },
};

function subscribePhone(onChange: () => void) {
  const query = window.matchMedia(PHONE_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}
const isPhone = () => window.matchMedia(PHONE_QUERY).matches;
const notPhoneOnServer = () => false;

function badgeText(unread: number): string {
  return unread > 9 ? '9+' : String(unread);
}

/**
 * The topbar's bell: unread count, and a list of the proactive nudges (a popover; a bottom sheet
 * on phones). Opening one marks it read and starts an assistant chat that opens with it.
 */
export function NotificationBell({ buttonClassName }: { buttonClassName: string }) {
  const router = useRouter();
  const bubble = useOptionalChatBubble();
  const phone = useSyncExternalStore(subscribePhone, isPhone, notPhoneOnServer);
  const [open, setOpen] = useState(false);
  const { data, reload } = usePortalQuery('notifications', portalApi.notifications);
  const unread = data?.unread ?? 0;
  const items = data?.items;

  // The agent's account_changed topic already invalidates every portal query (this one too);
  // the poll covers nudges that arrive while no session is up.
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === 'visible') reload();
    };
    const timer = window.setInterval(refresh, POLL_MS);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [reload]);

  const openNotification = useCallback(
    async (item: NotificationView) => {
      setOpen(false);
      if (!item.read_at) {
        try {
          await portalApi.markNotificationRead(item.id);
        } catch {
          toast.error('Could not mark that as read', { description: 'It will show again.' });
        }
        invalidatePortal(['notifications']);
      }
      if (bubble) void bubble.startNudgeSession(item.id);
      router.push('/portal/assistant');
    },
    [bubble, router]
  );

  const markAllRead = useCallback(async () => {
    try {
      await portalApi.markAllNotificationsRead();
    } catch {
      toast.error('Could not mark all as read', { description: 'Try again in a moment.' });
    }
    invalidatePortal(['notifications']);
  }, []);

  const trigger = (
    <button
      type="button"
      aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
      aria-haspopup="dialog"
      aria-expanded={open}
      onClick={phone ? () => setOpen(true) : undefined}
      className={cn(
        buttonClassName,
        'focus-visible:ring-ring/60 relative grid place-items-center outline-none focus-visible:ring-[3px]'
      )}
    >
      <BellIcon className="size-[18px]" aria-hidden="true" />
      {unread > 0 && (
        <span
          aria-hidden="true"
          className="bg-red absolute -top-1.5 -right-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full px-1 text-[10px] leading-none font-extrabold text-white"
        >
          {badgeText(unread)}
        </span>
      )}
    </button>
  );

  const list = (
    <NotificationList
      items={items}
      unread={unread}
      onOpen={openNotification}
      onMarkAllRead={markAllRead}
    />
  );

  if (phone) {
    return (
      <>
        {trigger}
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent
            side="bottom"
            className="bg-surface max-h-[80dvh] gap-0 rounded-t-[17px] pb-[env(safe-area-inset-bottom)]"
          >
            <SheetTitle className="sr-only">Notifications</SheetTitle>
            <SheetDescription className="sr-only">Updates about your account</SheetDescription>
            {list}
          </SheetContent>
        </Sheet>
      </>
    );
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>{trigger}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          aria-label="Notifications"
          className="bg-surface border-line text-foreground data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 z-50 flex max-h-[min(520px,var(--radix-popover-content-available-height))] w-[380px] flex-col overflow-hidden rounded-[17px] border shadow-lg outline-none"
        >
          {list}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function NotificationList({
  items,
  unread,
  onOpen,
  onMarkAllRead,
}: {
  items: NotificationView[] | undefined;
  unread: number;
  onOpen: (item: NotificationView) => void;
  onMarkAllRead: () => void;
}) {
  // Ages are fixed for as long as the list is open; reopening remounts it.
  const [now] = useState(() => new Date());
  return (
    <div className="flex min-h-0 flex-col">
      <div className="border-line phone:pr-12 flex items-center justify-between gap-3 border-b px-4 py-3">
        <p className="text-[15px] font-extrabold tracking-[-0.2px]">Notifications</p>
        <button
          type="button"
          onClick={onMarkAllRead}
          disabled={unread === 0}
          className="text-brand-text focus-visible:ring-ring/60 -mr-1 flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-bold outline-none hover:underline focus-visible:ring-[3px] disabled:pointer-events-none disabled:opacity-40"
        >
          <CheckCheckIcon className="size-3.5" aria-hidden="true" />
          Mark all read
        </button>
      </div>
      {items === undefined ? (
        <p className="text-muted-foreground px-4 py-8 text-center text-sm">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-muted-foreground px-4 py-8 text-center text-sm">
          You&apos;re all caught up. Reminders about packs, balance and your cases show up here.
        </p>
      ) : (
        <ul className="min-h-0 flex-1 overflow-y-auto">
          {items.map((item) => {
            const kind = KINDS[item.kind];
            const age = formatAge(item.created_at, now);
            return (
              <li key={item.id} className="border-line border-b last:border-b-0">
                <button
                  type="button"
                  onClick={() => onOpen(item)}
                  className="hover:bg-surface2 focus-visible:ring-ring/60 flex w-full items-start gap-3 px-4 py-3 text-left outline-none focus-visible:ring-[3px] focus-visible:ring-inset"
                >
                  <IconTile icon={kind.icon} tone={kind.tone} size="lg" />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span
                        className={cn(
                          'truncate text-[13.5px]',
                          item.read_at ? 'font-semibold' : 'font-extrabold'
                        )}
                      >
                        {item.title}
                      </span>
                      <span className="text-muted-foreground shrink-0 text-[11px]">
                        {age === 'just now' ? age : `${age} ago`}
                      </span>
                    </span>
                    <span className="text-muted-foreground mt-0.5 line-clamp-2 block text-xs leading-snug">
                      {item.body}
                    </span>
                  </span>
                  {!item.read_at && (
                    <span
                      role="img"
                      aria-label="Unread"
                      className="bg-brand mt-1.5 size-2 shrink-0 rounded-full"
                    />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
