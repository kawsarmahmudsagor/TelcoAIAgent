'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/dashboard/confirm-dialog';
import { FormField } from '@/components/dashboard/form-field';
import { SectionCard } from '@/components/dashboard/section-card';
import { Input } from '@/components/ui/input';
import { type AgentConfigOptions, api } from '@/lib/api-client';
import { TemplateEditor } from './template-editor';
import type { ConfigDraftApi } from './use-config-draft';

export function AgentTab({ form, options }: { form: ConfigDraftApi; options: AgentConfigOptions }) {
  const { draft, saved, errors, set, accept } = form;
  const [promptUnlocked, setPromptUnlocked] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const placeholders = (field: string) => options.placeholders[field] ?? [];

  async function resetPrompt() {
    setResetting(true);
    try {
      const updated = await api.agentConfig.resetPrompt();
      // Put the draft's prompt back to the saved one first, so `accept` moves it to the default.
      set('prompt_identity_rules', saved.prompt_identity_rules);
      accept(updated);
      setPromptUnlocked(false);
      setConfirmReset(false);
      toast.success('Instructions reset to the default');
    } catch (err) {
      toast.error('Could not reset the instructions', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setResetting(false);
    }
  }

  // A greeting's reset: back to the saved text if that is the default, otherwise to null
  // ("use the default" on save; the server fills the text back in).
  function resetGreeting(key: 'greeting_inbound' | 'greeting_coldcall' | 'greeting_followup') {
    const isDefault = saved[`${key}_is_default`];
    set(key, isDefault ? saved[key] : null);
  }

  const promptIsDefault =
    saved.prompt_is_default && draft.prompt_identity_rules === saved.prompt_identity_rules;

  return (
    <div className="grid gap-4 sm:gap-6">
      <SectionCard
        title="Identity"
        description="How the agent introduces itself in chats and on calls."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="assistant_name" label="Assistant name" error={errors.assistant_name}>
            {(control) => (
              <Input
                {...control}
                value={draft.assistant_name}
                onChange={(e) => set('assistant_name', e.target.value)}
                maxLength={100}
                autoComplete="off"
              />
            )}
          </FormField>
          <FormField id="agency_name" label="Agency name" error={errors.agency_name}>
            {(control) => (
              <Input
                {...control}
                value={draft.agency_name}
                onChange={(e) => set('agency_name', e.target.value)}
                maxLength={255}
                autoComplete="organization"
              />
            )}
          </FormField>
          <FormField
            id="agency_phone"
            label="Contact phone"
            hint="The agent gives this number for details it doesn't have. Blank uses the default."
            error={errors.agency_phone}
          >
            {(control) => (
              <Input
                {...control}
                type="tel"
                value={draft.agency_phone}
                onChange={(e) => set('agency_phone', e.target.value)}
                maxLength={50}
                autoComplete="off"
              />
            )}
          </FormField>
          <FormField
            id="agency_address"
            label="Office address"
            hint="Offered alongside the phone number for an in-person visit."
            error={errors.agency_address}
          >
            {(control) => (
              <Input
                {...control}
                value={draft.agency_address}
                onChange={(e) => set('agency_address', e.target.value)}
                maxLength={255}
                autoComplete="off"
              />
            )}
          </FormField>
        </div>
      </SectionCard>

      <SectionCard
        title="Opening instructions"
        description="While left at the default, the agent opens with one of a few ready-made Bangla greetings, picked at random, so it starts speaking right away. A customised text is an instruction, not a script: the agent writes its own first message from it. A scheduled call to a lead with a booked viewing uses the follow-up greeting; any other scheduled call is a cold call."
      >
        <div className="grid gap-5">
          <GreetingEditor
            id="greeting_inbound"
            label="When a customer starts a chat or call"
            value={draft.greeting_inbound}
            savedIsDefault={saved.greeting_inbound_is_default}
            savedValue={saved.greeting_inbound}
            placeholders={placeholders('greeting_inbound')}
            error={errors.greeting_inbound}
            onChange={(value) => set('greeting_inbound', value)}
            onReset={() => resetGreeting('greeting_inbound')}
          />
          <GreetingEditor
            id="greeting_coldcall"
            label="Cold call: the lead has no booked viewing"
            value={draft.greeting_coldcall}
            savedIsDefault={saved.greeting_coldcall_is_default}
            savedValue={saved.greeting_coldcall}
            placeholders={placeholders('greeting_coldcall')}
            error={errors.greeting_coldcall}
            onChange={(value) => set('greeting_coldcall', value)}
            onReset={() => resetGreeting('greeting_coldcall')}
          />
          <GreetingEditor
            id="greeting_followup"
            label="Follow-up call: the lead has a booked viewing"
            value={draft.greeting_followup}
            savedIsDefault={saved.greeting_followup_is_default}
            savedValue={saved.greeting_followup}
            placeholders={placeholders('greeting_followup')}
            error={errors.greeting_followup}
            onChange={(value) => set('greeting_followup', value)}
            onReset={() => resetGreeting('greeting_followup')}
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Instructions"
        description="The agent's standing instructions: who it is, how it behaves and what it must never do. Changes apply from the next chat or call."
      >
        <TemplateEditor
          id="prompt_identity_rules"
          label="Identity and rules"
          value={draft.prompt_identity_rules}
          onChange={(value) => set('prompt_identity_rules', value)}
          placeholders={placeholders('prompt_identity_rules')}
          isDefault={promptIsDefault}
          error={errors.prompt_identity_rules}
          rows={16}
          locked={!promptUnlocked}
          onUnlock={() => setPromptUnlocked(true)}
          onReset={saved.prompt_is_default ? undefined : () => setConfirmReset(true)}
          resetLabel="Reset to default"
          hint="Write literal braces as {{ and }}. Unknown placeholders are refused when you save."
        />
      </SectionCard>

      <ConfirmDialog
        open={confirmReset}
        onOpenChange={setConfirmReset}
        title="Reset the instructions?"
        description="Your custom instructions are replaced by the built-in default straight away. Other unsaved changes on this page are kept."
        confirmLabel="Reset instructions"
        onConfirm={resetPrompt}
        busy={resetting}
      />
    </div>
  );
}

function GreetingEditor({
  id,
  label,
  value,
  savedValue,
  savedIsDefault,
  placeholders,
  error,
  onChange,
  onReset,
}: {
  id: string;
  label: string;
  value: string | null;
  savedValue: string;
  savedIsDefault: boolean;
  placeholders: string[];
  error?: string;
  onChange: (value: string) => void;
  onReset: () => void;
}) {
  const pendingReset = value === null;
  const isDefault = savedIsDefault && value === savedValue;
  return (
    <TemplateEditor
      id={id}
      label={label}
      value={value ?? ''}
      onChange={onChange}
      placeholders={placeholders}
      isDefault={isDefault}
      error={error}
      rows={3}
      onReset={isDefault || pendingReset ? undefined : onReset}
      hint={
        pendingReset
          ? 'The default instruction will be used after you save.'
          : 'Leave empty to use the default.'
      }
    />
  );
}
