'use client';

import { useId } from 'react';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/shadcn/utils';

interface SwitchRowProps {
  label: string;
  description?: React.ReactNode;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}

/** A setting that is on or off: what it does on the left, the switch on the right. The text
 * block is the switch's label, so clicking it toggles too. */
export function SwitchRow({
  label,
  description,
  checked,
  onCheckedChange,
  disabled,
  className,
}: SwitchRowProps) {
  const id = useId();
  const descriptionId = `${id}-description`;
  return (
    <div className={cn('flex items-start justify-between gap-4 py-3', className)}>
      <label htmlFor={id} className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{label}</span>
        {description && (
          <span id={descriptionId} className="text-muted-foreground mt-0.5 block text-sm">
            {description}
          </span>
        )}
      </label>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        aria-describedby={description ? descriptionId : undefined}
        className="mt-0.5"
      />
    </div>
  );
}
