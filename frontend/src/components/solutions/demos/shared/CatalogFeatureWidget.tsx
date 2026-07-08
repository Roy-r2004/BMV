import { useMemo, useState, type ReactNode } from 'react';
import type { AIFeatureCatalogItem } from '../../../../data/aiFeatureCatalog';

interface Props {
  feature: AIFeatureCatalogItem;
}

function featureWidgetClass(feature: AIFeatureCatalogItem): string {
  return `${feature.id}-widget overlay-feature-widget--${feature.id} overlay-feature-widget--${feature.category}`;
}

function FeatureShell({
  feature,
  children,
}: Props & {
  children: ReactNode;
}) {
  return (
    <section
      className={`overlay-feature-widget ${featureWidgetClass(feature)}`}
      data-overlay-target={`section-catalog-feature-${feature.id}`}
      aria-label={`${feature.title} tool`}
    >
      <div className="overlay-feature-widget__head">
        <span className="overlay-feature-widget__badge">Live AI tool</span>
        <h2>{feature.title}</h2>
        <p>{feature.description}</p>
      </div>
      {children}
    </section>
  );
}

function SizeFinder({ feature }: Props) {
  const [height, setHeight] = useState('170-180');
  const [fit, setFit] = useState('regular');
  const [category, setCategory] = useState('chair');
  const recommendation = useMemo(() => {
    const size = height === 'under-170' ? 'Compact' : height === 'over-180' ? 'Tall' : 'Standard';
    const cushion = fit === 'relaxed' ? 'deep seat' : fit === 'snug' ? 'structured fit' : 'balanced fit';
    return `${size} ${category} · ${cushion}`;
  }, [height, fit, category]);

  return (
    <FeatureShell feature={feature}>
      <div className={`overlay-feature-widget__form overlay-feature-widget__form--three ${feature.id}-widget`}>
        <label>
          Height
          <select value={height} onChange={(e) => setHeight(e.target.value)}>
            <option value="under-170">Under 170 cm</option>
            <option value="170-180">170-180 cm</option>
            <option value="over-180">Over 180 cm</option>
          </select>
        </label>
        <label>
          Fit preference
          <select value={fit} onChange={(e) => setFit(e.target.value)}>
            <option value="snug">Snug</option>
            <option value="regular">Regular</option>
            <option value="relaxed">Relaxed</option>
          </select>
        </label>
        <label>
          Product
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="chair">Chair</option>
            <option value="sofa">Sofa</option>
            <option value="desk">Desk</option>
          </select>
        </label>
      </div>
      <div className={`overlay-feature-widget__result ${feature.id}-widget`}>
        <strong>Recommended fit</strong>
        <span>{recommendation}</span>
        <em>Confidence 94% · fewer returns expected</em>
      </div>
    </FeatureShell>
  );
}

function OrderAssistant({ feature }: Props) {
  const [orderId, setOrderId] = useState('LUM-1046');
  const [lookedUp, setLookedUp] = useState(true);

  return (
    <FeatureShell feature={feature}>
      <div className={`overlay-feature-widget__inline ${feature.id}-widget`}>
        <input value={orderId} onChange={(e) => setOrderId(e.target.value)} aria-label="Order number" />
        <button type="button" onClick={() => setLookedUp(true)}>
          Track order
        </button>
      </div>
      {lookedUp && (
        <ol className="overlay-feature-widget__timeline">
          <li className="overlay-feature-widget__timeline-done">Order found · {orderId}</li>
          <li className="overlay-feature-widget__timeline-done">Packed by fulfillment</li>
          <li>Out for delivery · ETA today 4:20 PM</li>
          <li>Return window ready if needed</li>
        </ol>
      )}
    </FeatureShell>
  );
}

function SmartBundles({ feature }: Props) {
  const [style, setStyle] = useState('warm minimal');
  const [budget, setBudget] = useState('$250');
  const [added, setAdded] = useState(false);

  return (
    <FeatureShell feature={feature}>
      <div className={`overlay-feature-widget__form ${feature.id}-widget`}>
        <label>
          Room style
          <select value={style} onChange={(e) => setStyle(e.target.value)}>
            <option>warm minimal</option>
            <option>coastal calm</option>
            <option>modern contrast</option>
          </select>
        </label>
        <label>
          Budget
          <select value={budget} onChange={(e) => setBudget(e.target.value)}>
            <option>$150</option>
            <option>$250</option>
            <option>$500</option>
          </select>
        </label>
      </div>
      <div className={`overlay-feature-widget__cards ${feature.id}-widget`}>
        <article>
          <strong>{style} edit</strong>
          <span>lamp + throw + tray</span>
          <em>{budget} target · 12% bundle save</em>
        </article>
        <article>
          <strong>AI upsell</strong>
          <span>adds matching cushion only if cart margin stays healthy</span>
        </article>
      </div>
      <button type="button" className="overlay-feature-widget__primary" onClick={() => setAdded(true)}>
        {added ? 'Bundle added to cart' : 'Add recommended bundle'}
      </button>
    </FeatureShell>
  );
}

function SearchTool({ feature }: Props) {
  const [query, setQuery] = useState('walnut lamp for small bedroom');
  const results = ['Mira walnut lamp', 'Linen shade bundle', 'Soft brass tray'];

  return (
    <FeatureShell feature={feature}>
      <div className={`overlay-feature-widget__inline ${feature.id}-widget`}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search query" />
        <button type="button">Search</button>
      </div>
      <div className={`overlay-feature-widget__cards ${feature.id}-widget`}>
        {results.map((result) => (
          <article key={result}>
            <strong>{result}</strong>
            <span>Matched to: {query}</span>
          </article>
        ))}
      </div>
    </FeatureShell>
  );
}

function SchedulingTool({ feature }: Props) {
  const [slot, setSlot] = useState('Tomorrow 10:30 AM');
  const [confirmed, setConfirmed] = useState(false);

  return (
    <FeatureShell feature={feature}>
      <div className={`overlay-feature-widget__form ${feature.id}-widget`}>
        <label>
          Best slot
          <select value={slot} onChange={(e) => setSlot(e.target.value)}>
            <option>Tomorrow 10:30 AM</option>
            <option>Friday 2:00 PM</option>
            <option>Saturday 11:15 AM</option>
          </select>
        </label>
      </div>
      <button type="button" className="overlay-feature-widget__primary" onClick={() => setConfirmed(true)}>
        {confirmed ? `Confirmed: ${slot}` : 'Confirm slot'}
      </button>
    </FeatureShell>
  );
}

function ScoringTool({ feature }: Props) {
  const [intent, setIntent] = useState(72);
  const [fit, setFit] = useState(81);
  const score = Math.round((intent + fit) / 2);

  return (
    <FeatureShell feature={feature}>
      <div className={`overlay-feature-widget__sliders ${feature.id}-widget`}>
        <label>
          Intent
          <input type="range" min="0" max="100" value={intent} onChange={(e) => setIntent(Number(e.target.value))} />
        </label>
        <label>
          Fit
          <input type="range" min="0" max="100" value={fit} onChange={(e) => setFit(Number(e.target.value))} />
        </label>
      </div>
      <div className={`overlay-feature-widget__score ${feature.id}-widget`}>
        <strong>{score}</strong>
        <span>{score >= 80 ? 'Hot priority' : score >= 60 ? 'Warm lead' : 'Needs nurture'}</span>
      </div>
    </FeatureShell>
  );
}

function ReminderTool({ feature }: Props) {
  const [channel, setChannel] = useState('SMS');
  const [scheduled, setScheduled] = useState(false);

  return (
    <FeatureShell feature={feature}>
      <div className={`overlay-feature-widget__form ${feature.id}-widget`}>
        <label>
          Channel
          <select value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option>SMS</option>
            <option>WhatsApp</option>
            <option>Email</option>
          </select>
        </label>
      </div>
      <button type="button" className="overlay-feature-widget__primary" onClick={() => setScheduled(true)}>
        {scheduled ? `${channel} reminder scheduled` : 'Schedule reminder'}
      </button>
    </FeatureShell>
  );
}

function OpsTool({ feature }: Props) {
  const [generated, setGenerated] = useState(false);

  return (
    <FeatureShell feature={feature}>
      <div className={`overlay-feature-widget__cards ${feature.id}-widget`}>
        <article>
          <strong>Today</strong>
          <span>12 open tasks · 3 need attention</span>
        </article>
        <article>
          <strong>AI action</strong>
          <span>{generated ? 'Digest generated and queued' : 'Ready to generate team digest'}</span>
        </article>
      </div>
      <button type="button" className="overlay-feature-widget__primary" onClick={() => setGenerated(true)}>
        Generate digest
      </button>
    </FeatureShell>
  );
}

function AutomationTool({ feature }: Props) {
  const [enabled, setEnabled] = useState(false);

  return (
    <FeatureShell feature={feature}>
      <div className={`overlay-feature-widget__cards ${feature.id}-widget`}>
        <article>
          <strong>Trigger</strong>
          <span>When a customer matches this workflow</span>
        </article>
        <article>
          <strong>Action</strong>
          <span>Personalized response + team handoff</span>
        </article>
      </div>
      <button type="button" className="overlay-feature-widget__primary" onClick={() => setEnabled((v) => !v)}>
        {enabled ? 'Automation running' : 'Turn on automation'}
      </button>
    </FeatureShell>
  );
}

export default function CatalogFeatureWidget({ feature }: Props) {
  if (feature.id === 'lum-size-finder') return <SizeFinder feature={feature} />;
  if (feature.id === 'lum-order-ai') return <OrderAssistant feature={feature} />;
  if (feature.id === 'lum-bundles') return <SmartBundles feature={feature} />;
  if (feature.id === 'lum-search') return <SearchTool feature={feature} />;

  if (feature.category === 'scheduling') return <SchedulingTool feature={feature} />;
  if (feature.category === 'scoring') return <ScoringTool feature={feature} />;
  if (feature.category === 'reminders') return <ReminderTool feature={feature} />;
  if (feature.category === 'ops') return <OpsTool feature={feature} />;
  if (feature.category === 'automation') return <AutomationTool feature={feature} />;
  return <SearchTool feature={feature} />;
}
