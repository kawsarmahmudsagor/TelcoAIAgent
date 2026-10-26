import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export const MSISDN_PATTERN = '01[0-9]{9}';
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 72;

/** Digits only, at most 11: what a typed or pasted mobile number keeps. */
export const msisdnDigits = (raw: string) => raw.replace(/\D/g, '').slice(0, 11);

/** A labelled input with an optional hint under it. */
export function Field({
  id,
  label,
  hint,
  ...input
}: { id: string; label: string; hint?: string } & React.ComponentProps<typeof Input>) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        className="h-11"
        aria-describedby={hint ? `${id}-hint` : undefined}
        {...input}
      />
      {hint && (
        <p id={`${id}-hint`} className="text-muted-foreground text-xs">
          {hint}
        </p>
      )}
    </div>
  );
}

/** The 11-digit mobile number field. */
export function MsisdnField({
  id = 'msisdn',
  value,
  onChange,
  ...rest
}: {
  id?: string;
  value: string;
  onChange(value: string): void;
} & Omit<React.ComponentProps<typeof Input>, 'value' | 'onChange'>) {
  return (
    <Field
      id={id}
      label="Mobile number"
      hint="11 digits, starting with 01."
      value={value}
      onChange={(e) => onChange(msisdnDigits(e.target.value))}
      inputMode="numeric"
      autoComplete="tel-national"
      placeholder="01XXXXXXXXX"
      pattern={MSISDN_PATTERN}
      required
      {...rest}
    />
  );
}
