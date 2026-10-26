'use client';

import {
  EyeIcon,
  FileTextIcon,
  GlobeIcon,
  type LucideIcon,
  MoreHorizontalIcon,
  NotebookPenIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  Trash2Icon,
} from 'lucide-react';
import { StatusPill } from '@/components/dashboard/status-pill';
import { RAG_SOURCE_STATUS, RAG_SOURCE_TYPE, styleOf } from '@/components/dashboard/status-tones';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { RagSource, RagSourceType } from '@/lib/api-client';
import { formatBytes, formatRelative } from '@/lib/format';

export const SOURCE_ICON: Record<RagSourceType, LucideIcon> = {
  document: FileTextIcon,
  link: GlobeIcon,
  text: NotebookPenIcon,
};

/** Where a source came from, in one line under its name. */
export function sourceOrigin(source: RagSource): string | null {
  if (source.source_type === 'link') return source.source_url;
  if (source.source_type === 'document') {
    const size = source.size_bytes ? formatBytes(source.size_bytes) : null;
    return [source.filename, size].filter(Boolean).join(', ') || null;
  }
  return null;
}

export function SourceTable({
  sources,
  onView,
  onReindex,
  onRetry,
  onDelete,
}: {
  sources: RagSource[];
  onView: (source: RagSource) => void;
  onReindex: (source: RagSource) => void;
  onRetry: (source: RagSource) => void;
  onDelete: (source: RagSource) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-full min-w-56">Source</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Passages</TableHead>
          <TableHead>Updated</TableHead>
          <TableHead className="w-12">
            <span className="sr-only">Actions</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sources.map((source) => {
          const Icon = SOURCE_ICON[source.source_type] ?? FileTextIcon;
          const status = styleOf(RAG_SOURCE_STATUS, source.status);
          const busy = source.status === 'pending' || source.status === 'processing';
          const failed = source.status === 'failed' || source.latest_job?.status === 'failed';
          const error = source.error ?? source.latest_job?.error ?? undefined;
          const origin = sourceOrigin(source);
          return (
            <TableRow key={source.id}>
              <TableCell className="max-w-0 py-2.5">
                <button
                  type="button"
                  onClick={() => onView(source)}
                  className="group focus-visible:ring-ring/50 flex w-full min-w-0 items-center gap-3 rounded-sm text-left outline-none focus-visible:ring-[3px]"
                >
                  <span className="bg-secondary text-secondary-foreground flex size-8 shrink-0 items-center justify-center rounded-md">
                    <Icon className="size-4" aria-hidden="true" />
                    <span className="sr-only">{RAG_SOURCE_TYPE[source.source_type]}</span>
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium group-hover:underline group-hover:underline-offset-2">
                      {source.name}
                    </span>
                    {origin && (
                      <span className="text-muted-foreground block truncate text-xs">{origin}</span>
                    )}
                  </span>
                </button>
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1.5">
                  <StatusPill
                    tone={status.tone}
                    pulse={status.pulse}
                    title={failed ? error : undefined}
                  >
                    {status.label}
                  </StatusPill>
                  {source.file_changed && !busy && (
                    <StatusPill tone="warning" title="The document changed since it was embedded">
                      Changed
                    </StatusPill>
                  )}
                </div>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {busy && source.chunk_count === 0 ? '—' : source.chunk_count.toLocaleString()}
              </TableCell>
              <TableCell className="text-muted-foreground whitespace-nowrap">
                {formatRelative(source.last_indexed_at ?? source.updated_at)}
              </TableCell>
              <TableCell className="py-1.5">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Actions for ${source.name}`}
                    >
                      <MoreHorizontalIcon aria-hidden="true" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-44">
                    <DropdownMenuItem onSelect={() => onView(source)}>
                      <EyeIcon aria-hidden="true" />
                      View details
                    </DropdownMenuItem>
                    {failed ? (
                      <DropdownMenuItem onSelect={() => onRetry(source)} disabled={busy}>
                        <RotateCcwIcon aria-hidden="true" />
                        Try again
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem onSelect={() => onReindex(source)} disabled={busy}>
                        <RefreshCwIcon aria-hidden="true" />
                        {source.file_changed ? 'Re-embed changes' : 'Reindex'}
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      variant="destructive"
                      onSelect={() => onDelete(source)}
                      disabled={source.status === 'processing'}
                    >
                      <Trash2Icon aria-hidden="true" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
