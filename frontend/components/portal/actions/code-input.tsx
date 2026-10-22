'use client';

import { type Ref, useImperativeHandle, useRef } from 'react';
import { cn } from '@/lib/shadcn/utils';

export const CODE_LENGTH = 6;
// ASCII and Bengali digits; the backend normalises Bengali ones, so they are sent as typed.
const DIGIT = /[0-9০-৯]/g;

const digitsOf = (text: string) => text.match(DIGIT) ?? [];

/** An empty code: one '' per box. */
export const emptyCode = (): string[] => Array(CODE_LENGTH).fill('');

export interface CodeInputHandle {
  /** Focuses box `i` (clamped). */
  focus(i?: number): void;
}

export interface CodeInputProps {
  /** One digit (or '') per box. */
  digits: string[];
  onChange(digits: string[]): void;
  /** The id of the element naming the group. */
  labelledBy: string;
  readOnly?: boolean;
  invalid?: boolean;
  /** `md` for the dialog, `sm` for a card inside the chat. */
  size?: 'md' | 'sm';
  ref?: Ref<CodeInputHandle>;
}

/**
 * The 6-box OTP input: typing moves to the next box, Backspace and the arrow keys move back and
 * forth, and a pasted or autofilled code spreads across the boxes.
 */
export function CodeInput({
  digits,
  onChange,
  labelledBy,
  readOnly,
  invalid,
  size = 'md',
  ref,
}: CodeInputProps) {
  const boxes = useRef<(HTMLInputElement | null)[]>([]);
  const focus = (i: number) => boxes.current[Math.max(0, Math.min(CODE_LENGTH - 1, i))]?.focus();

  useImperativeHandle(ref, () => ({ focus: (i = 0) => focus(i) }), []);

  /** Writes `chars` from box `from` on, then focuses the box after the last one written. */
  function fill(from: number, chars: string[]) {
    if (chars.length === 0) return;
    const next = [...digits];
    chars.slice(0, CODE_LENGTH - from).forEach((c, k) => (next[from + k] = c));
    onChange(next);
    focus(from + chars.length);
  }

  return (
    <div
      role="group"
      aria-labelledby={labelledBy}
      className={cn('grid grid-cols-6', size === 'md' ? 'narrow:gap-1.5 gap-2' : 'gap-1.5')}
    >
      {digits.map((digit, i) => (
        <input
          key={i}
          ref={(el) => {
            boxes.current[i] = el;
          }}
          value={digit}
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          aria-label={`Digit ${i + 1} of ${CODE_LENGTH}`}
          aria-invalid={invalid ? true : undefined}
          readOnly={readOnly}
          onFocus={(e) => e.currentTarget.select()}
          onChange={(e) => {
            const chars = digitsOf(e.target.value);
            if (chars.length === 0) {
              onChange(digits.map((d, k) => (k === i ? '' : d)));
              return;
            }
            // A typed digit replaces the box; an autofilled code spreads from here.
            fill(i, chars.length > 1 && digit ? chars.slice(1) : chars);
          }}
          onPaste={(e) => {
            const chars = digitsOf(e.clipboardData.getData('text'));
            if (chars.length === 0) return;
            e.preventDefault();
            // A whole pasted code fills every box.
            fill(chars.length >= CODE_LENGTH ? 0 : i, chars);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Backspace' && !digit && i > 0) {
              e.preventDefault();
              onChange(digits.map((d, k) => (k === i - 1 ? '' : d)));
              focus(i - 1);
            } else if (e.key === 'ArrowLeft') {
              e.preventDefault();
              focus(i - 1);
            } else if (e.key === 'ArrowRight') {
              e.preventDefault();
              focus(i + 1);
            }
          }}
          className={cn(
            'bg-surface2 border-line text-foreground focus-visible:border-brand focus-visible:ring-ring/40 w-full min-w-0 border text-center font-extrabold tabular-nums outline-none read-only:opacity-60 focus-visible:ring-[3px]',
            size === 'md'
              ? 'phone:h-12 h-[52px] rounded-xl text-xl'
              : 'h-11 rounded-[10px] text-lg',
            invalid && 'border-status-failed-foreground'
          )}
        />
      ))}
    </div>
  );
}
