const bdt = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/** Taka with South Asian digit grouping, e.g. "৳45,00,000". */
export function formatBdt(amount: number): string {
  return `৳${bdt.format(amount)}`;
}

/** A budget range; either end may be missing. */
export function formatBudget(min: number | null, max: number | null): string {
  if (min === null && max === null) return '—';
  if (min === null) return `Up to ${formatBdt(max!)}`;
  if (max === null) return `From ${formatBdt(min)}`;
  return `${formatBdt(min)} – ${formatBdt(max)}`;
}

const dateTime = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

/** e.g. "9 Oct 2026, 3:30 pm" in the viewer's locale and timezone. */
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

const weekdayDateTime = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

/** e.g. "Wed 14 Oct, 10:00" in the viewer's locale and timezone; no year. */
export function formatWeekdayDateTime(iso: string): string {
  return weekdayDateTime.format(new Date(iso));
}

const shortDay = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' });

/** A calendar day ("2026-10-09") as "9 Oct", without shifting it through UTC. */
export function formatShortDay(isoDate: string): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  return shortDay.format(new Date(y, m - 1, d));
}

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
const RELATIVE_STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
];

/** "3 minutes ago", "yesterday"; older than a week falls back to the full date and time. */
export function formatRelative(iso: string, now: number = Date.now()): string {
  let value = (new Date(iso).getTime() - now) / 1000;
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(value) < size) return relative.format(Math.round(value), unit);
    value /= size;
  }
  return formatDateTime(iso);
}

/** "4 min 12 s", "1 h 3 min" between two timestamps. */
export function formatDuration(startIso: string, endIso: string): string {
  const seconds = Math.max(0, Math.round((Date.parse(endIso) - Date.parse(startIso)) / 1000));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ${seconds % 60} s`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

/** "1.4 MB", "820 KB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
