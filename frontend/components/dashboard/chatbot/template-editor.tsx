'use client';

import { useRef } from 'react';
import { LockIcon, PencilIcon, RotateCcwIcon } from 'lucide-react';
import { FormField } from '@/components/dashboard/form-field';
import { StatusPill } from '@/components/dashboard/status-pill';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/shadcn/utils';

const PLACEHOLDER_HELP: Record<string, string> = {
  agent_name: 'the assistant’s name',
  operator_name: 'the operator’s name',
  customer_name: 'the customer’s name',
  nudge_text: 'the reminder the agent is nudging the customer about',
  current_date: 'today’s date',
  timezone: 'the agency timezone',
  knowledge_scope: 'what the agent may answer from (added automatically if missing)',
};

/**
 * A template the agent is given, with `{placeholders}` it fills in. Clicking a placeholder chip
 * inserts it at the cursor. `locked` shows the text read-only until the pencil is pressed, for
 * the long prompt where a stray keystroke would be costly.
 */
export function TemplateEditor({
  id,
  label,
  hint,
  value,
  onChange,
  placeholders,
  isDefault,
  error,
  rows = 4,
  locked = false,
  onUnlock,
  onReset,
  resetLabel = 'Use default',
  className,
}: {
  id: string;
  label: string;
  hint?: React.ReactNode;
  value: string;
  onChange: (value: string) => void;
  placeholders: string[];
  /** The saved value is the built-in default and hasn't been edited. */
  isDefault: boolean;
  error?: string;
  rows?: number;
  locked?: boolean;
  onUnlock?: () => void;
  /** Absent hides the reset action. */
  onReset?: () => void;
  resetLabel?: string;
  className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  function insert(name: string) {
    const token = `{${name}}`;
    const el = ref.current;
    if (!el || locked) return;
    const start = el.selectionStart ?? value.length;
    const end = el.selectionEnd ?? value.length;
    onChange(value.slice(0, start) + token + value.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + token.length, start + token.length);
    });
  }

  return (
    <FormField
      id={id}
      label={label}
      hint={hint}
      error={error}
      className={className}
      aside={
        <span className="flex items-center gap-2">
          {isDefault && <StatusPill tone="muted">Default</StatusPill>}
          {onReset && !locked && (
            <Button type="button" variant="ghost" size="xs" onClick={onReset}>
              <RotateCcwIcon aria-hidden="true" />
              {resetLabel}
            </Button>
          )}
          {locked && onUnlock && (
            <Button type="button" variant="outline" size="xs" onClick={onUnlock}>
              <PencilIcon aria-hidden="true" />
              Edit
            </Button>
          )}
        </span>
      }
    >
      {(control) => (
        <div className="grid gap-2">
          <div className="relative">
            <Textarea
              {...control}
              ref={ref}
              rows={rows}
              value={value}
              readOnly={locked}
              onChange={(e) => onChange(e.target.value)}
              spellCheck
              className={cn(
                'max-h-[30rem] min-h-20 text-sm leading-relaxed',
                locked &&
                  'bg-muted/50 text-muted-foreground cursor-default pr-9 focus-visible:ring-0'
              )}
            />
            {locked && (
              <LockIcon
                className="text-muted-foreground absolute top-2.5 right-2.5 size-4"
                aria-label="Locked. Press Edit to change it."
              />
            )}
          </div>
          {placeholders.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">Fills in:</span>
              {placeholders.map((name) => (
                <button
                  key={name}
                  type="button"
                  disabled={locked}
                  onClick={() => insert(name)}
                  title={`Insert {${name}}: ${PLACEHOLDER_HELP[name] ?? name}`}
                  className="bg-secondary text-secondary-foreground hover:bg-accent focus-visible:ring-ring/50 rounded-sm px-1.5 py-0.5 font-mono text-[11px] outline-none focus-visible:ring-[3px] disabled:cursor-default disabled:opacity-70"
                >
                  {`{${name}}`}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </FormField>
  );
}
