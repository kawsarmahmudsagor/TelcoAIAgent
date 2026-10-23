import { cn } from '@/lib/shadcn/utils';
import { initials } from '@/lib/telco-format';

/** Initials in a tinted circle. */
export function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'bg-tint-purple text-brand dark:text-brand2 grid size-9 shrink-0 place-items-center rounded-full text-[11px] font-extrabold',
        className
      )}
    >
      {initials(name)}
    </span>
  );
}
