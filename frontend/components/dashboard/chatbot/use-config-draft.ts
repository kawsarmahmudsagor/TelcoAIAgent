'use client';

import { useCallback, useEffect, useState } from 'react';
import { type AgentConfig, ApiError, api } from '@/lib/api-client';
import {
  type ConfigDraft,
  type DraftKey,
  type FieldErrors,
  buildUpdate,
  changedKeys,
  draftFrom,
  parseServerErrors,
  rebase,
} from './config-draft';

export type SaveResult =
  | { ok: true; config: AgentConfig }
  | { ok: false; errors: FieldErrors; message: string | null };

/**
 * The Chatbot form's state: the config as saved, the draft being edited, per-field errors, and
 * one Save for every tab. `accept` takes a newer config from the server (a re-embed poll, a
 * prompt reset) and keeps the fields being edited. Closing the tab with unsaved edits asks first.
 */
export function useConfigDraft(initial: AgentConfig) {
  const [{ saved, draft }, setState] = useState(() => ({
    saved: initial,
    draft: draftFrom(initial),
  }));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const changed = changedKeys(draft, saved);
  const isDirty = changed.length > 0;

  useEffect(() => {
    if (!isDirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  function set<K extends DraftKey>(key: K, value: ConfigDraft[K]) {
    setState((prev) => ({ ...prev, draft: { ...prev.draft, [key]: value } }));
    // Editing a refused field clears its message.
    setErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  function update(change: (prev: ConfigDraft) => ConfigDraft) {
    setState((prev) => ({ ...prev, draft: change(prev.draft) }));
  }

  const accept = useCallback((updated: AgentConfig) => {
    setState((prev) => ({ saved: updated, draft: rebase(prev.draft, prev.saved, updated) }));
  }, []);

  function discard() {
    setState((prev) => ({ ...prev, draft: draftFrom(prev.saved) }));
    setErrors({});
  }

  async function save(): Promise<SaveResult> {
    const built = buildUpdate(draft, saved);
    if ('errors' in built) {
      setErrors(built.errors);
      return { ok: false, errors: built.errors, message: null };
    }
    setSaving(true);
    try {
      const updated = await api.agentConfig.update(built.payload);
      setState({ saved: updated, draft: draftFrom(updated) });
      setErrors({});
      return { ok: true, config: updated };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not save the settings.';
      if (err instanceof ApiError && err.status === 422) {
        const parsed = parseServerErrors(message);
        setErrors(parsed.errors);
        return { ok: false, errors: parsed.errors, message: parsed.rest };
      }
      return { ok: false, errors: {}, message };
    } finally {
      setSaving(false);
    }
  }

  return { saved, draft, changed, isDirty, errors, saving, set, update, accept, discard, save };
}

export type ConfigDraftApi = ReturnType<typeof useConfigDraft>;
