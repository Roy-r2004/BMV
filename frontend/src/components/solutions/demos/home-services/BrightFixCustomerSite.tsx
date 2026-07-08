import { useCallback, useEffect, useRef, useState } from 'react';
import {
  COMPANY,
  JOB_TYPES,
  SERVICE_ZONES,
  URGENCY_OPTIONS,
  type QuoteSubmission,
  type Urgency,
} from './brightfixData.ts';
import BrightFixCustomerChat from './BrightFixCustomerChat.tsx';
import { BrightFixLogo, IconArrowRight } from '../shared/ShowcaseChatIcons.tsx';
import { onBrightfixImageError } from './brightfixImageFallback.ts';

const STEPS = ['Job type', 'Photos', 'Urgency & zone'];

const TICKER = [
  'Mike R. · 8 min out · Oak Hill burst pipe',
  'Sara L. · on-site · Congress Ave drain',
  'Central zone · 2 techs free · 12 min ETA',
  'Review bot · Linda W. opened Google link',
];

interface Props {
  onQuoteSubmit: (quote: QuoteSubmission) => void;
}

function estimateQuote(
  jobTypeId: string | null,
  urgency: Urgency | null,
  photos: number,
): { range: string; confidence: number; note: string } | null {
  if (!jobTypeId) return null;
  const job = JOB_TYPES.find((j) => j.id === jobTypeId);
  if (!job) return null;
  let confidence = 62;
  if (photos > 0) confidence += Math.min(photos * 8, 24);
  if (urgency === 'emergency') confidence += 6;
  if (urgency === 'today') confidence += 3;
  confidence = Math.min(confidence, 96);
  const note =
    photos === 0
      ? 'Add photos to tighten the range'
      : urgency === 'emergency'
        ? 'Emergency surcharge likely · parts held for nearest tech'
        : 'Quote AI refining from job type + photos';
  return { range: job.avgPrice, confidence, note };
}

export default function BrightFixCustomerSite({ onQuoteSubmit }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [jobTypeId, setJobTypeId] = useState<string | null>(null);
  const [urgency, setUrgency] = useState<Urgency | null>(null);
  const [zoneId, setZoneId] = useState<string | null>(null);
  const [photos, setPhotos] = useState(0);
  const [description, setDescription] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [tickerIdx, setTickerIdx] = useState(0);
  const [aiPulse, setAiPulse] = useState(false);

  useEffect(() => {
    const id = window.setInterval(() => setTickerIdx((i) => (i + 1) % TICKER.length), 3200);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!jobTypeId && photos === 0 && !urgency) return;
    setAiPulse(true);
    const t = window.setTimeout(() => setAiPulse(false), 700);
    return () => window.clearTimeout(t);
  }, [jobTypeId, photos, urgency, zoneId]);

  const resetWizard = useCallback(() => {
    setStep(0);
    setJobTypeId(null);
    setUrgency(null);
    setZoneId(null);
    setPhotos(0);
    setDescription('');
    setConfirmed(false);
  }, []);

  const openWizard = useCallback(() => {
    resetWizard();
    setWizardOpen(true);
    scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [resetWizard]);

  const openEmergency = useCallback(() => {
    resetWizard();
    setUrgency('emergency');
    setJobTypeId('leak');
    setWizardOpen(true);
    setStep(2);
    scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [resetWizard]);

  const addPhoto = () => setPhotos((p) => Math.min(p + 1, 5));

  const submitQuote = () => {
    if (!jobTypeId || !urgency || !zoneId) return;
    const quote: QuoteSubmission = { jobTypeId, urgency, zoneId, photos, description };
    setConfirmed(true);
    onQuoteSubmit(quote);
    window.setTimeout(() => {
      setWizardOpen(false);
      resetWizard();
    }, 2200);
  };

  const selectedJob = JOB_TYPES.find((j) => j.id === jobTypeId);
  const selectedZone = SERVICE_ZONES.find((z) => z.id === zoneId);
  const liveQuote = estimateQuote(jobTypeId, urgency, photos);

  return (
    <div className="bf-site">
      <div className="bf-site__scroll" ref={scrollRef}>
        <div className={`bf-site__emergency ${urgency === 'emergency' && wizardOpen ? 'bf-site__emergency--armed' : ''}`} role="status">
          <span className="bf-site__emergency-pulse" aria-hidden />
          <div className="bf-site__emergency-copy">
            <strong>24/7 emergency line</strong>
            <span>Active flood or burst? Call now — or start emergency quote.</span>
          </div>
          <div className="bf-site__emergency-actions">
            <a href={`tel:${COMPANY.emergencyPhone}`} className="bf-site__emergency-cta">
              {COMPANY.emergencyPhone}
            </a>
            <button type="button" className="bf-site__emergency-quote" onClick={openEmergency}>
              Emergency quote
            </button>
          </div>
        </div>

        <header className="bf-site__nav">
          <div className="bf-site__brand">
            <BrightFixLogo className="bf-site__logo" />
            <div>
              <strong>{COMPANY.name}</strong>
              <span>Licensed TX · Same-day Austin</span>
            </div>
          </div>
          <nav className="bf-site__nav-links" aria-label="Site">
            <button type="button" onClick={openWizard}>Get quote</button>
            <button type="button" onClick={() => setChatOpen(true)}>Quote AI</button>
            <a href={`tel:${COMPANY.phone}`}>{COMPANY.phone}</a>
          </nav>
          <button type="button" className="bf-site__nav-cta" onClick={openWizard}>
            Start quote
          </button>
        </header>

        <section className="bf-site__hero">
          <div className="bf-site__hero-bg" aria-hidden>
            <img src={COMPANY.heroImage} alt="" onError={(e) => onBrightfixImageError(e)} />
            <div className="bf-site__hero-shade" />
          </div>
          <div className="bf-site__hero-copy">
            <p className="bf-site__brand-mark">{COMPANY.name}</p>
            <h1>Plumber booked. Not put on hold.</h1>
            <p className="bf-site__hero-sub">
              Describe the job, drop photos, pick urgency — Quote AI prices it and routes the nearest licensed tech.
            </p>
            <div className="bf-site__hero-actions">
              <button type="button" className="bf-site__btn bf-site__btn--primary" onClick={openWizard}>
                Get a quote
                <IconArrowRight className="bf-site__icon" />
              </button>
              <button type="button" className="bf-site__btn bf-site__btn--ghost" onClick={openEmergency}>
                Emergency dispatch
              </button>
            </div>
          </div>
          <div className="bf-site__ticker" aria-live="polite">
            <span className="bf-site__ticker-live">Live</span>
            <span key={tickerIdx} className="bf-site__ticker-text">{TICKER[tickerIdx]}</span>
          </div>
        </section>

        {wizardOpen && (
          <section className="bf-site__wizard" aria-label="Quote wizard">
            <header className="bf-site__wizard-head">
              <div>
                <h2>Quote wizard</h2>
                <p>
                  Step {step + 1} of {STEPS.length} — {STEPS[step]}
                </p>
              </div>
              <button type="button" className="bf-site__wizard-close" onClick={() => setWizardOpen(false)} aria-label="Close wizard">
                ×
              </button>
            </header>

            <div className="bf-site__wizard-progress" role="progressbar" aria-valuenow={step + 1} aria-valuemin={1} aria-valuemax={3}>
              {STEPS.map((s, i) => (
                <div key={s} className={`bf-site__wizard-progress-seg ${i <= step ? 'bf-site__wizard-progress-seg--on' : ''}`}>
                  <span>{i + 1}</span>
                  <em>{s}</em>
                </div>
              ))}
            </div>

            {confirmed ? (
              <div className="bf-site__wizard-done">
                <span className="bf-site__wizard-done-icon" aria-hidden>✓</span>
                <strong>Quote sent to dispatch</strong>
                <p>Quote AI scored your job — opening the job inbox for routing.</p>
              </div>
            ) : (
              <>
                {step === 0 && (
                  <div className="bf-site__wizard-pane">
                    <p className="bf-site__wizard-hint">What needs fixing?</p>
                    <div className="bf-site__job-grid">
                      {JOB_TYPES.map((job) => (
                        <button
                          key={job.id}
                          type="button"
                          className={jobTypeId === job.id ? 'bf-site__job-card bf-site__job-card--on' : 'bf-site__job-card'}
                          onClick={() => setJobTypeId(job.id)}
                        >
                          <span className="bf-site__job-icon" aria-hidden>
                            {job.icon}
                          </span>
                          <strong>{job.label}</strong>
                          <span>{job.desc}</span>
                          <em>{job.avgPrice}</em>
                        </button>
                      ))}
                    </div>
                    <textarea
                      className="bf-site__wizard-text"
                      placeholder="Describe the issue (optional)…"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={2}
                    />
                  </div>
                )}

                {step === 1 && (
                  <div className="bf-site__wizard-pane">
                    <p className="bf-site__wizard-hint">Photos help Quote AI price parts and labor</p>
                    <div className="bf-site__photo-zone">
                      <button type="button" className="bf-site__photo-add" onClick={addPhoto}>
                        <span>+</span>
                        <span>{photos === 0 ? 'Add photos' : `${photos} photo${photos > 1 ? 's' : ''} added`}</span>
                      </button>
                      {photos > 0 && (
                        <div className="bf-site__photo-thumbs">
                          {Array.from({ length: photos }).map((_, i) => (
                            <div key={i} className="bf-site__photo-thumb" aria-hidden>
                              <span>{i + 1}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    <p className="bf-site__wizard-note">Shutoff, model plate, and damage close-ups work best.</p>
                  </div>
                )}

                {step === 2 && (
                  <div className="bf-site__wizard-pane">
                    <p className="bf-site__wizard-hint">Urgency</p>
                    <div className="bf-site__urgency-row">
                      {URGENCY_OPTIONS.map((opt) => (
                        <button
                          key={opt.id}
                          type="button"
                          className={
                            urgency === opt.id
                              ? `bf-site__urgency bf-site__urgency--on bf-site__urgency--${opt.id}`
                              : `bf-site__urgency bf-site__urgency--${opt.id}`
                          }
                          onClick={() => setUrgency(opt.id)}
                        >
                          {opt.badge && <span className="bf-site__urgency-badge">{opt.badge}</span>}
                          <strong>{opt.label}</strong>
                          <span>{opt.desc}</span>
                        </button>
                      ))}
                    </div>
                    <p className="bf-site__wizard-hint bf-site__wizard-hint--zone">Service zone</p>
                    <div className="bf-site__zone-map">
                      {SERVICE_ZONES.map((zone) => (
                        <button
                          key={zone.id}
                          type="button"
                          className={
                            zoneId === zone.id
                              ? `bf-site__zone bf-site__zone--on bf-site__zone--${zone.id}`
                              : `bf-site__zone bf-site__zone--${zone.id}`
                          }
                          onClick={() => setZoneId(zone.id)}
                        >
                          <strong>{zone.label}</strong>
                          <span>ETA {zone.eta}</span>
                          <em>
                            {zone.techs} tech{zone.techs > 1 ? 's' : ''} free
                          </em>
                          {zone.urgent && <span className="bf-site__zone-hot">High demand</span>}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {liveQuote && (
                  <div className={`bf-site__ai-quote ${aiPulse ? 'bf-site__ai-quote--pulse' : ''}`}>
                    <div className="bf-site__ai-quote-top">
                      <span className="bf-site__ai-quote-label">Quote AI</span>
                      <strong>{liveQuote.range}</strong>
                    </div>
                    <div className="bf-site__ai-quote-bar">
                      <span style={{ width: `${liveQuote.confidence}%` }} />
                    </div>
                    <p>
                      {liveQuote.confidence}% confidence
                      {selectedJob ? ` · ${selectedJob.label}` : ''}
                      {urgency ? ` · ${urgency}` : ''}
                      {selectedZone ? ` · ${selectedZone.label}` : ''}
                    </p>
                    <em>{liveQuote.note}</em>
                  </div>
                )}

                <footer className="bf-site__wizard-foot">
                  {step > 0 && (
                    <button type="button" className="bf-site__btn bf-site__btn--ghost" onClick={() => setStep((s) => s - 1)}>
                      Back
                    </button>
                  )}
                  {step < 2 ? (
                    <button
                      type="button"
                      className="bf-site__btn bf-site__btn--primary"
                      disabled={step === 0 && !jobTypeId}
                      onClick={() => setStep((s) => s + 1)}
                    >
                      Continue
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="bf-site__btn bf-site__btn--primary"
                      disabled={!jobTypeId || !urgency || !zoneId}
                      onClick={submitQuote}
                    >
                      Submit to dispatch
                    </button>
                  )}
                </footer>
              </>
            )}
          </section>
        )}

        <section className="bf-site__proof">
          <div className="bf-site__proof-row">
            <div>
              <strong>TX #M-40291</strong>
              <span>Licensed & insured</span>
            </div>
            <div>
              <strong>4 min</strong>
              <span>Avg quote → dispatch</span>
            </div>
            <div>
              <strong>1,800+</strong>
              <span>Jobs completed</span>
            </div>
            <div>
              <strong>24/7</strong>
              <span>Emergency line</span>
            </div>
          </div>
        </section>

        <section className="bf-site__journey">
          <h2>Leak to truck — minutes, not hold music</h2>
          <p className="bf-site__journey-sub">One path from the customer phone to a tech on the map.</p>
          <ol className="bf-site__journey-list">
            {[
              { n: '01', title: 'Capture the job', desc: 'Wizard or SMS — AI qualifies type, photos, urgency.' },
              { n: '02', title: 'Score & route', desc: 'Nearest available tech by skill and zone ETA.' },
              { n: '03', title: 'Live status', desc: 'En route → on-site → done, texted automatically.' },
              { n: '04', title: 'Review ask', desc: 'Google review request only after a clean close.' },
            ].map((j) => (
              <li key={j.n}>
                <span>{j.n}</span>
                <strong>{j.title}</strong>
                <p>{j.desc}</p>
              </li>
            ))}
          </ol>
        </section>

        <footer className="bf-site__footer">
          <div>
            <strong>{COMPANY.name}</strong>
            <p>
              {COMPANY.address}, {COMPANY.city}
            </p>
          </div>
          <div>
            <p>{COMPANY.phone}</p>
            <p>{COMPANY.email}</p>
          </div>
        </footer>
      </div>

      <BrightFixCustomerChat onQuoteClick={openWizard} open={chatOpen} onOpenChange={setChatOpen} />
    </div>
  );
}
