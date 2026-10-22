'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { CircleAlertIcon, Loader2Icon } from 'lucide-react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/dashboard/confirm-dialog';
import { FormField } from '@/components/dashboard/form-field';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { type AgentConfig, type ModelOption, api } from '@/lib/api-client';

const POLL_MS = 4000;

/**
 * The embedding model. Save never changes it: picking another one offers "Start re-embedding",
 * which re-embeds every source with the new model in the background (the old vectors keep
 * serving) and then switches over. While that runs, the config is polled and handed to
 * `onConfig`, with one toast when it finishes or fails.
 */
export function EmbeddingModelField({
  config,
  models,
  onConfig,
  disabled,
}: {
  config: AgentConfig;
  models: ModelOption[];
  onConfig: (config: AgentConfig) => void;
  /** No embedding key: nothing can be re-embedded. */
  disabled?: boolean;
}) {
  const [selected, setSelected] = useState(config.embedding_model);
  const [confirming, setConfirming] = useState(false);
  const [starting, setStarting] = useState(false);
  const status = config.embedding_migration_status;
  const lastStatus = useRef(status);
  const running = status === 'running';

  // After a switch completes, the saved model moves; follow it.
  useEffect(() => {
    if (!running) setSelected(config.embedding_model);
  }, [config.embedding_model, running]);

  const poll = useCallback(async () => {
    try {
      const updated = await api.agentConfig.get();
      if (lastStatus.current === 'running') {
        if (updated.embedding_migration_status === 'succeeded') {
          toast.success('Re-embedding finished', {
            description: `The knowledge base now uses ${updated.embedding_model}.`,
          });
        } else if (updated.embedding_migration_status === 'failed') {
          toast.error('Re-embedding failed', {
            description: updated.embedding_migration_error ?? undefined,
          });
        }
      }
      lastStatus.current = updated.embedding_migration_status;
      onConfig(updated);
    } catch {
      // A missed poll is retried on the next tick.
    }
  }, [onConfig]);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => void poll(), POLL_MS);
    return () => clearInterval(id);
  }, [running, poll]);

  async function start() {
    setStarting(true);
    try {
      const updated = await api.agentConfig.migrateEmbedding(selected);
      lastStatus.current = updated.embedding_migration_status;
      onConfig(updated);
      setConfirming(false);
      toast.message('Re-embedding started', {
        description: 'The current model keeps answering until it finishes.',
      });
    } catch (err) {
      toast.error('Could not start re-embedding', {
        description: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setStarting(false);
    }
  }

  const label = (id: string | null) => models.find((m) => m.id === id)?.label ?? id ?? '';
  const pending = !running && selected !== config.embedding_model;

  return (
    <div className="grid gap-3">
      <FormField
        id="embedding_model"
        label="Embedding model"
        hint="Turns text into vectors for search. Switching re-embeds every source."
      >
        {(control) => (
          <Select value={selected} onValueChange={setSelected} disabled={running || disabled}>
            <SelectTrigger {...control} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {models.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </FormField>

      {running && (
        <p
          className="bg-info/10 text-info flex items-center gap-2 rounded-md px-3 py-2 text-sm"
          role="status"
        >
          <Loader2Icon className="size-4 shrink-0 motion-safe:animate-spin" aria-hidden="true" />
          Re-embedding with {label(config.embedding_migration_target)}. The current model keeps
          answering until it finishes.
        </p>
      )}

      {status === 'failed' && config.embedding_migration_error && !pending && (
        <p
          className="bg-destructive/8 text-destructive flex gap-2 rounded-md px-3 py-2 text-sm"
          role="alert"
        >
          <CircleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>Last re-embedding failed: {config.embedding_migration_error}</span>
        </p>
      )}

      {pending && (
        <div className="bg-muted/60 grid gap-3 rounded-md border p-3">
          <p className="text-sm">
            Re-embed every source with <strong>{label(selected)}</strong>? It runs in the background
            and can take a few minutes on a large knowledge base.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" onClick={() => setConfirming(true)}>
              Start re-embedding
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setSelected(config.embedding_model)}
            >
              Keep {label(config.embedding_model)}
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Start re-embedding?"
        description={`Every knowledge source is embedded again with ${label(selected)}, which uses API credits. Search keeps using ${label(config.embedding_model)} until it finishes.`}
        confirmLabel="Start re-embedding"
        destructive={false}
        onConfirm={start}
        busy={starting}
      />
    </div>
  );
}
