import { Loader2Icon } from 'lucide-react';

/** In-layout loading state for public pages; the chat bubble stays mounted beside it. */
export default function SiteLoading() {
  return (
    <main className="text-muted-foreground grid min-h-svh place-content-center text-sm">
      <span className="inline-flex items-center gap-2" role="status">
        <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
        Loading…
      </span>
    </main>
  );
}
