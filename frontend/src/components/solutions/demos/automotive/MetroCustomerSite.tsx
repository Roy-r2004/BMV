import { useCallback, useRef, useState } from 'react';
import {
  BOOKING_SLOTS,
  COMPANY,
  SERVICES,
  STATUS_TIMELINE,
  bayLabelForPreference,
  type BookingSubmission,
} from './metroData.ts';
import MetroCustomerChat from './MetroCustomerChat.tsx';
import { IconArrowRight, MetroLogo } from '../shared/ShowcaseChatIcons.tsx';
import { onMetroImageError } from './metroImageFallback.ts';

const STEPS = ['Service', 'Vehicle', 'Slot'];

interface Props {
  onBookSubmit: (booking: BookingSubmission) => void;
}

export default function MetroCustomerSite({ onBookSubmit }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [serviceId, setServiceId] = useState<string | null>(null);
  const [vehicle, setVehicle] = useState('');
  const [mileage, setMileage] = useState('');
  const [slot, setSlot] = useState<string | null>(null);
  const [notes, setNotes] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const resetWizard = useCallback(() => {
    setStep(0);
    setServiceId(null);
    setVehicle('');
    setMileage('');
    setSlot(null);
    setNotes('');
    setConfirmed(false);
  }, []);

  const openWizard = useCallback(() => {
    resetWizard();
    setWizardOpen(true);
    window.setTimeout(() => {
      scrollRef.current?.querySelector('.mt-site__book')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 40);
  }, [resetWizard]);

  const focusStatus = useCallback(() => {
    scrollRef.current?.querySelector('.mt-site__status')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const submitBook = () => {
    if (!serviceId || !vehicle.trim() || !slot) return;
    const booking: BookingSubmission = { serviceId, vehicle: vehicle.trim(), slot, notes };
    setConfirmed(true);
    onBookSubmit(booking);
    window.setTimeout(() => {
      setWizardOpen(false);
      resetWizard();
    }, 2200);
  };

  const selected = SERVICES.find((s) => s.id === serviceId);
  const canNext =
    (step === 0 && !!serviceId) ||
    (step === 1 && vehicle.trim().length >= 4) ||
    (step === 2 && !!slot);

  return (
    <div className="mt-site">
      <div className="mt-site__scroll" ref={scrollRef}>
        <header className="mt-site__nav">
          <div className="mt-site__brand">
            <MetroLogo className="mt-site__logo" />
            <div>
              <strong>METRO</strong>
              <span>Auto Care · Denver</span>
            </div>
          </div>
          <nav className="mt-site__nav-links" aria-label="Site">
            <button type="button" onClick={openWizard}>Book service</button>
            <button type="button" onClick={focusStatus}>Track my car</button>
            <a href={`tel:${COMPANY.phone}`}>{COMPANY.phone}</a>
          </nav>
          <button type="button" className="mt-site__nav-cta" onClick={openWizard}>
            Book service
          </button>
        </header>

        <section className="mt-site__hero" aria-label="Metro Auto Care">
          <div className="mt-site__hero-bg" aria-hidden>
            <img src={COMPANY.heroImage} alt="" onError={(e) => onMetroImageError(e)} />
            <div className="mt-site__hero-shade" />
            <div className="mt-site__hero-grain" />
          </div>
          <div className="mt-site__hero-copy">
            <p className="mt-site__brand-mark">METRO</p>
            <h1>Bay ready. Progress on your phone.</h1>
            <p className="mt-site__hero-sub">
              Book the lift online — Bay AI assigns the right rack and Status Bot texts every stage.
            </p>
            <div className="mt-site__hero-actions">
              <button type="button" className="mt-site__btn mt-site__btn--primary" onClick={openWizard}>
                Book service
                <IconArrowRight className="mt-site__icon" />
              </button>
              <button type="button" className="mt-site__btn mt-site__btn--ghost" onClick={focusStatus}>
                Track my car
              </button>
            </div>
          </div>
        </section>

        {wizardOpen && (
          <section className="mt-site__book" aria-label="Book service">
            <header className="mt-site__book-head">
              <div>
                <h2>Book a bay</h2>
                <p>Service → vehicle → slot. Bay AI places the job on the right lift.</p>
              </div>
              <button
                type="button"
                className="mt-site__book-close"
                onClick={() => {
                  setWizardOpen(false);
                  resetWizard();
                }}
                aria-label="Close booking"
              >
                ×
              </button>
            </header>

            <div className="mt-site__wizard-progress" role="progressbar" aria-valuenow={step + 1} aria-valuemin={1} aria-valuemax={3}>
              {STEPS.map((label, i) => (
                <div key={label} className={`mt-site__wizard-seg ${i <= step ? 'mt-site__wizard-seg--on' : ''}`}>
                  <span>{i + 1}</span>
                  <em>{label}</em>
                </div>
              ))}
            </div>

            {confirmed ? (
              <div className="mt-site__wizard-done" role="status">
                <span className="mt-site__wizard-done-mark" aria-hidden>✓</span>
                <strong>Sent to bay scheduler</strong>
                <p>
                  {selected?.label} for {vehicle} · {slot}. Opening service inbox…
                </p>
              </div>
            ) : (
              <>
                {step === 0 && (
                  <div className="mt-site__wizard-pane">
                    <p className="mt-site__wizard-hint">What do you need?</p>
                    <div className="mt-site__svc-grid" role="listbox" aria-label="Services">
                      {SERVICES.map((svc) => (
                        <button
                          key={svc.id}
                          type="button"
                          role="option"
                          aria-selected={serviceId === svc.id}
                          className={serviceId === svc.id ? 'mt-site__svc-tile mt-site__svc-tile--on' : 'mt-site__svc-tile'}
                          onClick={() => setServiceId(svc.id)}
                        >
                          <div className="mt-site__svc-tile-media" aria-hidden>
                            <img src={svc.imageUrl} alt="" onError={(e) => onMetroImageError(e, svc.glyph)} />
                            <span className="mt-site__svc-glyph">{svc.glyph}</span>
                          </div>
                          <div className="mt-site__svc-tile-body">
                            <strong>{svc.label}</strong>
                            <span>{svc.desc}</span>
                            <em>
                              {svc.price} · {svc.duration}
                            </em>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {step === 1 && (
                  <div className="mt-site__wizard-pane">
                    <p className="mt-site__wizard-hint">Vehicle details</p>
                    <div className="mt-site__wizard-form">
                      <label>
                        <span>Year · make · model</span>
                        <input
                          value={vehicle}
                          onChange={(e) => setVehicle(e.target.value)}
                          placeholder="2021 Honda CR-V"
                          autoComplete="off"
                        />
                      </label>
                      <label>
                        <span>Mileage (optional)</span>
                        <input
                          value={mileage}
                          onChange={(e) => setMileage(e.target.value)}
                          placeholder="48,210"
                          inputMode="numeric"
                        />
                      </label>
                      <label>
                        <span>Notes (optional)</span>
                        <textarea
                          rows={2}
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          placeholder="Check-engine light? Noise when braking?"
                        />
                      </label>
                    </div>
                    {selected && (
                      <p className="mt-site__wizard-note">
                        Preferred lift: {bayLabelForPreference(selected.bayPreference)}
                      </p>
                    )}
                  </div>
                )}

                {step === 2 && (
                  <div className="mt-site__wizard-pane">
                    <p className="mt-site__wizard-hint">Pick a drop-off slot</p>
                    <div className="mt-site__slot-grid" role="listbox" aria-label="Available slots">
                      {BOOKING_SLOTS.map((s) => (
                        <button
                          key={s}
                          type="button"
                          role="option"
                          aria-selected={slot === s}
                          className={slot === s ? 'mt-site__slot mt-site__slot--on' : 'mt-site__slot'}
                          onClick={() => setSlot(s)}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                    {selected && slot && (
                      <div className="mt-site__book-preview">
                        <strong>
                          {selected.label} · {selected.price}
                        </strong>
                        <span>
                          {vehicle} · {slot} · {bayLabelForPreference(selected.bayPreference)}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                <footer className="mt-site__wizard-foot">
                  {step > 0 ? (
                    <button type="button" className="mt-site__btn mt-site__btn--ghost-dark" onClick={() => setStep((s) => s - 1)}>
                      Back
                    </button>
                  ) : (
                    <span />
                  )}
                  {step < 2 ? (
                    <button
                      type="button"
                      className="mt-site__btn mt-site__btn--primary"
                      disabled={!canNext}
                      onClick={() => setStep((s) => s + 1)}
                    >
                      Continue
                      <IconArrowRight className="mt-site__icon" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="mt-site__btn mt-site__btn--primary"
                      disabled={!canNext}
                      onClick={submitBook}
                    >
                      Confirm booking
                    </button>
                  )}
                </footer>
              </>
            )}
          </section>
        )}

        <section className="mt-site__status" aria-label="Live repair status">
          <div className="mt-site__status-media" aria-hidden>
            <img src={COMPANY.statusImage} alt="" onError={(e) => onMetroImageError(e)} />
            <div className="mt-site__status-media-shade" />
          </div>
          <div className="mt-site__status-body">
            <p className="mt-site__eyebrow">Live status</p>
            <h2>Your car on the floor</h2>
            <p className="mt-site__status-lead">
              Status Bot texts every stage — checked in, on lift, quality check, ready. No front-desk call loop.
            </p>
            <ol className="mt-site__timeline">
              {STATUS_TIMELINE.map((item) => (
                <li key={item.stage} className={item.done ? 'mt-site__timeline-item mt-site__timeline-item--done' : 'mt-site__timeline-item'}>
                  <i aria-hidden />
                  <div>
                    <strong>{item.stage}</strong>
                    <span>{item.time}</span>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-site__status-demo">
              Demo vehicle: Priya Nair · Bay 1 · rotating tires · ETA 18 min
            </p>
            <button type="button" className="mt-site__btn mt-site__btn--outline" onClick={() => setChatOpen(true)}>
              Ask Service Bot
            </button>
          </div>
        </section>

        <section className="mt-site__bay-ai" aria-label="Bay AI">
          <div className="mt-site__bay-ai-inner">
            <p className="mt-site__eyebrow">Bay AI</p>
            <h2>Right lift. First try.</h2>
            <p>
              Oil jobs hit the quick rack. Alignments get the alignment bay. Diagnostics sit on the scanner station.
              Techs see upsell alerts — you approve before anything gets added.
            </p>
            <ul className="mt-site__bay-ai-list">
              <li>
                <strong>Bay scheduler</strong>
                <span>Matches job type to open lifts</span>
              </li>
              <li>
                <strong>Status Bot</strong>
                <span>SMS at every shop-floor stage</span>
              </li>
              <li>
                <strong>Upsell alerts</strong>
                <span>Staff-only until you approve</span>
              </li>
            </ul>
          </div>
        </section>

        <footer className="mt-site__footer">
          <div className="mt-site__footer-grid">
            <div>
              <p className="mt-site__footer-brand">METRO</p>
              <p className="mt-site__footer-muted">{COMPANY.name}</p>
              <p className="mt-site__footer-muted">
                {COMPANY.address}, {COMPANY.city}
              </p>
              <p className="mt-site__footer-muted">{COMPANY.phone}</p>
              <p className="mt-site__footer-muted">{COMPANY.email}</p>
            </div>
            <div>
              <p className="mt-site__footer-heading">Hours</p>
              {COMPANY.hours.map((h) => (
                <p key={h.days} className="mt-site__footer-hours">
                  <span>{h.days}</span>
                  <span>{h.time}</span>
                </p>
              ))}
            </div>
            <div>
              <p className="mt-site__footer-heading">Service</p>
              <button type="button" className="mt-site__footer-link" onClick={openWizard}>
                Book a bay
              </button>
              <button type="button" className="mt-site__footer-link" onClick={focusStatus}>
                Track progress
              </button>
              <button type="button" className="mt-site__footer-link" onClick={() => setChatOpen(true)}>
                Service Bot
              </button>
            </div>
          </div>
        </footer>
      </div>

      <MetroCustomerChat onBookClick={openWizard} open={chatOpen} onOpenChange={setChatOpen} />
    </div>
  );
}
