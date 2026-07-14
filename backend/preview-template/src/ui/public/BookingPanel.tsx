import * as React from 'react';
import { format, parseISO } from 'date-fns';

import { Button } from '../core/Button';
import { toast } from '../core/Toast';
import { MotionReveal } from '../motion';
import { cn } from '../lib/cn';

export interface BookingTreatment {
  id: string;
  name: string;
  duration: string;
}

export interface BookingSlot {
  id: string;
  startsAt: string;
  label?: string;
}

export interface BookingPanelProps {
  heading: string;
  /** Optional when `children` supplies a custom booking form. */
  treatments?: BookingTreatment[];
  /** Structured slots — or omit when using `children`. */
  slots?: BookingSlot[] | React.ReactNode;
  description?: string;
  confirmLabel?: string;
  onConfirm?: (payload: { treatmentId: string; slotId: string }) => void;
  /** Custom booking UI (AI often invents a free-form form). */
  children?: React.ReactNode;
  className?: string;
}

type Step = 1 | 2 | 3;

function isSlotList(value: unknown): value is BookingSlot[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item) =>
        typeof item === 'object' &&
        item !== null &&
        !React.isValidElement(item) &&
        typeof (item as BookingSlot).id === 'string'
    )
  );
}

/** Three-step consult booking demo — also accepts a custom children form from codegen. */
export function BookingPanel({
  children,
  className,
  confirmLabel = 'Confirm consult',
  description,
  heading,
  onConfirm,
  slots,
  treatments = [],
}: BookingPanelProps) {
  const structuredSlots = isSlotList(slots) ? slots : [];
  const customSlots = !isSlotList(slots) && slots != null ? (slots as React.ReactNode) : null;
  const useCustom = Boolean(children || customSlots);

  const [step, setStep] = React.useState<Step>(1);
  const [treatmentId, setTreatmentId] = React.useState(treatments[0]?.id ?? '');
  const [slotId, setSlotId] = React.useState(structuredSlots[0]?.id ?? '');

  const treatment = treatments.find((t) => t.id === treatmentId);
  const slot = structuredSlots.find((s) => s.id === slotId);

  const slotLabel = React.useMemo(() => {
    if (!slot) return '';
    if (slot.label) return slot.label;
    try {
      return format(parseISO(slot.startsAt), "EEE d MMM · h:mm a");
    } catch {
      return slot.startsAt;
    }
  }, [slot]);

  const handleConfirm = () => {
    if (useCustom) {
      onConfirm?.({ treatmentId: treatmentId || 'custom', slotId: slotId || 'custom' });
      return;
    }
    if (!treatmentId || !slotId) return;
    onConfirm?.({ treatmentId, slotId });
    toast.success('Consult held', `${treatment?.name ?? 'Treatment'} · ${slotLabel}`);
    setStep(1);
  };

  return (
    <section id="book" className={cn('scroll-mt-28 px-6 py-28 lg:px-12 lg:py-32', className)}>
      <div className="mx-auto grid w-full max-w-[92rem] gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
        <MotionReveal>
          <p className="text-[11px] font-semibold tracking-[0.2em] text-brand uppercase">Book</p>
          <h2 className="mt-4 font-display text-[clamp(2.75rem,5vw,4.5rem)] italic leading-[0.92] tracking-[-0.04em] text-foreground">
            {heading}
          </h2>
          {description ? <p className="mt-5 max-w-md text-base leading-8 text-muted">{description}</p> : null}
          {!useCustom ? (
            <ol className="mt-10 flex gap-6 text-[11px] font-semibold tracking-[0.16em] uppercase">
              {([1, 2, 3] as const).map((n) => (
                <li key={n} className={cn(step === n ? 'text-foreground' : 'text-muted')}>
                  0{n}
                </li>
              ))}
            </ol>
          ) : null}
        </MotionReveal>

        <MotionReveal className="border border-border-subtle bg-card p-6 sm:p-8">
          {useCustom ? (
            <div className="space-y-6">
              {children}
              {customSlots}
              {onConfirm ? (
                <Button type="button" className="w-full sm:w-auto" onClick={handleConfirm}>
                  {confirmLabel}
                </Button>
              ) : null}
            </div>
          ) : null}

          {!useCustom && step === 1 ? (
            <div className="space-y-4">
              <h3 className="font-display text-2xl italic text-foreground">Choose treatment</h3>
              <div className="space-y-2">
                {treatments.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTreatmentId(t.id)}
                    className={cn(
                      'flex w-full items-center justify-between border px-4 py-4 text-left transition-colors',
                      treatmentId === t.id
                        ? 'border-foreground bg-foreground text-background'
                        : 'border-border-subtle bg-background text-foreground hover:border-foreground/40',
                    )}
                  >
                    <span className="text-sm font-medium">{t.name}</span>
                    <span className="font-mono text-[11px] opacity-70">{t.duration}</span>
                  </button>
                ))}
              </div>
              <Button type="button" className="mt-4 w-full sm:w-auto" onClick={() => setStep(2)} disabled={!treatmentId}>
                Continue
              </Button>
            </div>
          ) : null}

          {!useCustom && step === 2 ? (
            <div className="space-y-4">
              <h3 className="font-display text-2xl italic text-foreground">Pick a slot</h3>
              <div className="grid gap-2 sm:grid-cols-2">
                {structuredSlots.map((s) => {
                  let label = s.label;
                  if (!label) {
                    try {
                      label = format(parseISO(s.startsAt), "EEE d MMM · h:mm a");
                    } catch {
                      label = s.startsAt;
                    }
                  }
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setSlotId(s.id)}
                      className={cn(
                        'border px-4 py-4 text-left text-sm transition-colors',
                        slotId === s.id
                          ? 'border-foreground bg-foreground text-background'
                          : 'border-border-subtle bg-background text-foreground hover:border-foreground/40',
                      )}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              <div className="mt-4 flex flex-wrap gap-3">
                <Button type="button" variant="secondary" onClick={() => setStep(1)}>
                  Back
                </Button>
                <Button type="button" onClick={() => setStep(3)} disabled={!slotId}>
                  Continue
                </Button>
              </div>
            </div>
          ) : null}

          {!useCustom && step === 3 ? (
            <div className="space-y-6">
              <h3 className="font-display text-2xl italic text-foreground">Confirm</h3>
              <dl className="space-y-3 border border-border-subtle bg-background px-4 py-4 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">Treatment</dt>
                  <dd className="font-medium text-foreground">{treatment?.name}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">Duration</dt>
                  <dd className="font-mono text-foreground">{treatment?.duration}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted">Slot</dt>
                  <dd className="text-right font-medium text-foreground">{slotLabel}</dd>
                </div>
              </dl>
              <div className="flex flex-wrap gap-3">
                <Button type="button" variant="secondary" onClick={() => setStep(2)}>
                  Back
                </Button>
                <Button type="button" onClick={handleConfirm}>
                  {confirmLabel}
                </Button>
              </div>
            </div>
          ) : null}
        </MotionReveal>
      </div>
    </section>
  );
}
