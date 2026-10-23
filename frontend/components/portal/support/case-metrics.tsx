import { CheckCircle2Icon, ClockIcon, InboxIcon, MessageSquareIcon } from 'lucide-react';
import { MetricTile } from '@/components/portal/ui/metric-tile';
import { Bone } from '@/components/portal/ui/query-states';
import type { CaseView } from '@/lib/types/portal';

/** All, open (open + in review) and resolved counts, and the static response time. */
export function CaseMetrics({ cases }: { cases: CaseView[] | undefined }) {
  const count = (pick: (c: CaseView) => boolean) => cases?.filter(pick).length ?? 0;
  const pending = <Bone className="mt-1 h-7 w-12" />;
  return (
    <div className="tablet:grid-cols-2 phone:gap-2.5 mb-5 grid grid-cols-4 gap-[18px]">
      <MetricTile
        icon={InboxIcon}
        tone="purple"
        label="All cases"
        value={cases ? cases.length : pending}
        foot="Since you joined"
      />
      <MetricTile
        icon={MessageSquareIcon}
        tone="orange"
        label="Open"
        value={cases ? count((c) => c.status !== 'resolved') : pending}
        foot="Open or being reviewed"
      />
      <MetricTile
        icon={CheckCircle2Icon}
        tone="green"
        label="Resolved"
        value={cases ? count((c) => c.status === 'resolved') : pending}
        foot="Closed by our team"
      />
      <MetricTile
        icon={ClockIcon}
        tone="pink"
        label="Typical response"
        value="~2 hrs"
        foot="During support hours"
      />
    </div>
  );
}
