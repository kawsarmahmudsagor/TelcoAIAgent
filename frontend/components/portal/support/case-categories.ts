import { humanize } from '@/lib/telco-format';
import type { PortalCaseCategory } from '@/lib/types/portal';

/** The categories the portal can file a case under, in the order the dialog lists them. */
export const PORTAL_CASE_CATEGORIES: { value: PortalCaseCategory; label: string }[] = [
  { value: 'recharge_not_credited', label: 'Recharge not credited' },
  { value: 'unexpected_deduction', label: 'Unexpected deduction' },
  { value: 'package_activation', label: 'Package activation' },
  { value: 'network_issue', label: 'Network issue' },
  { value: 'billing', label: 'Billing' },
  { value: 'other', label: 'Other' },
];

/** The label for a portal category; cases opened elsewhere (e.g. `human_handoff` from the agent) get a humanised code. */
export function caseCategoryLabel(category: string): string {
  return PORTAL_CASE_CATEGORIES.find((c) => c.value === category)?.label ?? humanize(category);
}
