import { StatusChip, type StatusTone } from '@/components/portal/ui/status-chip';
import type { DistrictHealthState, IncidentAdminView } from '@/lib/types/admin';
import type { IncidentKind, IncidentStatus } from '@/lib/types/portal';

export const KIND_LABEL: Record<IncidentKind, string> = {
  outage: 'Outage',
  congestion: 'Data congestion',
  maintenance: 'Planned maintenance',
};

const HEALTH: Record<DistrictHealthState, { tone: StatusTone; label: string }> = {
  normal: { tone: 'success', label: 'Normal' },
  degraded: { tone: 'pending', label: 'Degraded' },
  maintenance: { tone: 'open', label: 'Maintenance' },
};

export function HealthChip({ health }: { health: DistrictHealthState }) {
  const h = HEALTH[health] ?? { tone: 'open' as const, label: health };
  return <StatusChip tone={h.tone}>{h.label}</StatusChip>;
}

const STATUS: Record<IncidentStatus, { tone: StatusTone; label: string }> = {
  investigating: { tone: 'pending', label: 'Investigating' },
  scheduled: { tone: 'open', label: 'Scheduled' },
  resolved: { tone: 'success', label: 'Resolved' },
};

export function IncidentStatusChip({ status }: { status: IncidentStatus }) {
  const s = STATUS[status] ?? { tone: 'open' as const, label: status };
  return <StatusChip tone={s.tone}>{s.label}</StatusChip>;
}

/** An incident that is still in force: not resolved and not past its end time. */
export function isLive(i: IncidentAdminView, now: Date): boolean {
  return i.status !== 'resolved' && (i.ends_at === null || new Date(i.ends_at) > now);
}
