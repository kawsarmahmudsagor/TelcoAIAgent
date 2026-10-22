/** Display formats for the telco. portal (Global Constraints: money, data, dates). */

const takaWhole = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const takaFractional = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** `"৳ 486.50"` when fractional, `"৳ 500"` when whole; South Asian digit grouping. */
export function formatTaka(n: number): string {
  const abs = Math.abs(n);
  const cents = Math.round(abs * 100);
  const text = cents % 100 === 0 ? takaWhole.format(cents / 100) : takaFractional.format(abs);
  return `${n < 0 && cents !== 0 ? '-' : ''}৳ ${text}`;
}

/** `"8.4 GB"` at 1024 MB or more, otherwise `"800 MB"`. */
export function formatData(mb: number): string {
  const wholeMb = Math.round(mb);
  if (wholeMb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${wholeMb} MB`;
}

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
// A fixed time zone keeps server and client renders identical. Date-only values are calendar
// days already, so they are read as UTC midnight and printed in UTC; datetimes are shown in
// Bangladesh time, where the fictional operator lives.
const dayUtc = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
});
const dayDhaka = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'Asia/Dhaka',
});

/** `"22 Oct"` from an ISO date (`2026-10-22`) or datetime. */
export function formatDay(iso: string): string {
  if (DATE_ONLY.test(iso)) return dayUtc.format(new Date(`${iso}T00:00:00Z`));
  return dayDhaka.format(new Date(iso));
}

/** `"SK"` from `"Samiha Khan"`: first and last initials, for avatars. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (
    (parts[0]?.[0] ?? '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')
  ).toUpperCase();
}

/** `"Prepaid"` / `"Postpaid"`. */
export function formatPlan(plan: 'prepaid' | 'postpaid'): string {
  return plan === 'prepaid' ? 'Prepaid' : 'Postpaid';
}
