import * as React from 'react';

import { AnimeReveal } from '../motion';
import { Button } from '../core/Button';
import { Input } from '../core/Input';
import { cn } from '../lib/cn';

export type InquiryPayload = {
  /** The catalogue item being asked about, when the panel sits on a detail page. */
  itemId?: string;
  itemTitle?: string;
  name: string;
  email: string;
  phone?: string;
  message: string;
};

export type InquiryPanelProps = {
  heading?: string;
  description?: string;
  itemId?: string;
  itemTitle?: string;
  /** Prefills the message so the visitor is never staring at an empty box. */
  messagePlaceholder?: string;
  ctaLabel?: string;
  /** Shown after a successful submit. */
  confirmationHeading?: string;
  confirmationBody?: string;
  requirePhone?: boolean;
  /**
   * The real-backend seam.
   *
   * Left undefined, the panel confirms locally — enough for a preview to
   * demonstrate the whole browse → detail → inquire path with no server. Pass a
   * handler (a POST to the inquiries endpoint) and the same UI becomes live:
   * resolve to confirm, throw to surface the error state.
   */
  onSubmit?: (payload: InquiryPayload) => void | Promise<void>;
  className?: string;
};

type Stage = 'idle' | 'submitting' | 'confirmed' | 'error';

/**
 * Terminal step of the public happy path — ask about a specific item.
 *
 * Deliberately self-contained: it owns its own success state rather than
 * navigating to a confirmation route, so the journey completes even when no
 * such route exists.
 */
export function InquiryPanel({
  className,
  confirmationBody = 'Thanks — your message is on its way. We usually reply within one business day.',
  confirmationHeading = 'Inquiry sent',
  ctaLabel = 'Send inquiry',
  description,
  heading = 'Inquire about this piece',
  itemId,
  itemTitle,
  messagePlaceholder = 'Tell us what you would like to know — availability, dimensions, shipping.',
  onSubmit,
  requirePhone = false,
}: InquiryPanelProps) {
  const [stage, setStage] = React.useState<Stage>('idle');
  const [name, setName] = React.useState('');
  const [email, setEmail] = React.useState('');
  const [phone, setPhone] = React.useState('');
  const [message, setMessage] = React.useState('');
  const [error, setError] = React.useState('');

  const resolvedDescription =
    description ??
    (itemTitle
      ? `Send a note about ${itemTitle} and we will come back to you directly.`
      : 'Send a note and we will come back to you directly.');

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (stage === 'submitting') return;
    if (!name.trim() || !email.trim() || !message.trim()) {
      setError('Name, email and a short message are needed.');
      return;
    }
    if (requirePhone && !phone.trim()) {
      setError('A phone number is needed for this request.');
      return;
    }
    setError('');
    setStage('submitting');
    try {
      await onSubmit?.({
        itemId,
        itemTitle,
        name: name.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
        message: message.trim(),
      });
      setStage('confirmed');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That did not go through. Please try again.');
      setStage('error');
    }
  }

  return (
    <section
      id="inquire"
      data-inquiry-panel=""
      className={cn(
        // scroll-margin clears sticky/fixed public nav when Contact for Purchase
        // or /contact#inquire lands here via ScrollToTop.
        'relative isolate scroll-mt-[calc(var(--public-header-h,7rem)+1.5rem)] px-6 py-20 sm:px-10 lg:px-12 lg:py-28',
        className
      )}
    >
      <div className="mx-auto grid max-w-[92rem] gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
        <AnimeReveal>
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-brand">Enquiries</p>
          <h2 className="mt-4 font-display text-[clamp(2rem,4vw,3.2rem)] leading-[1.02] tracking-[-0.03em] text-foreground">
            {heading}
          </h2>
          <p className="mt-4 max-w-lg text-base leading-7 text-muted">{resolvedDescription}</p>
          {itemTitle ? (
            <p className="mt-6 border-t border-border-subtle pt-6 font-mono text-xs uppercase tracking-[0.16em] text-muted">
              Regarding · {itemTitle}
            </p>
          ) : null}
        </AnimeReveal>

        <div className="min-w-0">
          {stage === 'confirmed' ? (
            <div
              data-inquiry-confirmed=""
              role="status"
              aria-live="polite"
              className="rounded-[var(--radius-ui)] border border-brand/30 bg-brand/5 p-8"
            >
              <h3 className="font-display text-2xl tracking-tight text-foreground">
                {confirmationHeading}
              </h3>
              <p className="mt-3 text-sm leading-6 text-muted">{confirmationBody}</p>
              <Button
                variant="outline"
                className="mt-6"
                onClick={() => {
                  setStage('idle');
                  setMessage('');
                }}
              >
                Send another
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate className="grid gap-5">
              <div className="grid gap-5 sm:grid-cols-2">
                <Input
                  label="Name"
                  name="name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <Input
                  label="Email"
                  name="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <Input
                label={requirePhone ? 'Phone' : 'Phone (optional)'}
                name="phone"
                type="tel"
                required={requirePhone}
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
              <Input
                as="textarea"
                rows={5}
                label="Message"
                name="message"
                required
                placeholder={messagePlaceholder}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
              {error ? (
                <p role="alert" className="text-sm text-[color:var(--color-destructive,#b42318)]">
                  {error}
                </p>
              ) : null}
              <div className="flex items-center gap-4">
                <Button type="submit" disabled={stage === 'submitting'}>
                  {stage === 'submitting' ? 'Sending…' : ctaLabel}
                </Button>
                <p className="text-xs text-muted">We never share your details.</p>
              </div>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
