'use client';

import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  useTransition,
} from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDownIcon, Loader2Icon, SlidersHorizontalIcon } from 'lucide-react';
import { PROPERTY_TYPE } from '@/components/dashboard/status-tones';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { formatBdt } from '@/lib/format';
import {
  BATHROOM_OPTIONS,
  BEDROOM_OPTIONS,
  LISTING_OPTIONS,
  PROPERTY_SORTS,
  PROPERTY_TYPE_OPTIONS,
  type PropertyFilters,
  type PropertySort,
  activeFilterCount,
  propertiesHref,
} from '@/lib/property-filters';
import { cn } from '@/lib/shadcn/utils';
import type { PropertyType, PublicListingFacets } from '@/lib/types';

interface BrowserState {
  filters: PropertyFilters;
  facets: PublicListingFacets | null;
  /** Total matches for the current filters, or null when the listings didn't load. */
  total: number | null;
  pending: boolean;
  /** Changes some filters and goes back to page 1. Client navigation, so a live call stays up. */
  apply: (next: Partial<PropertyFilters>) => void;
}

const BrowserContext = createContext<BrowserState | null>(null);

function useBrowser(): BrowserState {
  const state = useContext(BrowserContext);
  if (!state) throw new Error('useBrowser must be used inside <PropertyBrowser>');
  return state;
}

/** Holds the page's filters and the pending state of a filter change for everything below it. */
export function PropertyBrowser({
  filters,
  facets,
  total,
  children,
}: {
  filters: PropertyFilters;
  facets: PublicListingFacets | null;
  total: number | null;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const apply = (next: Partial<PropertyFilters>) => {
    startTransition(() => {
      router.push(propertiesHref({ ...filters, ...next, page: 1 }), { scroll: false });
    });
  };
  return (
    <BrowserContext.Provider value={{ filters, facets, total, pending, apply }}>
      {children}
    </BrowserContext.Provider>
  );
}

/** The results area: dimmed and marked busy while a filter change loads. */
export function PropertyResults({ children }: { children: React.ReactNode }) {
  const { pending } = useBrowser();
  return (
    <div
      aria-busy={pending}
      className={cn('transition-opacity duration-200', pending && 'opacity-60')}
    >
      {children}
    </div>
  );
}

/** The filter form in the desktop sidebar. */
export function PropertyFiltersSidebar() {
  const { filters, pending } = useBrowser();
  const count = activeFilterCount(filters);
  return (
    <section aria-labelledby="filters-title">
      <div className="flex h-9 items-center justify-between gap-2">
        <h2 id="filters-title" className="flex items-center gap-2 font-semibold">
          Filters
          {pending && (
            <Loader2Icon
              aria-label="Updating"
              className="text-muted-foreground size-4 animate-spin"
            />
          )}
        </h2>
        {count > 0 && <ClearFiltersButton />}
      </div>
      <FilterFields className="mt-4" />
    </section>
  );
}

/** "Filters" button that opens the form in a bottom sheet on small screens. */
export function PropertyFiltersSheet() {
  const { filters, total, pending } = useBrowser();
  const count = activeFilterCount(filters);
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" className="h-10">
          <SlidersHorizontalIcon aria-hidden="true" />
          Filters
          {count > 0 && (
            <span className="bg-primary text-primary-foreground grid min-w-5 place-items-center rounded-full px-1 text-xs tabular-nums">
              {count}
            </span>
          )}
        </Button>
      </SheetTrigger>
      <SheetContent side="bottom" className="max-h-[88svh] gap-0 rounded-t-xl">
        <SheetHeader className="border-b">
          <SheetTitle className="font-display text-lg">Filters</SheetTitle>
          <SheetDescription>Results update as you choose.</SheetDescription>
        </SheetHeader>
        <FilterFields className="overflow-y-auto p-4" />
        <SheetFooter className="flex-row border-t">
          {count > 0 && <ClearFiltersButton className="h-10" />}
          <SheetClose asChild>
            <Button className="h-10 flex-1">
              {pending ? (
                <Loader2Icon aria-hidden="true" className="animate-spin" />
              ) : total === null ? (
                'Show homes'
              ) : (
                `Show ${total} ${total === 1 ? 'home' : 'homes'}`
              )}
            </Button>
          </SheetClose>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

export function ClearFiltersButton({ className }: { className?: string }) {
  const { apply } = useBrowser();
  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn('text-muted-foreground', className)}
      onClick={() =>
        apply({
          listing: undefined,
          types: [],
          area: undefined,
          min: undefined,
          max: undefined,
          beds: undefined,
          baths: undefined,
        })
      }
    >
      Clear all
    </Button>
  );
}

/** The sort order, above the results. */
export function PropertySortSelect() {
  const { filters, apply } = useBrowser();
  const id = useId();
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="text-muted-foreground shrink-0 text-sm">
        Sort by
      </label>
      <NativeSelect
        id={id}
        value={filters.sort}
        onChange={(e) => apply({ sort: e.target.value as PropertySort })}
        className="w-auto"
      >
        {PROPERTY_SORTS.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}

function FilterFields({ className }: { className?: string }) {
  const { filters, facets, apply } = useBrowser();
  const areaId = useId();
  const typeCounts = new Map(facets?.property_types.map((t) => [t.value, t.count]));
  const cities = facets?.cities ?? [];
  const neighborhoods = facets?.neighborhoods ?? [];
  const areaKnown =
    !filters.area ||
    cities.some((c) => c.name === filters.area) ||
    neighborhoods.some((n) => n.name === filters.area);

  const toggleType = (t: PropertyType) =>
    apply({
      types: filters.types.includes(t)
        ? filters.types.filter((x) => x !== t)
        : [...filters.types, t],
    });

  return (
    <div className={cn('flex flex-col gap-6', className)}>
      <FilterGroup legend="Looking to">
        <ChipList>
          <Chip current={!filters.listing} onClick={() => apply({ listing: undefined })}>
            Buy or rent
          </Chip>
          {LISTING_OPTIONS.map((o) => (
            <Chip
              key={o.value}
              current={filters.listing === o.value}
              onClick={() => apply({ listing: o.value })}
            >
              {o.label}
            </Chip>
          ))}
        </ChipList>
      </FilterGroup>

      <FilterGroup legend="Property type">
        <ChipList>
          {PROPERTY_TYPE_OPTIONS.map((t) => {
            const count = typeCounts.get(t) ?? 0;
            const current = filters.types.includes(t);
            if (!current && facets && count === 0) return null;
            return (
              <Chip key={t} current={current} onClick={() => toggleType(t)}>
                {PROPERTY_TYPE[t]}
                {facets && (
                  <span
                    className={cn(
                      'tabular-nums',
                      current ? 'text-background/70' : 'text-muted-foreground'
                    )}
                  >
                    {count}
                  </span>
                )}
              </Chip>
            );
          })}
        </ChipList>
      </FilterGroup>

      <div className="flex flex-col gap-2.5">
        <label htmlFor={areaId} className="text-sm font-semibold">
          Area
        </label>
        <NativeSelect
          id={areaId}
          value={filters.area ?? ''}
          onChange={(e) => apply({ area: e.target.value || undefined })}
        >
          <option value="">Anywhere</option>
          {!areaKnown && <option value={filters.area}>{filters.area}</option>}
          {neighborhoods.length > 0 && (
            <optgroup label="Neighbourhoods">
              {neighborhoods.map((n) => (
                <option key={`${n.name}|${n.city}`} value={n.name}>
                  {n.name}
                  {n.city !== 'Dhaka' ? `, ${n.city}` : ''} ({n.count})
                </option>
              ))}
            </optgroup>
          )}
          {cities.length > 0 && (
            <optgroup label="Cities">
              {cities.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.count})
                </option>
              ))}
            </optgroup>
          )}
        </NativeSelect>
      </div>

      <PriceFields />

      <FilterGroup legend="Bedrooms">
        <ChipList>
          <Chip current={!filters.beds} onClick={() => apply({ beds: undefined })}>
            Any
          </Chip>
          {BEDROOM_OPTIONS.map((n) => (
            <Chip key={n} current={filters.beds === n} onClick={() => apply({ beds: n })}>
              {n}+
            </Chip>
          ))}
        </ChipList>
      </FilterGroup>

      <FilterGroup legend="Bathrooms">
        <ChipList>
          <Chip current={!filters.baths} onClick={() => apply({ baths: undefined })}>
            Any
          </Chip>
          {BATHROOM_OPTIONS.map((n) => (
            <Chip key={n} current={filters.baths === n} onClick={() => apply({ baths: n })}>
              {n}+
            </Chip>
          ))}
        </ChipList>
      </FilterGroup>
    </div>
  );
}

/** Taka typed with or without commas; empty or junk means no bound. */
function parseTaka(value: string): number | undefined {
  const digits = value.replace(/[^\d.]/g, '');
  if (!digits) return undefined;
  const n = Number(digits);
  return Number.isFinite(n) ? n : undefined;
}

function PriceFields() {
  const { filters, facets, apply } = useBrowser();
  const minId = useId();
  const maxId = useId();
  const hintId = useId();
  const [min, setMin] = useState(filters.min?.toString() ?? '');
  const [max, setMax] = useState(filters.max?.toString() ?? '');

  // Follow the URL when it changes underneath (back button, "Clear all").
  useEffect(() => setMin(filters.min?.toString() ?? ''), [filters.min]);
  useEffect(() => setMax(filters.max?.toString() ?? ''), [filters.max]);

  const ranges = facets?.price_ranges ?? [];
  const range = filters.listing ? ranges.filter((r) => r.listing_type === filters.listing) : ranges;
  const hint = range
    .map(
      (r) =>
        `${r.listing_type === 'rent' ? 'Rents' : 'Sale prices'} run ${formatBdt(r.min)} to ${formatBdt(r.max)}${r.listing_type === 'rent' ? ' a month' : ''}.`
    )
    .join(' ');

  // The last bounds sent, so blur-then-submit (tapping "Apply price") navigates once.
  const sent = useRef({ min: filters.min, max: filters.max });
  useEffect(() => {
    sent.current = { min: filters.min, max: filters.max };
  }, [filters.min, filters.max]);

  const commit = () => {
    const nextMin = parseTaka(min);
    const nextMax = parseTaka(max);
    if (nextMin === sent.current.min && nextMax === sent.current.max) return;
    sent.current = { min: nextMin, max: nextMax };
    apply({ min: nextMin, max: nextMax });
  };

  return (
    <form
      className="flex flex-col gap-2.5"
      onSubmit={(e) => {
        e.preventDefault();
        commit();
      }}
    >
      <fieldset className="flex flex-col gap-2.5">
        <legend className="mb-2.5 text-sm font-semibold">Price (৳)</legend>
        <div className="flex items-center gap-2">
          <label htmlFor={minId} className="sr-only">
            Minimum price in taka
          </label>
          <Input
            id={minId}
            inputMode="numeric"
            placeholder="Min"
            autoComplete="off"
            value={min}
            onChange={(e) => setMin(e.target.value)}
            onBlur={commit}
            aria-describedby={hint ? hintId : undefined}
            className="bg-card h-10 tabular-nums"
          />
          <span aria-hidden="true" className="text-muted-foreground">
            –
          </span>
          <label htmlFor={maxId} className="sr-only">
            Maximum price in taka
          </label>
          <Input
            id={maxId}
            inputMode="numeric"
            placeholder="Max"
            autoComplete="off"
            value={max}
            onChange={(e) => setMax(e.target.value)}
            onBlur={commit}
            aria-describedby={hint ? hintId : undefined}
            className="bg-card h-10 tabular-nums"
          />
        </div>
        {hint && (
          <p id={hintId} className="text-muted-foreground text-xs leading-relaxed">
            {hint}
          </p>
        )}
      </fieldset>
      {/* Enter in either box applies; the button is there for touch keyboards without one. */}
      <Button type="submit" variant="outline" size="sm" className="self-start">
        Apply price
      </Button>
    </form>
  );
}

function FilterGroup({ legend, children }: { legend: string; children: React.ReactNode }) {
  return (
    <fieldset>
      <legend className="mb-2.5 text-sm font-semibold">{legend}</legend>
      {children}
    </fieldset>
  );
}

function ChipList({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap gap-2">{children}</div>;
}

function Chip({
  current,
  onClick,
  children,
}: {
  current: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={current}
      onClick={onClick}
      className={cn(
        'focus-visible:ring-ring/50 inline-flex h-9 items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium transition-colors outline-none focus-visible:ring-[3px]',
        current
          ? 'bg-foreground text-background border-foreground'
          : 'bg-card text-foreground hover:bg-accent'
      )}
    >
      {children}
    </button>
  );
}

function NativeSelect({ className, children, ...props }: React.ComponentProps<'select'>) {
  return (
    <div className={cn('relative w-full', className)}>
      <select
        {...props}
        className="border-input bg-card focus-visible:border-ring focus-visible:ring-ring/50 h-10 w-full appearance-none rounded-md border py-1 pr-9 pl-3 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
      >
        {children}
      </select>
      <ChevronDownIcon
        aria-hidden="true"
        className="text-muted-foreground pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2"
      />
    </div>
  );
}
