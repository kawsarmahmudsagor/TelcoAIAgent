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
  { text: 'আমার ব্যালেন্স কত?', lang: 'bn' },
  { text: 'আমার কত ডাটা বাকি আছে?', lang: 'bn' },
  { text: 'আমার জন্য কোন প্যাকটা ভালো হবে?', lang: 'bn' },
  { text: 'ব্যালেন্স থেকে টাকা কাটল কেন?', lang: 'bn' },
  { text: 'একটা কমপ্লেইন করতে চাই', lang: 'bn' },
];

/** The same for a guest on the home page: nothing that needs their account. */
export const GUEST_QUESTIONS: SuggestedQuestion[] = [
  { text: 'মান্থলি ডাটা প্যাক কী কী আছে?', lang: 'bn' },
  { text: '৩০০ টাকার মধ্যে কোনো ইন্টারনেট প্যাক আছে?', lang: 'bn' },
  { text: 'নতুন সিম কীভাবে নেবো?', lang: 'bn' },
  { text: 'কাছের কেয়ার সেন্টার কোথায়?', lang: 'bn' },
  { text: 'ঢাকায় কি নেটওয়ার্কে কোনো সমস্যা হচ্ছে?', lang: 'bn' },
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
            className="hover:text-brand-text focus-visible:ring-ring/60 flex min-h-11 w-full items-center justify-between gap-3 rounded-md py-2.5 text-left text-xs outline-none focus-visible:ring-[3px] motion-safe:transition-colors"
          >
            {q.text}
            <ArrowUpRightIcon className="text-brand-text size-3.5 shrink-0" aria-hidden="true" />
          </button>
        </li>
      ))}
    </ul>
  );
}

/** The reference's quick-reply chips, for the chat's empty state. */
export function QuestionChips({
  onAsk,
  questions = POPULAR_QUESTIONS,
  className,
}: {
  onAsk(text: string): void;
  questions?: SuggestedQuestion[];
  className?: string;
}) {
  return (
    <div className={cn('flex flex-wrap gap-[7px]', className)}>
      {questions.map((q) => (
        <button
          key={q.text}
          type="button"
          lang={q.lang}
          onClick={() => onAsk(q.text)}
          className="text-brand-text bg-surface focus-visible:ring-ring/60 hover:bg-tint-purple border-chip-border min-h-8 rounded-lg border px-[9px] py-[7px] text-left text-[11px] font-bold outline-none focus-visible:ring-[3px] motion-safe:transition-colors"
        >
          {q.text}
        </button>
      ))}
    </div>
  );
}
