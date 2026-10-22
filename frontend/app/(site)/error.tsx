'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

/** In-layout error boundary for public pages, so a crash doesn't unmount the chat bubble. */
export default function SiteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main
      id="main"
      className="mx-auto flex min-h-svh w-full max-w-6xl flex-col justify-center px-4 py-20 sm:px-8"
    >
      <h1 className="font-display text-3xl font-semibold tracking-[-0.02em] sm:text-4xl">
        Something went wrong
      </h1>
      <p className="text-muted-foreground mt-3 max-w-xl text-lg leading-relaxed">
        This page didn’t load. You can try again, or keep chatting with our AI agent.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <Button size="lg" onClick={reset}>
          Try again
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link href="/home">Back to home</Link>
        </Button>
      </div>
    </main>
  );
}
