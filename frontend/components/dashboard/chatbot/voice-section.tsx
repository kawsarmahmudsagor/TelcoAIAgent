'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2Icon, PlayIcon, SquareIcon } from 'lucide-react';
import { FormField } from '@/components/dashboard/form-field';
import { SectionCard } from '@/components/dashboard/section-card';
import { SwitchRow } from '@/components/dashboard/switch-row';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  type AgentConfigOptions,
  type PreviewLanguage,
  type SttTtsProvider,
  api,
} from '@/lib/api-client';
import type { ConfigDraftApi } from './use-config-draft';

const VOICE_PROVIDER_LABEL: Record<SttTtsProvider, string> = {
  elevenlabs: 'ElevenLabs',
  openrouter: 'ElevenLabs via OpenRouter',
  deepgram: 'Deepgram',
};

const PROVIDER_HINT: Partial<Record<SttTtsProvider, string>> = {
  elevenlabs: 'Uses the ElevenLabs keys from the server (ELEVENLABS_API_KEYS).',
  openrouter:
    'Uses the OpenRouter API key. Speech is transcribed after the caller stops talking, so replies start about 1–2 s later.',
  deepgram: 'English voices only.',
};

const PREVIEW_LANGUAGES: { id: PreviewLanguage; label: string }[] = [
  { id: 'en', label: 'English' },
  { id: 'bn', label: 'বাংলা' },
];

export function VoiceSection({
  form,
  options,
}: {
  form: ConfigDraftApi;
  options: AgentConfigOptions;
}) {
  const { draft, saved, errors, set } = form;
  const provider = draft.stt_tts_provider;
  const isDeepgram = provider === 'deepgram';
  const ttsModels = options.elevenlabs_tts_models[provider] ?? [];

  function changeProvider(next: SttTtsProvider) {
    set('stt_tts_provider', next);
    // ElevenLabs and OpenRouter name the models differently, and the server resets the model
    // when the provider changes; mirror that so Save doesn't send the old provider's id.
    set('elevenlabs_tts_model', next === saved.stt_tts_provider ? saved.elevenlabs_tts_model : '');
  }

  return (
    <SectionCard
      title="Voice"
      description="Speech recognition and the voice the agent speaks with on calls. Applies from the next call; no restart needed."
    >
      <SwitchRow
        label="Voice responses"
        description="Off: logged-in customers can still speak; the assistant replies in text. Guests always chat in text. Applies to new chats."
        checked={draft.voice_replies_enabled}
        onCheckedChange={(value) => set('voice_replies_enabled', value)}
        className="mb-2 border-b pt-0 pb-3"
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          id="stt_tts_provider"
          label="Voice provider"
          error={errors.stt_tts_provider}
          hint={PROVIDER_HINT[provider]}
        >
          {(control) => (
            <Select
              value={provider}
              onValueChange={(value) => changeProvider(value as SttTtsProvider)}
            >
              <SelectTrigger {...control} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {options.stt_tts_providers.map((p) => (
                  <SelectItem key={p} value={p}>
                    {VOICE_PROVIDER_LABEL[p] ?? p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </FormField>

        {isDeepgram ? (
          <FormField id="deepgram_tts_model" label="Voice" error={errors.deepgram_tts_model}>
            {(control) => (
              <Select
                value={draft.deepgram_tts_model}
                onValueChange={(value) => set('deepgram_tts_model', value)}
              >
                <SelectTrigger {...control} className="w-full">
                  <SelectValue placeholder="Choose a voice" />
                </SelectTrigger>
                <SelectContent>
                  {withCurrent(options.deepgram_tts_voices, draft.deepgram_tts_model).map((v) => (
                    <SelectItem key={v.id} value={v.id}>
                      {v.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>
        ) : (
          <FormField
            id="elevenlabs_tts_model"
            label="Voice model"
            error={errors.elevenlabs_tts_model}
            hint="Only models marked Bangla can speak Bangla replies."
          >
            {(control) => (
              <Select
                value={draft.elevenlabs_tts_model}
                onValueChange={(value) => set('elevenlabs_tts_model', value)}
              >
                <SelectTrigger {...control} className="w-full">
                  <SelectValue placeholder="Server default" />
                </SelectTrigger>
                <SelectContent>
                  {withCurrent(ttsModels, draft.elevenlabs_tts_model).map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </FormField>
        )}

        {!isDeepgram && (
          <>
            <FormField id="elevenlabs_voice" label="Voice" error={errors.elevenlabs_voice_id}>
              {(control) => (
                <Select
                  value={draft.elevenlabs_voice_id}
                  onValueChange={(value) => set('elevenlabs_voice_id', value)}
                >
                  <SelectTrigger {...control} className="w-full">
                    <SelectValue placeholder="Choose a voice" />
                  </SelectTrigger>
                  <SelectContent>
                    {withCurrent(options.elevenlabs_voices, draft.elevenlabs_voice_id).map((v) => (
                      <SelectItem key={v.id} value={v.id}>
                        {v.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </FormField>

            <FormField
              id="elevenlabs_voice_id"
              label="Voice ID"
              hint="Pick a voice above, or paste any voice ID from your ElevenLabs voice library."
            >
              {(control) => (
                <Input
                  {...control}
                  value={draft.elevenlabs_voice_id}
                  onChange={(e) => set('elevenlabs_voice_id', e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  className="font-mono text-[13px]"
                />
              )}
            </FormField>
          </>
        )}

        {provider === 'elevenlabs' && (
          <>
            <FormField
              id="elevenlabs_stt_model"
              label="Transcription mode"
              error={errors.elevenlabs_stt_model}
              hint={
                draft.elevenlabs_stt_model === 'scribe_v2_realtime'
                  ? 'Replies start sooner, but the language is guessed from the first moments of speech, so Bangla can come out as another language.'
                  : 'Each turn is transcribed whole after the caller stops: reliable Bangla, replies start about 1–2 s later.'
              }
            >
              {(control) => (
                <Select
                  value={draft.elevenlabs_stt_model}
                  onValueChange={(value) => set('elevenlabs_stt_model', value)}
                >
                  <SelectTrigger {...control} className="w-full">
                    <SelectValue placeholder="Server default" />
                  </SelectTrigger>
                  <SelectContent>
                    {withCurrent(options.elevenlabs_stt_models, draft.elevenlabs_stt_model).map(
                      (m) => (
                        <SelectItem key={m.id} value={m.id}>
                          {m.label}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              )}
            </FormField>

            <FormField
              id="elevenlabs_stt_language"
              label="Caller language"
              error={errors.elevenlabs_stt_language}
              hint="Auto-detect hears Bangla and English. Pick one language only if every caller speaks it."
            >
              {(control) => (
                <Select
                  value={draft.elevenlabs_stt_language}
                  onValueChange={(value) => set('elevenlabs_stt_language', value)}
                >
                  <SelectTrigger {...control} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {withCurrent(
                      options.elevenlabs_stt_languages,
                      draft.elevenlabs_stt_language
                    ).map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </FormField>
          </>
        )}

        <VoicePreview
          className="sm:col-span-2"
          provider={provider}
          voice={isDeepgram ? draft.deepgram_tts_model : draft.elevenlabs_voice_id}
          model={isDeepgram ? null : draft.elevenlabs_tts_model}
        />
      </div>
    </SectionCard>
  );
}

/**
 * Plays a short sample line with the current (possibly unsaved) choices. A clip is fetched once
 * per provider/voice/model/language and replayed from memory, since each fetch spends credits.
 */
function VoicePreview({
  provider,
  voice,
  model,
  className,
}: {
  provider: SttTtsProvider;
  voice: string;
  model: string | null;
  className?: string;
}) {
  const [loading, setLoading] = useState<PreviewLanguage | null>(null);
  const [playing, setPlaying] = useState<PreviewLanguage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const clipsRef = useRef(new Map<string, string>());

  useEffect(() => {
    const clips = clipsRef.current;
    return () => {
      audioRef.current?.pause();
      for (const url of clips.values()) URL.revokeObjectURL(url);
      clips.clear();
    };
  }, []);

  // A changed choice makes the old message stale.
  useEffect(() => setError(null), [provider, voice, model]);

  function stop() {
    audioRef.current?.pause();
    audioRef.current = null;
    setPlaying(null);
  }

  async function play(language: PreviewLanguage) {
    if (playing === language) {
      stop();
      return;
    }
    stop();
    setError(null);
    const key = [provider, voice.trim(), model ?? '', language].join('|');
    let url = clipsRef.current.get(key);
    if (!url) {
      setLoading(language);
      try {
        const blob = await api.agentConfig.previewVoice({
          stt_tts_provider: provider,
          voice: voice.trim(),
          model: model || null,
          language,
        });
        url = URL.createObjectURL(blob);
        clipsRef.current.set(key, url);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'The preview failed.');
        return;
      } finally {
        setLoading(null);
      }
    }
    const audio = new Audio(url);
    audioRef.current = audio;
    audio.onended = () => setPlaying((current) => (current === language ? null : current));
    try {
      await audio.play();
      setPlaying(language);
    } catch {
      setError('Your browser blocked playback. Click the button again.');
    }
  }

  const noVoice = !voice.trim();
  return (
    <div className={className}>
      <div className="grid gap-2 rounded-lg border border-dashed p-3 sm:p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="grid gap-0.5">
            <p className="text-sm font-medium">Preview</p>
            <p className="text-muted-foreground text-xs">
              A short sample line with the choices above, saved or not. Each new sample uses the
              provider’s credits.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {PREVIEW_LANGUAGES.map(({ id, label }) => {
              const banglaBlocked = id === 'bn' && provider === 'deepgram';
              const Icon = loading === id ? Loader2Icon : playing === id ? SquareIcon : PlayIcon;
              return (
                <Button
                  key={id}
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={noVoice || banglaBlocked || (loading !== null && loading !== id)}
                  onClick={() => play(id)}
                  aria-pressed={playing === id}
                  title={banglaBlocked ? 'Deepgram’s voices are English-only' : undefined}
                >
                  <Icon className={loading === id ? 'animate-spin' : undefined} />
                  {label}
                </Button>
              );
            })}
          </div>
        </div>
        {error && (
          <p role="alert" className="text-destructive text-xs">
            {error}
          </p>
        )}
        {!error && provider === 'deepgram' && (
          <p className="text-muted-foreground text-xs">
            Deepgram has no Bangla voice, so Bangla replies won’t sound right.
          </p>
        )}
      </div>
    </div>
  );
}

/** The saved value stays selectable even when it isn't in the suggestion list. */
function withCurrent(list: { id: string; label: string }[], current: string) {
  if (!current || list.some((item) => item.id === current)) return list;
  return [{ id: current, label: current }, ...list];
}
