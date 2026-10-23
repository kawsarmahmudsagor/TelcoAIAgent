'use client';

import { useEffect, useState } from 'react';
import { PlusIcon, XIcon } from 'lucide-react';
import { SearchField } from '@/components/dashboard/list-controls';
import { Button } from '@/components/ui/button';
import { adminApi } from '@/lib/admin-api';
import type { OfferSubscriberRef, SubscriberItem } from '@/lib/types/admin';

/** Chooses the subscribers a `specific` offer is for: search by name or number, add, remove. */
export function SubscriberPicker({
  picked,
  onChange,
}: {
  picked: OfferSubscriberRef[];
  onChange: (next: OfferSubscriberRef[]) => void;
}) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<SubscriberItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!q) {
      setResults(null);
      return;
    }
    let cancelled = false;
    setFailed(false);
    adminApi.subscribers({ q, limit: 6 }).then(
      (page) => {
        if (!cancelled) setResults(page.items);
      },
      () => {
        if (!cancelled) setFailed(true);
      }
    );
    return () => {
      cancelled = true;
    };
  }, [q]);

  const chosen = new Set(picked.map((p) => p.id));
  const options = (results ?? []).filter((r) => !chosen.has(r.id));

  return (
    <div className="grid gap-2.5">
      {picked.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Chosen subscribers">
          {picked.map((p) => (
            <li
              key={p.id}
              className="bg-tint-purple text-brand dark:text-brand2 flex items-center gap-1 rounded-full py-1 pr-1 pl-3 text-xs font-bold"
            >
              <span>
                {p.full_name} <span className="font-normal tabular-nums">{p.msisdn_masked}</span>
              </span>
              <button
                type="button"
                onClick={() => onChange(picked.filter((x) => x.id !== p.id))}
                aria-label={`Remove ${p.full_name}`}
                className="focus-visible:ring-ring/60 grid size-6 place-items-center rounded-full outline-none hover:bg-black/10 focus-visible:ring-[3px]"
              >
                <XIcon className="size-3.5" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex">
        <SearchField
          label="Search subscribers to add"
          placeholder="Search name or number…"
          onSearch={setQ}
        />
      </div>
      {q && failed && (
        <p role="alert" className="text-destructive text-xs">
          Search failed. Try again.
        </p>
      )}
      {q && results && (
        <ul className="divide-line border-line divide-y rounded-md border" aria-label="Matches">
          {options.length === 0 ? (
            <li className="text-muted-foreground px-3 py-2.5 text-xs">
              {results.length === 0 ? 'No subscriber matches.' : 'Every match is already added.'}
            </li>
          ) : (
            options.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="min-w-0 text-xs">
                  <span className="block truncate font-bold">{s.full_name}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {s.msisdn_masked} · {s.district}
                  </span>
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    onChange([
                      ...picked,
                      { id: s.id, full_name: s.full_name, msisdn_masked: s.msisdn_masked },
                    ])
                  }
                  aria-label={`Add ${s.full_name}`}
                >
                  <PlusIcon aria-hidden="true" /> Add
                </Button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
