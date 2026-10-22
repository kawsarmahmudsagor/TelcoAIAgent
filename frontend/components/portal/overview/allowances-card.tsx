import { ArrowUpRightIcon, MessageSquareTextIcon, PhoneIcon, WifiIcon } from 'lucide-react';
import { IconTile, type IconTileTone } from '@/components/portal/ui/icon-tile';
import { LinkButton, SmallLink } from '@/components/portal/ui/link-button';
import { ProgressBar, type ProgressTone } from '@/components/portal/ui/progress-bar';
import { Bone } from '@/components/portal/ui/query-states';
import { type AllowanceKind, type AllowanceLine, allowanceLines } from '@/lib/portal-allowances';
import { formatData } from '@/lib/telco-format';
import type { AccountSummary, PackageView } from '@/lib/types/portal';

const CARD =
  'bg-surface border-line rounded-hero shadow-panel phone:p-[19px] min-w-0 border px-[22px] pt-[22px] pb-[18px]';

const LINES: {
  kind: AllowanceKind;
  label: string;
  icon: typeof WifiIcon;
  tone: IconTileTone;
  bar: ProgressTone;
}[] = [
  { kind: 'data', label: 'Internet data', icon: WifiIcon, tone: 'purple', bar: 'brand' },
  { kind: 'minutes', label: 'Talk-time', icon: PhoneIcon, tone: 'green', bar: 'mint' },
  { kind: 'sms', label: 'SMS', icon: MessageSquareTextIcon, tone: 'orange', bar: 'orange' },
];

function amount(kind: AllowanceKind, n: number): string {
  if (kind === 'data') return formatData(n);
  return `${n.toLocaleString('en-IN')}${kind === 'minutes' ? ' min' : ''}`;
}

/** "8.4 GB / 15.0 GB", "182 / 300 min", "74 / 100"; just the amount left when the total is unknown. */
function AllowanceValue({ kind, line }: { kind: AllowanceKind; line: AllowanceLine }) {
  if (line.expiresAt === null) {
    return (
      <span className="text-muted-foreground text-[11px] font-semibold">Not in your packs</span>
    );
  }
  if (line.total === null) return <>{amount(kind, line.left)}</>;
  const left = kind === 'data' ? formatData(line.left) : line.left.toLocaleString('en-IN');
  return (
    <>
      {left}{' '}
      <span className="text-muted-foreground text-[10px] font-medium">
        / {amount(kind, line.total)}
      </span>
    </>
  );
}

/** "Your active allowances": data, minutes and SMS left against what the active packs include. */
export function AllowancesCard({
  summary,
  packages,
}: {
  summary: AccountSummary;
  /** The package catalogue, for the included totals; undefined while loading (no bars yet). */
  packages: PackageView[] | undefined;
}) {
  const lines = allowanceLines(summary.subscriptions, packages);

  return (
    <div className={CARD}>
      <div className="mb-1 flex items-center justify-between gap-2.5">
        <h3 className="text-sm font-extrabold tracking-[-0.2px]">Your active allowances</h3>
        <SmallLink href="/portal/balance">
          Details
          <ArrowUpRightIcon aria-hidden="true" />
        </SmallLink>
      </div>

      {summary.subscriptions.length === 0 ? (
        <div className="mt-4 flex flex-col items-start gap-3">
          <div>
            <p className="text-sm font-bold">No active pack</p>
            <p className="text-muted-foreground mt-1 text-[11px]">
              Data, minutes and SMS come with a pack.
            </p>
          </div>
          <LinkButton href="/portal/packages" variant="soft">
            Buy a pack
          </LinkButton>
        </div>
      ) : (
        <ul>
          {LINES.map(({ kind, label, icon, tone, bar }) => {
            const line = lines[kind];
            return (
              <li key={kind} className="my-3.5 flex items-center gap-3">
                <IconTile icon={icon} tone={tone} size="lg" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-[5px]">
                    <p className="text-muted-foreground mb-0.5 text-[11px]">{label}</p>
                    <p className="text-sm font-extrabold whitespace-nowrap">
                      <AllowanceValue kind={kind} line={line} />
                    </p>
                  </div>
                  {line.total !== null && line.total > 0 && (
                    <ProgressBar
                      value={line.left}
                      max={line.total}
                      tone={bar}
                      label={`${label} left`}
                    />
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function AllowancesCardSkeleton() {
  return (
    <div className={CARD} aria-hidden="true">
      <Bone className="h-4 w-40" />
      {LINES.map(({ kind }) => (
        <div key={kind} className="my-3.5 flex items-center gap-3">
          <Bone className="size-[38px] rounded-xl" />
          <div className="flex-1 space-y-2.5">
            <Bone className="h-3 w-2/3" />
            <Bone className="h-1.5 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
