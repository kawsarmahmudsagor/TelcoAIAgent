'use client';

import { useState } from 'react';
import { Loader2Icon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { ReplyLanguage } from '@/lib/reply-language';
import { cn } from '@/lib/shadcn/utils';

const LANGUAGES: { value: ReplyLanguage; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'bn', label: 'বাংলা' },
];

/** Saves an export response as a file, named as the server named it. */
export async function downloadResponse(res: Response): Promise<void> {
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'telco-chat.docx';
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * Picks the language and downloads an ended conversation as a Word file; anything not in that
 * language is translated by the server. `fetchExport` is the surface's own authenticated fetch
 * (visitor id for the chat, admin cookie for the dashboard). Stays open on an error, for retry.
 */
export function ExportConversationDialog({
  open,
  onOpenChange,
  defaultLanguage,
  fetchExport,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  defaultLanguage: ReplyLanguage | null;
  fetchExport(lang: ReplyLanguage): Promise<Response>;
}) {
  const [lang, setLang] = useState<ReplyLanguage>(defaultLanguage ?? 'en');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Each opening starts from the chat's language with no old error.
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setLang(defaultLanguage ?? 'en');
      setError(null);
    }
  }

  const changeOpen = (next: boolean) => {
    if (!busy) onOpenChange(next);
  };

  const exportNow = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetchExport(lang);
      if (res.status === 409) {
        setError('This chat is still in progress');
        return;
      }
      if (res.status === 429) {
        setError('Too many exports right now, try again in a moment');
        return;
      }
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      await downloadResponse(res);
      onOpenChange(false);
    } catch {
      setError('Couldn’t translate, try again');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Export chat</DialogTitle>
          <DialogDescription>
            Download the conversation as a Word file. Messages in another language are translated.
          </DialogDescription>
        </DialogHeader>
        <div role="radiogroup" aria-label="Language" className="grid grid-cols-2 gap-2">
          {LANGUAGES.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={lang === option.value}
              lang={option.value}
              disabled={busy}
              onClick={() => setLang(option.value)}
              className={cn(
                'rounded-md border px-3 py-2.5 text-sm font-semibold transition-colors',
                lang === option.value
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-input hover:bg-accent'
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => changeOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void exportNow()} disabled={busy}>
            {busy && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            {busy ? 'Exporting…' : 'Export'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
