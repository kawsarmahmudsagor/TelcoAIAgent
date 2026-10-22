'use client';

import { type DragEvent, useRef, useState } from 'react';
import {
  ChevronDownIcon,
  FileTextIcon,
  GlobeIcon,
  Loader2Icon,
  NotebookPenIcon,
  UploadIcon,
  XIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import { FormField } from '@/components/dashboard/form-field';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { api } from '@/lib/api-client';
import { formatBytes } from '@/lib/format';
import { cn } from '@/lib/shadcn/utils';

type Kind = 'document' | 'link' | 'text';

const ACCEPTED = ['.md', '.txt', '.pdf', '.xlsx', '.json'];
const MAX_BYTES = 20 * 1024 * 1024;
const MAX_TEXT = 200_000;

function fileProblem(file: File): string | null {
  const dot = file.name.lastIndexOf('.');
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : '';
  if (!ACCEPTED.includes(ext)) return `${ext || 'This file type'} isn’t supported`;
  if (file.size > MAX_BYTES) return `Larger than 20 MB (${formatBytes(file.size)})`;
  if (file.size === 0) return 'The file is empty';
  return null;
}

export function AddSourceDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const [kind, setKind] = useState<Kind>('document');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [docName, setDocName] = useState('');
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const [url, setUrl] = useState('');
  const [linkName, setLinkName] = useState('');
  const [crawlOpen, setCrawlOpen] = useState(false);
  const [maxDepth, setMaxDepth] = useState('1');
  const [maxPages, setMaxPages] = useState('25');
  const [domains, setDomains] = useState('');

  const [textName, setTextName] = useState('');
  const [text, setText] = useState('');

  function reset() {
    setKind('document');
    setError(null);
    setFiles([]);
    setDocName('');
    setUrl('');
    setLinkName('');
    setCrawlOpen(false);
    setMaxDepth('1');
    setMaxPages('25');
    setDomains('');
    setTextName('');
    setText('');
  }

  function close(next: boolean) {
    if (busy) return;
    onOpenChange(next);
    if (!next) reset();
  }

  function addFiles(list: FileList | null) {
    if (!list) return;
    setError(null);
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...Array.from(list).filter((f) => !names.has(f.name))];
    });
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }

  const badFiles = files.filter((f) => fileProblem(f));
  const depth = Number(maxDepth);
  const pages = Number(maxPages);
  const crawlError =
    !Number.isInteger(depth) || depth < 0 || depth > 3
      ? 'Link depth must be 0 to 3.'
      : !Number.isInteger(pages) || pages < 1 || pages > 100
        ? 'Pages must be 1 to 100.'
        : null;

  const canSubmit =
    kind === 'document'
      ? files.length > 0 && badFiles.length === 0
      : kind === 'link'
        ? /^https?:\/\/\S+$/i.test(url.trim()) && !crawlError
        : textName.trim().length > 0 && text.trim().length > 0 && text.length <= MAX_TEXT;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === 'document') {
        const name = files.length === 1 ? docName.trim() || undefined : undefined;
        const results = await Promise.allSettled(
          files.map((file) => api.rag.uploadDocument(file, name))
        );
        const failed = results
          .map((r, i) => (r.status === 'rejected' ? { file: files[i], reason: r.reason } : null))
          .filter((x): x is { file: File; reason: unknown } => x !== null);
        const added = results.length - failed.length;
        if (added > 0) {
          toast.success(added === 1 ? 'Document added' : `${added} documents added`, {
            description: 'Embedding runs in the background.',
          });
          onCreated();
        }
        if (failed.length > 0) {
          setFiles(failed.map((f) => f.file));
          setError(
            failed
              .map(
                (f) => `${f.file.name}: ${f.reason instanceof Error ? f.reason.message : 'failed'}`
              )
              .join('\n')
          );
          return;
        }
      } else if (kind === 'link') {
        const allowed = domains
          .split(/[\s,]+/)
          .map((d) => d.trim())
          .filter(Boolean);
        await api.rag.addLink({
          url: url.trim(),
          name: linkName.trim() || null,
          max_depth: depth,
          max_pages: pages,
          allowed_domains: allowed,
        });
        toast.success('Website added', { description: 'Crawling runs in the background.' });
        onCreated();
      } else {
        await api.rag.addText({ name: textName.trim(), text });
        toast.success('Text added', { description: textName.trim() });
        onCreated();
      }
      onOpenChange(false);
      reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add the source.');
    } finally {
      setBusy(false);
    }
  }

  const submitLabel =
    kind === 'document'
      ? files.length > 1
        ? `Add ${files.length} documents`
        : 'Add document'
      : kind === 'link'
        ? 'Add website'
        : 'Add text';

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Add a source</DialogTitle>
          <DialogDescription>
            The agent can search it once it shows as Ready, usually within a minute.
          </DialogDescription>
        </DialogHeader>

        <form id="add-source" onSubmit={submit} className="grid gap-4">
          <Tabs
            value={kind}
            onValueChange={(v) => {
              setKind(v as Kind);
              setError(null);
            }}
            className="gap-4"
          >
            <TabsList className="w-full">
              <TabsTrigger value="document">
                <FileTextIcon aria-hidden="true" />
                Document
              </TabsTrigger>
              <TabsTrigger value="link">
                <GlobeIcon aria-hidden="true" />
                Website
              </TabsTrigger>
              <TabsTrigger value="text">
                <NotebookPenIcon aria-hidden="true" />
                Text
              </TabsTrigger>
            </TabsList>

            <TabsContent value="document" className="grid gap-4">
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={cn(
                  'flex flex-col items-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center',
                  dragging ? 'border-primary bg-primary/5' : 'bg-muted/40'
                )}
              >
                <UploadIcon className="text-muted-foreground size-6" aria-hidden="true" />
                <p className="text-sm">
                  Drop files here or{' '}
                  <button
                    type="button"
                    onClick={() => fileInput.current?.click()}
                    className="text-primary font-medium underline underline-offset-2"
                  >
                    choose files
                  </button>
                </p>
                <p className="text-muted-foreground text-xs">
                  PDF, plain text or Markdown, Excel (.xlsx) or JSON, up to 20 MB each
                </p>
                <input
                  ref={fileInput}
                  type="file"
                  multiple
                  accept={ACCEPTED.join(',')}
                  className="sr-only"
                  tabIndex={-1}
                  onChange={(e) => {
                    addFiles(e.target.files);
                    e.target.value = '';
                  }}
                />
              </div>

              {files.length > 0 && (
                <ul className="divide-y rounded-md border">
                  {files.map((file) => {
                    const problem = fileProblem(file);
                    return (
                      <li key={file.name} className="flex items-center gap-3 px-3 py-2 text-sm">
                        <FileTextIcon
                          className="text-muted-foreground size-4 shrink-0"
                          aria-hidden="true"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">{file.name}</span>
                          <span
                            className={cn(
                              'block text-xs',
                              problem ? 'text-destructive' : 'text-muted-foreground'
                            )}
                          >
                            {problem ?? formatBytes(file.size)}
                          </span>
                        </span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Remove ${file.name}`}
                          onClick={() => setFiles((prev) => prev.filter((f) => f !== file))}
                          disabled={busy}
                        >
                          <XIcon aria-hidden="true" />
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              )}

              {files.length === 1 && (
                <FormField id="doc-name" label="Name" hint="Optional. Defaults to the file name.">
                  {(control) => (
                    <Input
                      {...control}
                      value={docName}
                      onChange={(e) => setDocName(e.target.value)}
                      maxLength={255}
                      placeholder={files[0].name}
                    />
                  )}
                </FormField>
              )}
            </TabsContent>

            <TabsContent value="link" className="grid gap-4">
              <FormField
                id="link-url"
                label="Start page"
                hint="Pages it links to on the same site are read too, up to the limits below."
              >
                {(control) => (
                  <Input
                    {...control}
                    type="url"
                    inputMode="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://example.com/faq"
                    autoComplete="url"
                  />
                )}
              </FormField>
              <FormField id="link-name" label="Name" hint="Optional. Defaults to the address.">
                {(control) => (
                  <Input
                    {...control}
                    value={linkName}
                    onChange={(e) => setLinkName(e.target.value)}
                    maxLength={255}
                  />
                )}
              </FormField>

              <div className="rounded-md border">
                <button
                  type="button"
                  aria-expanded={crawlOpen}
                  aria-controls="crawl-settings"
                  onClick={() => setCrawlOpen((v) => !v)}
                  className="focus-visible:ring-ring/50 flex w-full items-center justify-between gap-2 rounded-md px-3 py-2.5 text-left text-sm font-medium outline-none focus-visible:ring-[3px]"
                >
                  <span>
                    Crawl settings{' '}
                    <span className="text-muted-foreground font-normal">
                      {depth} {depth === 1 ? 'link' : 'links'} deep, up to {pages} pages
                    </span>
                  </span>
                  <ChevronDownIcon
                    className={cn(
                      'size-4 shrink-0 transition-transform',
                      crawlOpen && 'rotate-180'
                    )}
                    aria-hidden="true"
                  />
                </button>
                {crawlOpen && (
                  <div id="crawl-settings" className="grid gap-4 border-t p-3 sm:grid-cols-2">
                    <FormField
                      id="crawl-depth"
                      label="Link depth"
                      hint="0 reads only the start page."
                    >
                      {(control) => (
                        <Input
                          {...control}
                          type="number"
                          min={0}
                          max={3}
                          value={maxDepth}
                          onChange={(e) => setMaxDepth(e.target.value)}
                        />
                      )}
                    </FormField>
                    <FormField id="crawl-pages" label="Most pages" hint="1 to 100.">
                      {(control) => (
                        <Input
                          {...control}
                          type="number"
                          min={1}
                          max={100}
                          value={maxPages}
                          onChange={(e) => setMaxPages(e.target.value)}
                        />
                      )}
                    </FormField>
                    <FormField
                      id="crawl-domains"
                      label="Other sites it may follow"
                      hint="Optional, comma separated. By default only the start page’s site."
                      className="sm:col-span-2"
                    >
                      {(control) => (
                        <Input
                          {...control}
                          value={domains}
                          onChange={(e) => setDomains(e.target.value)}
                          placeholder="help.example.com, docs.example.com"
                        />
                      )}
                    </FormField>
                    {crawlError && (
                      <p className="text-destructive text-xs sm:col-span-2" role="alert">
                        {crawlError}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="text" className="grid gap-4">
              <FormField id="text-name" label="Name">
                {(control) => (
                  <Input
                    {...control}
                    value={textName}
                    onChange={(e) => setTextName(e.target.value)}
                    maxLength={255}
                    placeholder="Viewing and booking FAQ"
                  />
                )}
              </FormField>
              <FormField
                id="text-body"
                label="Text"
                hint={`${text.length.toLocaleString()} of ${MAX_TEXT.toLocaleString()} characters. Markdown headings help split it into passages.`}
                error={text.length > MAX_TEXT ? 'Too long: split it into two sources.' : null}
              >
                {(control) => (
                  <Textarea
                    {...control}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    className="max-h-80 min-h-40"
                    placeholder={'## Can I bring a pet?\nMost Gulshan buildings allow small pets…'}
                  />
                )}
              </FormField>
            </TabsContent>
          </Tabs>

          {error && (
            <p
              className="bg-destructive/8 text-destructive rounded-md px-3 py-2 text-sm whitespace-pre-line"
              role="alert"
            >
              {error}
            </p>
          )}
        </form>

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" form="add-source" disabled={!canSubmit || busy}>
            {busy && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            {submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
