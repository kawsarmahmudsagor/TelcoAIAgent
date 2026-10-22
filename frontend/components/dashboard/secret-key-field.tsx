'use client';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/**
 * A write-only key: the server never sends a stored key back, only whether there is one, so the
 * input starts empty. `value`: null keeps the stored key, '' removes it on save, anything else
 * replaces it.
 */
export function SecretKeyField({
  id,
  label,
  hint,
  stored,
  value,
  onChange,
  emptyPlaceholder,
  disabled,
}: {
  id: string;
  label: string;
  hint?: React.ReactNode;
  /** Whether a key is saved now. */
  stored: boolean;
  value: string | null;
  onChange: (value: string | null) => void;
  /** What the input says when no key is saved: which key is used instead. */
  emptyPlaceholder: string;
  /** e.g. the server can't store keys. */
  disabled?: boolean;
}) {
  const removing = value === '';
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        {stored && !removing && !disabled && (
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-2"
            onClick={() => onChange('')}
          >
            Remove saved key
          </button>
        )}
        {removing && (
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-2"
            onClick={() => onChange(null)}
          >
            Keep saved key
          </button>
        )}
      </div>
      <Input
        id={id}
        type="password"
        autoComplete="off"
        disabled={disabled}
        value={value ?? ''}
        // Clearing the field again means "keep what is saved", not "remove".
        onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
        aria-describedby={hint ? `${id}-hint` : undefined}
        placeholder={
          removing ? 'Will be removed on save' : stored ? '•••••••••• saved' : emptyPlaceholder
        }
      />
      {hint && (
        <p id={`${id}-hint`} className="text-muted-foreground text-xs">
          {hint}
        </p>
      )}
    </div>
  );
}
