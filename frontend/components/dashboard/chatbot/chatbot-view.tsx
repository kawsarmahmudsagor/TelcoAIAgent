'use client';

import { useCallback, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Loader2Icon } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '@/components/dashboard/page-header';
import { Panel, TableState } from '@/components/dashboard/table-state';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { type LoadState, useLoad } from '@/hooks/useLoad';
import { type AgentConfig, type AgentConfigOptions, type RagSource, api } from '@/lib/api-client';
import { cn } from '@/lib/shadcn/utils';
import { AgentTab } from './agent-tab';
import { CHATBOT_TABS, type ChatbotTab, FIELD_TAB } from './config-draft';
import { KnowledgeTab } from './knowledge-tab';
import { ModelTab } from './model-tab';
import { useConfigDraft } from './use-config-draft';

const TAB_LABEL: Record<ChatbotTab, string> = {
  agent: 'Agent',
  model: 'Model and voice',
  knowledge: 'Knowledge',
};

const DESCRIPTION =
  'How the agent introduces itself, which model and voice it uses, and what it knows.';

/** /dashboard/chatbot. Reads `?tab=` (so it must render inside a Suspense boundary). */
export function ChatbotView() {
  const core = useLoad(
    async () => {
      const [config, options] = await Promise.all([
        api.agentConfig.get(),
        api.agentConfig.options(),
      ]);
      return { config, options };
    },
    [],
    { fallbackError: 'Could not load the agent settings. Is the API running?' }
  );
  // Separate, so a failure here only affects the source picker.
  const sources = useLoad(async () => (await api.rag.sources({ limit: 500 })).items, [], {
    fallbackError: 'Could not load knowledge sources.',
  });

  if (core.loading) return <ChatbotSkeleton />;
  if (core.error || !core.data) {
    return (
      <>
        <PageHeader title="Chatbot" description={DESCRIPTION} />
        <Panel>
          <TableState error={core.error} onRetry={() => void core.retry()} />
        </Panel>
      </>
    );
  }
  return <ChatbotForm initial={core.data.config} options={core.data.options} sources={sources} />;
}

function ChatbotForm({
  initial,
  options,
  sources,
}: {
  initial: AgentConfig;
  options: AgentConfigOptions;
  sources: LoadState<RagSource[]>;
}) {
  const form = useConfigDraft(initial);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [customModelSelected, setCustomModelSelected] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requested = searchParams.get('tab') as ChatbotTab | null;
  const tab: ChatbotTab = requested && CHATBOT_TABS.includes(requested) ? requested : 'agent';

  const setTab = useCallback(
    (next: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (next === 'agent') params.delete('tab');
      else params.set('tab', next);
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  const tabsWithErrors = new Set(
    (Object.keys(form.errors) as (keyof typeof form.errors)[]).map((key) => FIELD_TAB[key])
  );
  const tabsWithEdits = new Set(form.changed.map((key) => FIELD_TAB[key]));

  async function save() {
    setSaveError(null);
    const result = await form.save();
    if (result.ok) {
      toast.success('Settings saved', {
        description: 'The agent uses them from its next chat or call.',
      });
      void sources.reload();
      return;
    }
    const fieldTabs = (Object.keys(result.errors) as (keyof typeof result.errors)[]).map(
      (key) => FIELD_TAB[key]
    );
    if (fieldTabs.length && !fieldTabs.includes(tab)) setTab(fieldTabs[0]);
    // Shown in the save bar rather than a toast, which would sit on top of it.
    setSaveError(
      result.message ??
        (fieldTabs.length === 1
          ? 'One value needs fixing. It is marked above.'
          : `${fieldTabs.length} values need fixing. They are marked above.`)
    );
  }

  return (
    <>
      <PageHeader title="Chatbot" description={DESCRIPTION} />
      <div>
        <Tabs value={tab} onValueChange={setTab} className="gap-5">
          <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
            <TabsList className="h-10">
              {CHATBOT_TABS.map((t) => (
                <TabsTrigger key={t} value={t} className="px-3">
                  {TAB_LABEL[t]}
                  {(tabsWithErrors.has(t) || tabsWithEdits.has(t)) && (
                    <span
                      className={cn(
                        'size-1.5 rounded-full',
                        tabsWithErrors.has(t) ? 'bg-destructive' : 'bg-brass'
                      )}
                      aria-label={tabsWithErrors.has(t) ? 'has errors' : 'has unsaved changes'}
                    />
                  )}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          <TabsContent value="agent">
            <AgentTab form={form} options={options} />
          </TabsContent>
          <TabsContent value="model">
            <ModelTab
              form={form}
              options={options}
              customModelSelected={customModelSelected}
              setCustomModelSelected={setCustomModelSelected}
            />
          </TabsContent>
          <TabsContent value="knowledge">
            <KnowledgeTab form={form} options={options} sources={sources} />
          </TabsContent>
        </Tabs>

        <SaveBar
          dirty={form.isDirty}
          count={form.changed.length}
          saving={form.saving}
          error={saveError}
          onDiscard={() => {
            setSaveError(null);
            setCustomModelSelected(false);
            form.discard();
          }}
          onSave={() => void save()}
        />
      </div>
    </>
  );
}

/** One Save for all three tabs, pinned to the bottom of the viewport. */
function SaveBar({
  dirty,
  count,
  saving,
  error,
  onDiscard,
  onSave,
}: {
  dirty: boolean;
  count: number;
  saving: boolean;
  error: string | null;
  onDiscard: () => void;
  onSave: () => void;
}) {
  return (
    // On a phone it only appears once there is something to save, so it doesn't cover content.
    <div
      className={cn(
        'sticky bottom-0 z-20 -mx-4 mt-6 px-4 pb-4 sm:-mx-8 sm:px-8',
        !dirty && 'max-sm:hidden'
      )}
    >
      <div
        className={cn(
          'bg-card flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3',
          dirty && 'border-brass/60 shadow-lg',
          error && 'border-destructive/50'
        )}
      >
        <p className="min-w-0 flex-1 text-sm" role="status" aria-live="polite">
          {error && dirty ? (
            <span className="text-destructive">{error}</span>
          ) : dirty ? (
            <>
              <span className="font-medium">Unsaved changes</span>
              <span className="text-muted-foreground">
                {' '}
                in {count} {count === 1 ? 'field' : 'fields'}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground">All changes saved</span>
          )}
        </p>
        <div className="flex gap-2">
          {dirty && (
            <Button type="button" variant="ghost" onClick={onDiscard} disabled={saving}>
              Discard
            </Button>
          )}
          <Button type="button" onClick={onSave} disabled={!dirty || saving}>
            {saving && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            Save changes
          </Button>
        </div>
      </div>
    </div>
  );
}

function ChatbotSkeleton() {
  return (
    <>
      <PageHeader title="Chatbot" description={DESCRIPTION} />
      <div className="grid gap-5" aria-busy="true" aria-label="Loading settings">
        <Skeleton className="h-10 w-80 max-w-full" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    </>
  );
}
