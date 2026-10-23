import { Avatar } from '@/components/dashboard/avatar';

/** A subscriber's avatar, name and masked number, as the admin tables show them. */
export function PersonCell({ name, msisdn }: { name: string; msisdn: string }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <Avatar name={name} />
      <div className="min-w-0">
        <p className="truncate text-xs font-bold">{name}</p>
        <p className="text-muted-foreground truncate text-[11px] tabular-nums">{msisdn}</p>
      </div>
    </div>
  );
}
