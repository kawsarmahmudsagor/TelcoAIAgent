import { PhoneIcon, ReceiptTextIcon, WalletIcon, WifiIcon } from 'lucide-react';
import { IconTile, type IconTileTone } from '@/components/portal/ui/icon-tile';
import { LinkButton } from '@/components/portal/ui/link-button';
import { ProgressBar, type ProgressTone } from '@/components/portal/ui/progress-bar';
import { Bone } from '@/components/portal/ui/query-states';
import { type AllowanceLine, allowanceLines } from '@/lib/portal-allowances';
import { formatData, formatDate, formatTaka } from '@/lib/telco-format';
import type { AccountSummary, PackageView } from '@/lib/types/portal';

const GRID = 'phone:grid-cols-1 grid grid-cols-3 gap-[18px]';
const CARD = 'bg-surface border-line min-w-0 rounded-[15px] border p-5';

function DetailCard({
  icon,
  tone,
  label,
  value,
  line,
  children,
}: {
  icon: typeof WalletIcon;
  tone: IconTileTone;
  label: string;
  value: string;
  line: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={CARD}>
      <IconTile icon={icon} tone={tone} size="lg" />
      <p className="text-muted-foreground mt-3.5 text-[11px]">{label}</p>
      <p className="mt-3 mb-1 text-2xl font-[850] tracking-[-0.6px] whitespace-nowrap">{value}</p>
      <p className="text-muted-foreground text-[11px]">{line}</p>
      {children}
    </div>
  );
}

/** "Of 15.0 GB · Expires 25 Oct 2026", or why there is nothing to show. */
function allowanceText(line: AllowanceLine, total: string | null, none: string): string {
  if (line.expiresAt === null) return none;
  const expires = `Expires ${formatDate(line.expiresAt)}`;
  return total ? `Of ${total} · ${expires}` : expires;
}

function AllowanceCard({
  line,
  icon,
  tone,
  bar,
  label,
  format,
  none,
}: {
  line: AllowanceLine;
  icon: typeof WalletIcon;
  tone: IconTileTone;
  bar: ProgressTone;
  label: string;
  format(n: number): string;
  none: string;
}) {
  const held = line.expiresAt !== null;
  return (
    <DetailCard
      icon={icon}
      tone={tone}
      label={label}
      value={held ? format(line.left) : '—'}
      line={allowanceText(line, line.total ? format(line.total) : null, none)}
    >
      {held && line.total !== null && line.total > 0 && (
        <ProgressBar
          value={line.left}
          max={line.total}
          tone={bar}
          label={label}
          className="mt-[15px]"
        />
      )}
    </DetailCard>
  );
}

/** Main balance (or the postpaid bill), internet left and talk-time left, with their expiries. */
export function DetailCards({
  summary,
  packages,
}: {
  summary: AccountSummary;
  packages: PackageView[] | undefined;
}) {
  const lines = allowanceLines(summary.subscriptions, packages);
  const postpaid = summary.plan_type === 'postpaid';

  return (
    <div className={GRID}>
      {postpaid ? (
        <DetailCard
          icon={ReceiptTextIcon}
          tone="purple"
          label="Bill due"
          value={formatTaka(summary.postpaid_due)}
          line="Due with this cycle's bill"
        >
          <LinkButton href="/portal/recharge" className="mt-[15px]">
            Pay bill
          </LinkButton>
        </DetailCard>
      ) : (
        <DetailCard
          icon={WalletIcon}
          tone="purple"
          label="Main balance"
          value={formatTaka(summary.main_balance)}
          line="Available to use anytime"
        >
          <LinkButton href="/portal/recharge" className="mt-[15px]">
            Recharge balance
          </LinkButton>
        </DetailCard>
      )}
      <AllowanceCard
        line={lines.data}
        icon={WifiIcon}
        tone="green"
        bar="brand"
        label="Internet remaining"
        format={formatData}
        none="No data pack active"
      />
      <AllowanceCard
        line={lines.minutes}
        icon={PhoneIcon}
        tone="orange"
        bar="mint"
        label="Talk-time remaining"
        format={(n) => `${n.toLocaleString('en-IN')} min`}
        none="No minutes pack active"
      />
    </div>
  );
}

export function DetailCardsSkeleton() {
  return (
    <div className={GRID} aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className={`${CARD} flex flex-col gap-3`}>
          <Bone className="size-[38px] rounded-xl" />
          <Bone className="h-3 w-24" />
          <Bone className="h-7 w-28" />
          <Bone className="h-3 w-40" />
        </div>
      ))}
    </div>
  );
}
