'use client';

import { FormField } from '@/components/dashboard/form-field';
import { SectionCard } from '@/components/dashboard/section-card';
import { SwitchRow } from '@/components/dashboard/switch-row';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { AgentConfigOptions } from '@/lib/api-client';
import type { ConfigDraftApi } from './use-config-draft';

const DEFAULT_MODEL_VALUE = '__server_default__';

/** The quick-reply switches: a small, fast model that answers the simple turns of a voice call
 * and fills the wait while a search runs. */
export function QuickReplySection({
  form,
  options,
}: {
  form: ConfigDraftApi;
  options: AgentConfigOptions;
}) {
  const { draft, saved, errors, set } = form;
  const defaultLabel =
    options.quick_reply_models.find((model) => model.id === saved.quick_reply_model_default)
      ?.label ?? saved.quick_reply_model_default;

  return (
    <SectionCard
      title="Quick replies"
      description="A small, fast model that makes voice calls feel quicker. Voice calls only: it needs the turn gate and an OpenRouter key, and applies from the next call."
    >
      <SwitchRow
        label="Use quick replies"
        description="When off, every reply comes from the language model above, as before."
        checked={draft.quick_reply_enabled}
        onCheckedChange={(value) => set('quick_reply_enabled', value)}
        className="pt-0"
      />
      {draft.quick_reply_enabled && (
        <div className="mt-2 border-t pt-2">
          <SwitchRow
            label="Fast answers"
            description="The small model answers turns that need no search: greetings, small talk, questions about what was already said. Anything else goes to the main model."
            checked={draft.quick_fast_answer}
            onCheckedChange={(value) => set('quick_fast_answer', value)}
          />
          <SwitchRow
            label="Filler line"
            description="A short line, such as “let me look for that”, spoken while a listing or offer search runs."
            checked={draft.quick_filler}
            onCheckedChange={(value) => set('quick_filler', value)}
          />
          <div className="grid gap-4 pt-3 sm:grid-cols-2">
            <FormField
              id="quick_reply_model"
              label="Quick reply model"
              error={errors.quick_reply_model}
              hint="Faster models answer sooner; check that it speaks Bangla well before switching."
            >
              {(control) => (
                <Select
                  value={draft.quick_reply_model || DEFAULT_MODEL_VALUE}
                  onValueChange={(value) =>
                    set('quick_reply_model', value === DEFAULT_MODEL_VALUE ? '' : value)
                  }
                >
                  <SelectTrigger {...control} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DEFAULT_MODEL_VALUE}>
                      Server default ({defaultLabel})
                    </SelectItem>
                    {options.quick_reply_models.map((model) => (
                      <SelectItem key={model.id} value={model.id}>
                        {model.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </FormField>
          </div>
        </div>
      )}
    </SectionCard>
  );
}
