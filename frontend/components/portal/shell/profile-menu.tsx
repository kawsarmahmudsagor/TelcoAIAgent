'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ChevronDownIcon, LogOutIcon, ShieldCheckIcon, UsersRoundIcon } from 'lucide-react';
import { toast } from 'sonner';
import { usePortalMe } from '@/components/portal/portal-me-context';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { portalApi } from '@/lib/portal-api';
import { cn } from '@/lib/shadcn/utils';
import { formatPlan, initials } from '@/lib/telco-format';

/**
 * Ends the portal session and returns to the persona picker. "Switch persona" and "Log out" both
 * use it. The AI assistant (Task 10) extends `logOut` to end its LiveKit session first.
 */
export function usePortalLogout(): { logOut: () => Promise<void>; loggingOut: boolean } {
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);

  const logOut = useCallback(async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await portalApi.logout();
      router.push('/');
    } catch {
      toast.error('Log out did not go through', {
        description: 'Check your connection and try again.',
      });
      setLoggingOut(false);
    }
  }, [loggingOut, router]);

  return { logOut, loggingOut };
}

/** The reference's round gradient avatar with the customer's initials. */
export function ProfileAvatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'grid size-[34px] shrink-0 place-items-center rounded-full bg-linear-135 from-[#f4b58e] to-[#dd6c8d] text-xs font-extrabold text-white',
        className
      )}
    >
      {initials(name)}
    </span>
  );
}

/**
 * The customer's menu: switch persona, the admin dashboard, log out. `avatar` is the topbar's
 * round button; `row` is the sidebar's profile row (avatar, name, masked number and plan).
 */
export function ProfileMenu({ variant }: { variant: 'avatar' | 'row' }) {
  const me = usePortalMe();
  const { logOut, loggingOut } = usePortalLogout();
  const meta = `${me.masked_msisdn} · ${formatPlan(me.plan_type)}`;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`Account menu for ${me.full_name}`}
        className={cn(
          'focus-visible:ring-ring/60 outline-none focus-visible:ring-[3px]',
          variant === 'avatar'
            ? 'rounded-full'
            : 'hover:bg-surface2 flex w-full min-w-0 items-center gap-2.5 rounded-[11px] px-[5px] py-1.5 text-left motion-safe:transition-colors'
        )}
      >
        {variant === 'avatar' ? (
          <ProfileAvatar name={me.full_name} className="size-9 text-[11px]" />
        ) : (
          <>
            <ProfileAvatar name={me.full_name} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-bold">{me.full_name}</span>
              <span className="text-muted-foreground block truncate text-[10px]">{meta}</span>
            </span>
            <ChevronDownIcon className="text-muted-foreground size-4 shrink-0" aria-hidden="true" />
          </>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" side={variant === 'row' ? 'top' : 'bottom'} className="w-56">
        <DropdownMenuLabel className="font-normal">
          <span className="block truncate text-sm font-semibold">{me.full_name}</span>
          <span className="text-muted-foreground block truncate text-xs">{meta}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={loggingOut} onSelect={() => void logOut()}>
          <UsersRoundIcon aria-hidden="true" />
          Switch persona
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/login">
            <ShieldCheckIcon aria-hidden="true" />
            Admin
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={loggingOut} onSelect={() => void logOut()}>
          <LogOutIcon aria-hidden="true" />
          {loggingOut ? 'Logging out…' : 'Log out'}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
