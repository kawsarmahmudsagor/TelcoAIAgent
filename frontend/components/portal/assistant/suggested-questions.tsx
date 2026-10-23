'use client';

import { ArrowUpRightIcon } from 'lucide-react';
import { cn } from '@/lib/shadcn/utils';

export interface SuggestedQuestion {
  text: string;
  /** BCP 47 language of the text, for screen readers and font shaping. */
  lang?: string;
}

/** The questions the assistant page and the bubble offer; each sends its text as is. */
export const POPULAR_QUESTIONS: SuggestedQuestion[] = [
  { text: 'How much data do I have left?' },
  { text: 'Which package is best for me?' },
  { text: 'Why was my balance deducted?' },
  { text: 'Create a support case' },
  { text: 'আমার ব্যালেন্স কত?', lang: 'bn' },
];

/** The reference's "Popular questions" list: full-width rows with a brand arrow. */
export function PopularQuestionList({ onAsk }: { onAsk(text: string): void }) {
  return (
    <ul>
      {POPULAR_QUESTIONS.map((q) => (
        <li key={q.text} className="border-line border-b last:border-b-0">
          <button
            type="button"
            lang={q.lang}
            onClick={() => onAsk(q.text)}
            className="hover:text-brand focus-visible:ring-ring/60 flex min-h-11 w-full items-center justify-between gap-3 rounded-md py-2.5 text-left text-xs outline-none focus-visible:ring-[3px] motion-safe:transition-colors dark:hover:text-[#a9a3ff]"
          >
            {q.text}
            <ArrowUpRightIcon
              className="text-brand size-3.5 shrink-0 dark:text-[#a9a3ff]"
              aria-hidden="true"
            />
          </button>
        </li>
      ))}
    </ul>
  );
}

/** The reference's quick-reply chips, for the chat's empty state. */
export function QuestionChips({
  onAsk,
  className,
}: {
  onAsk(text: string): void;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-wrap gap-[7px]', className)}>
      {POPULAR_QUESTIONS.map((q) => (
        <button
          key={q.text}
          type="button"
          lang={q.lang}
          onClick={() => onAsk(q.text)}
          className="text-brand bg-surface focus-visible:ring-ring/60 hover:bg-tint-purple min-h-8 rounded-lg border border-[#bcb8ff] px-[9px] py-[7px] text-[11px] font-bold outline-none focus-visible:ring-[3px] motion-safe:transition-colors dark:border-[#4a4690] dark:text-[#a9a3ff]"
        >
          {q.text}
        </button>
      ))}
    </div>
  );
}
