/**
 * The front door: one question.
 *
 * Not "what's wrong with your business" — that shuts out everyone who has not
 * started one yet. A problem that costs them, a decision they're stuck on, or
 * something they want to start: whatever they write is the thing we test,
 * so the question has to let all three in.
 */
import { Link as RouterLink } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';

export default function FrontDoor({
  firstName,
  value,
  onChange,
  siteUrl,
  onSiteUrl,
  error,
  onStart,
  signedIn,
  checkingAuth,
}: {
  firstName: string | null;
  value: string;
  onChange: (v: string) => void;
  siteUrl: string;
  onSiteUrl: (v: string) => void;
  error?: string;
  onStart: () => void;
  signedIn: boolean;
  checkingAuth: boolean;
}) {
  const reduce = useReducedMotion();
  const enter = (d: number) =>
    reduce ? {} : { initial: { opacity: 0, y: 16 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.55, delay: d } };

  return (
    <section className="relative pt-[6vh]">
      <div className="cx-dotfield" aria-hidden="true" />
      <div className="relative max-w-[1180px]">
        <motion.p className="cx-faint text-[17px]" {...enter(0)}>
          {firstName ? `Hi ${firstName}.` : 'A consultation, not a sales call.'}
        </motion.p>
        <motion.h1 className="cx-h1 mt-5 max-w-[14ch]" {...enter(0.05)}>
          What are you trying to work out?
        </motion.h1>
        <motion.p className="cx-lead mt-7 max-w-[48ch]" {...enter(0.12)}>
          A problem that's costing you, a decision you're stuck on, or something you want to
          start. Say it the way you'd say it across a table.
        </motion.p>

        {!signedIn && !checkingAuth ? (
          <motion.div className="cx-card mt-10 max-w-[760px] p-8" {...enter(0.2)}>
            <h2 className="cx-h3">Sign in to start</h2>
            <p className="cx-muted mt-2">
              Every consultation is private to your account: only you can open what it produces.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <RouterLink to="/signup" state={{ from: '/demo' }} className="cx-btn cx-btn--blue">
                Create your account
              </RouterLink>
              <RouterLink to="/login" state={{ from: '/demo' }} className="cx-btn cx-btn--ghost">
                Sign in
              </RouterLink>
            </div>
          </motion.div>
        ) : (
          <motion.form
            className="mt-10 max-w-[1000px]"
            onSubmit={(e) => {
              e.preventDefault();
              onStart();
            }}
            noValidate
            {...enter(0.2)}
          >
            <label htmlFor="cx-problem" className="sr-only">What are you trying to work out?</label>
            <textarea
              id="cx-problem"
              className="cx-field"
              rows={4}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) onStart();
              }}
              placeholder={'e.g. "We keep missing calls in the evening and I think we\'re losing bookings."\nor "I want to open a second clinic but I can\'t tell if the numbers work."'}
              autoFocus
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'cx-problem-error' : undefined}
            />
            {error ? (
              <p id="cx-problem-error" className="cx-error mt-3" role="alert">{error}</p>
            ) : null}

            <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2">
              <label htmlFor="cx-site" className="cx-muted">Your website, if you have one</label>
              <input
                id="cx-site"
                className="cx-input w-[280px] max-w-full"
                value={siteUrl}
                onChange={(e) => onSiteUrl(e.target.value)}
                placeholder="e.g. yourbusiness.com"
                autoComplete="url"
              />
              <span className="cx-faint">We read it before we ask you anything.</span>
            </div>

            <div className="mt-10 flex flex-wrap items-center gap-6">
              <button type="submit" className="cx-btn cx-btn--blue">Start the conversation</button>
              <span className="cx-muted">About 15 minutes to an honest answer.</span>
            </div>
          </motion.form>
        )}

        <motion.div
          className="mt-[9vh] flex flex-wrap gap-x-14 gap-y-3 text-[15.5px] cx-muted"
          {...enter(0.3)}
        >
          <p><b className="text-[var(--cx-txt)]">Nothing is built</b> until you've read our answer.</p>
          <p><b className="text-[var(--cx-txt)]">Every number</b> will be yours, never invented.</p>
          <p><b className="text-[var(--cx-txt)]">Your own idea</b> gets tested like any other.</p>
        </motion.div>
      </div>
    </section>
  );
}
