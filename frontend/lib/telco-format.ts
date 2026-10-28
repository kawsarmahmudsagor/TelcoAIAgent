/** Display formats for the telco portal (Global Constraints: money, data, dates). */

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

const dayYearUtc = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});

/** `"14 Mar 2024"` from an ISO date (read as a calendar day, no zone shift) or datetime. */
export function formatJoinDate(iso: string): string {
  if (DATE_ONLY.test(iso)) return dayYearUtc.format(new Date(`${iso}T00:00:00Z`));
  return dayYearDhaka.format(new Date(iso));
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

const dayYearDhaka = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'Asia/Dhaka',
});
const dayTimeDhaka = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
  timeZone: 'Asia/Dhaka',
});
const longDateDhaka = new Intl.DateTimeFormat('en-GB', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'Asia/Dhaka',
});
const isoDayDhaka = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dhaka' });
const hourDhaka = new Intl.DateTimeFormat('en-GB', {
  hour: 'numeric',
  hourCycle: 'h23',
  timeZone: 'Asia/Dhaka',
});

/** `"25 Oct 2026"` from an ISO datetime, in Bangladesh time. */
export function formatDate(iso: string): string {
  return dayYearDhaka.format(new Date(iso));
}

/** `"22 Oct, 10:27 am"` from an ISO datetime, in Bangladesh time. */
export function formatDayTime(iso: string): string {
  return dayTimeDhaka.format(new Date(iso));
}

/** `"Thursday, 22 October 2026"`: today's date in Bangladesh. */
export function formatLongDate(now: Date): string {
  return longDateDhaka.format(now);
}

/** Calendar days from `now` to the ISO datetime, counted in Bangladesh time (0 = today). */
export function daysUntil(iso: string, now: Date): number {
  const day = (d: Date) => Date.parse(`${isoDayDhaka.format(d)}T00:00:00Z`);
  return Math.round((day(new Date(iso)) - day(now)) / 86_400_000);
}

/** `"Good morning"` / `"Good afternoon"` / `"Good evening"` by the hour in Bangladesh. */
export function greeting(now: Date): string {
  const hour = Number(hourDhaka.format(now));
  if (hour >= 5 && hour < 12) return 'Good morning';
  if (hour >= 12 && hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/** `"5m"`, `"3h"` or `"2d"`: how long ago the ISO datetime was, rounded down to one unit. */
export function formatAge(iso: string, now: Date): string {
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours}h` : `${Math.floor(hours / 24)}d`;
}

/** `"human_handoff"` becomes `"Human handoff"`: for a code the UI has no label for. */
export function humanize(code: string): string {
  const text = code.replace(/[_-]+/g, ' ').trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const dhakaParts = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Dhaka',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

/** Minutes Bangladesh time is ahead of UTC at `instant` (read from Intl, not hard-coded). */
function dhakaOffsetMinutes(instant: number): number {
  const p = Object.fromEntries(dhakaParts.formatToParts(instant).map((x) => [x.type, x.value]));
  const asUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute);
  return Math.round((asUtc - Math.floor(instant / 60_000) * 60_000) / 60_000);
}

/**
 * `"2026-10-23T14:30"` (a datetime-local value, read as Bangladesh time) becomes the ISO instant
 * `"2026-10-23T08:30:00.000Z"`, so the backend never has to guess the zone. `null` when empty or
 * not a valid date.
 */
export function dhakaLocalToIso(local: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(local);
  if (!m) return null;
  const wall = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  let instant = wall - dhakaOffsetMinutes(wall) * 60_000;
  instant = wall - dhakaOffsetMinutes(instant) * 60_000;
  return Number.isNaN(instant) ? null : new Date(instant).toISOString();
}
