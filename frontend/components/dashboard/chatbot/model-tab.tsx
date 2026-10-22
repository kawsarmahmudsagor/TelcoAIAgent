'use client';

import { FormField } from '@/components/dashboard/form-field';
import { SecretKeyField } from '@/components/dashboard/secret-key-field';
import { SectionCard } from '@/components/dashboard/section-card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { AgentConfigOptions, LlmProvider, ReasoningEffort } from '@/lib/api-client';
import { QuickReplySection } from './quick-reply-section';
import type { ConfigDraftApi } from './use-config-draft';
import { VoiceSection } from './voice-section';

const LLM_PROVIDER_LABEL: Record<LlmProvider, string> = {
  openrouter: 'OpenRouter',
  gemini: 'Google Gemini',
};

const KEY_FALLBACK: Record<LlmProvider, string> = {
  openrouter: 'Not set: uses OPENROUTER_API_KEY from the server',
  gemini: 'Not set: uses GOOGLE_API_KEY from the server',
};

const REASONING_EFFORTS: ReasoningEffort[] = ['none', 'minimal', 'low', 'medium', 'high'];

const CUSTOM_MODEL_VALUE = '__custom_model__';
const DEFAULT_MODEL_VALUE = '__server_default__';

export function ModelTab({
  form,
  options,
  customModelSelected,
  setCustomModelSelected,
}: {
  form: ConfigDraftApi;
  options: AgentConfigOptions;
  customModelSelected: boolean;
  setCustomModelSelected: (selected: boolean) => void;
}) {
  const { draft, saved, errors, set } = form;
  const providerChanged = draft.llm_provider !== saved.llm_provider;
  const models = options.llm_models[draft.llm_provider] ?? [];
  const modelSelection =
    customModelSelected ||
    (draft.llm_model && !models.some((model) => model.id === draft.llm_model))
      ? CUSTOM_MODEL_VALUE
      : draft.llm_model || DEFAULT_MODEL_VALUE;

  function changeProvider(next: LlmProvider) {
    setCustomModelSelected(false);
    set('llm_provider', next);
    // The server forgets the model (and key) when the provider changes; mirror that here.
    set('llm_model', next === saved.llm_provider ? saved.llm_model : '');
    set('reasoning_effort', next === saved.llm_provider ? (saved.reasoning_effort ?? '') : '');
    if (next === saved.llm_provider) set('api_key', null);
  }

  return (
    <div className="grid gap-4 sm:gap-6">
      <SectionCard
        title="Language model"
        description="The model that writes the agent's replies in chats and on calls."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            id="llm_provider"
            label="Provider"
            error={errors.llm_provider}
            hint={
              providerChanged
                ? 'Switching provider clears the saved model and API key when you save.'
                : undefined
            }
          >
            {(control) => (
              <Select
                value={draft.llm_provider}
                onValueChange={(value) => changeProvider(value as LlmProvider)}
              >
                <SelectTrigger {...control} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {options.llm_providers.map((p) => (
                    <SelectItem key={p} value={p}>
                      {LLM_PROVIDER_LABEL[p] ?? p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>

          <FormField
            id="llm_model"
            label="Model"
            error={errors.llm_model}
            hint="Choose a model or the server default, or select Custom model ID to enter another model."
          >
            {(control) => (
              <>
                <Select
                  value={modelSelection}
                  onValueChange={(value) => {
                    if (value === CUSTOM_MODEL_VALUE) {
                      setCustomModelSelected(true);
                      return;
                    }
                    setCustomModelSelected(false);
                    set('llm_model', value === DEFAULT_MODEL_VALUE ? '' : value);
                  }}
                >
                  <SelectTrigger {...control} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DEFAULT_MODEL_VALUE}>Server default</SelectItem>
                    {models.map((model) => (
                      <SelectItem key={model.id} value={model.id}>
                        {model.label}
                      </SelectItem>
                    ))}
                    <SelectItem value={CUSTOM_MODEL_VALUE}>Custom model ID</SelectItem>
                  </SelectContent>
                </Select>
                {modelSelection === CUSTOM_MODEL_VALUE && (
                  <Input
                    {...control}
                    id={`${control.id}-custom`}
                    aria-label="Custom model ID"
                    value={draft.llm_model}
                    onChange={(event) => set('llm_model', event.target.value)}
                    placeholder="Enter model ID"
                    autoComplete="off"
                    spellCheck={false}
                    className="font-mono text-[13px]"
                  />
                )}
              </>
            )}
          </FormField>

          <FormField
            id="temperature"
            label="Temperature"
            error={errors.temperature}
            hint="0 to 2. Lower is more predictable; empty uses the model's default."
          >
            {(control) => (
              <Input
                {...control}
                type="number"
                inputMode="decimal"
                min={0}
                max={2}
                step={0.1}
                value={draft.temperature}
                onChange={(e) => set('temperature', e.target.value)}
                placeholder="Model default"
              />
            )}
          </FormField>

          <FormField
            id="max_output_tokens"
            label="Longest reply (tokens)"
            error={errors.max_output_tokens}
            hint="Caps each reply. Voice replies should stay short; empty means no cap."
          >
            {(control) => (
              <Input
                {...control}
                type="number"
                inputMode="numeric"
                min={1}
                max={32768}
                step={1}
                value={draft.max_output_tokens}
                onChange={(e) => set('max_output_tokens', e.target.value)}
                placeholder="No cap"
              />
            )}
          </FormField>

          {draft.llm_provider === 'openrouter' && (
            <FormField
              id="reasoning_effort"
              label="Reasoning effort"
              error={errors.reasoning_effort}
              hint="How long the model thinks before replying. Lower answers faster; voice calls rarely need more than minimal."
            >
              {(control) => (
                <Select
                  value={draft.reasoning_effort || DEFAULT_MODEL_VALUE}
                  onValueChange={(value) =>
                    set(
                      'reasoning_effort',
                      value === DEFAULT_MODEL_VALUE ? '' : (value as ReasoningEffort)
                    )
                  }
                >
                  <SelectTrigger {...control} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={DEFAULT_MODEL_VALUE}>
                      Server default ({saved.reasoning_effort_default})
                    </SelectItem>
                    {REASONING_EFFORTS.map((effort) => (
                      <SelectItem key={effort} value={effort}>
                        {effort}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </FormField>
          )}

          <div className="sm:col-span-2">
            <SecretKeyField
              id="api_key"
              label={`${LLM_PROVIDER_LABEL[draft.llm_provider]} API key`}
              stored={saved.has_api_key && !providerChanged}
              value={draft.api_key}
              onChange={(value) => set('api_key', value)}
              emptyPlaceholder={KEY_FALLBACK[draft.llm_provider]}
              disabled={!saved.encryption_available && !saved.has_api_key}
              hint={
                errors.api_key ? (
                  <span className="text-destructive">{errors.api_key}</span>
                ) : !saved.encryption_available ? (
                  <span className="text-warning">
                    The server has no SETTINGS_ENCRYPTION_KEY, so a key can’t be saved here. The key
                    from the server environment is used.
                  </span>
                ) : (
                  'Stored encrypted and never shown again. With OpenRouter, this key is also used for knowledge base embeddings.'
                )
              }
            />
          </div>
        </div>
      </SectionCard>

      <QuickReplySection form={form} options={options} />

      <VoiceSection form={form} options={options} />
    </div>
  );
}
