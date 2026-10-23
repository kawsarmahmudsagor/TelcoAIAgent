'use client';

import { useEffect, useState } from 'react';
import { SearchIcon } from 'lucide-react';
import { cn } from '@/lib/shadcn/utils';

/** The look of a filter input or select in the admin lists. */
export const FIELD =
  'border-line bg-surface text-foreground rounded-button focus-visible:ring-ring/60 min-h-9 border px-3 text-xs outline-none focus-visible:ring-[3px]';

const DEBOUNCE_MS = 300;

/**
 * A search box that reports the trimmed text once typing pauses (so each keystroke doesn't
 * query). `onSearch` is also called on mount with the empty string, which callers treat as "no
 * search".
 */
export function SearchField({
  label,
  placeholder,
  onSearch,
}: {
  label: string;
  placeholder: string;
  onSearch: (q: string) => void;
}) {
  const [text, setText] = useState('');
  useEffect(() => {
    const t = setTimeout(() => onSearch(text.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
    // onSearch is a state setter or stable callback in every caller.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);
  return (
    <label className="relative min-w-0 flex-1">
      <span className="sr-only">{label}</span>
      <SearchIcon
        className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2"
        aria-hidden="true"
      />
      <input
        type="search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        className={cn(FIELD, 'w-full pl-9')}
      />
    </label>
  );
}

/** A row of mutually exclusive filter buttons (a radio group in spirit: one is always on). */
export function SegmentedFilter<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="bg-surface2 border-line rounded-button flex gap-0.5 border p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            'focus-visible:ring-ring/60 min-h-8 flex-1 rounded-[8px] px-3 text-xs font-bold whitespace-nowrap outline-none focus-visible:ring-[3px] motion-safe:transition-colors',
            o.value === value
              ? 'bg-surface text-brand shadow-panel dark:text-brand2'
              : 'text-muted-foreground hover:text-foreground'
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
