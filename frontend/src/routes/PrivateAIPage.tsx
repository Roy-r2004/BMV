import { useEffect, useRef, useState } from 'react';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import EnvironmentModel, { type Mode, type Stage } from '../components/private-ai/EnvironmentModel';
import { consultingEmailUrl } from '../api/client';
import '../styles/private-ai.css';

// One scroll story over a 3D model of the client's environment. Each section's
// `data-stage` tells EnvironmentModel what to build and where to look.

const CONTACT_SUBJECT = 'Private AI deployment';
const CONTACT_BODY =
  "Hi,\n\nI'd like to discuss a private AI deployment.\n\nMy business: \nWhat the AI needs to do: \nData it touches: \n";

const CHAPTERS: { name: string; stages: Stage[] }[] = [
  { name: 'Your AI', stages: ['hero'] },
  { name: 'Why private', stages: ['why'] },
  { name: 'How it works', stages: ['how1', 'how2', 'how3', 'how4'] },
  { name: 'Cloud or private', stages: ['compare'] },
  { name: 'Honest fit', stages: ['honest'] },
  { name: 'Talk to us', stages: ['cta'] },
];

// The order matches WHY_PARTS in EnvironmentModel: data, model, hardware, boundary.
// Each reason rings its part of the model.
const WHY = [
  { title: 'Data stays private', body: 'Sensitive information can remain inside infrastructure controlled by your business.' },
  { title: 'Control the model', body: 'Choose and customize open-weight models around your actual workload.' },
  { title: 'Predictable economics', body: 'For sustained workloads, dedicated infrastructure can replace variable API costs.' },
  { title: 'No platform lock-in', body: 'You own the deployment and can continue operating it independently.' },
] as const;

const HOW = [
  {
    stage: 'how1',
    title: 'We understand the workload.',
    body: 'We identify what the AI needs to do, what data it touches, latency requirements, integrations, security requirements, and expected usage.',
  },
  {
    stage: 'how2',
    title: 'We design the stack.',
    body: 'We select the model, inference architecture, hardware requirements, storage, security boundaries, and integrations.',
  },
  {
    stage: 'how3',
    title: 'We deploy it into your environment.',
    body: 'The system runs on dedicated infrastructure controlled by your business.',
  },
  {
    stage: 'how4',
    title: 'We integrate it with the business.',
    body: 'We connect it to your internal software, workflows, databases, permissions, and human review.',
  },
] as const;

const CLOUD_ROWS = ['Fastest to launch', 'Great for experimentation', 'Usage-based pricing', 'Third-party infrastructure'];
const PRIVATE_ROWS = [
  'Dedicated deployment',
  'Greater infrastructure control',
  'Predictable high-volume economics',
  'Designed for sensitive workloads',
];

const MODE_READ: Record<Mode, string> = {
  cloud: 'Cloud: each request leaves your environment and runs on a provider’s servers.',
  private: 'Private: requests go from your application to the model and back without leaving your boundary.',
};

// What the picture shows, in one line.
const WHY_CAPTIONS = [
  'Your data never leaves the boundary.',
  'The model is yours to choose and tune.',
  'Sustained workloads run on hardware you own.',
  'You own the deployment and can run it without us.',
];
function caption(stage: Stage, why: number, mode: Mode) {
  switch (stage) {
    case 'hero':
      return 'A working model of your environment. Everything inside the blue line runs on infrastructure you control.';
    case 'why':
      return WHY_CAPTIONS[why];
    case 'how1':
      return 'First, the people and the data the work touches.';
    case 'how2':
      return 'Then the stack: the model and the hardware it runs on.';
    case 'how3':
      return 'Then your security boundary goes around all of it.';
    case 'how4':
      return 'Last, it is wired into the software your team already uses.';
    case 'compare':
      return mode === 'cloud'
        ? 'Cloud: requests cross your boundary to a provider and back.'
        : 'Private: requests stay inside your boundary.';
    case 'honest':
      return 'Some workloads belong in the cloud. The design follows the requirement.';
    case 'cta':
      return 'Your AI. Your data. Your infrastructure.';
  }
}

function Icon({ d, className = 'w-4 h-4' }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} className={className} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}
const ARROW = 'M17 8l4 4m0 0l-4 4m4-4H3';
const LOCK =
  'M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z';

function Chapter({ stage, id, children }: { stage: Stage; id?: string; children: React.ReactNode }) {
  const step = stage.startsWith('how');
  return (
    <section className={`pai-chapter${step ? ' pai-chapter--step' : ''}`} data-stage={stage} id={id}>
      <div className="container-max px-4 sm:px-6 w-full">
        <div className="pai-col">{children}</div>
      </div>
    </section>
  );
}

export default function PrivateAIPage() {
  const storyRef = useRef<HTMLDivElement>(null);
  const [stage, setStage] = useState<Stage>('hero');
  const [why, setWhy] = useState(0);
  const [mode, setMode] = useState<Mode>('cloud');
  const pinnedUntil = useRef(0);

  // While the reasons are on screen, walk through them unless one was picked.
  useEffect(() => {
    if (stage !== 'why' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = window.setInterval(() => {
      if (performance.now() > pinnedUntil.current) setWhy((w) => (w + 1) % WHY.length);
    }, 3400);
    return () => window.clearInterval(id);
  }, [stage]);

  const pickWhy = (i: number) => {
    pinnedUntil.current = performance.now() + 9000;
    setWhy(i);
  };

  const goTo = (s: Stage) => {
    const el = storyRef.current?.querySelector(`[data-stage="${s}"]`);
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // Narrow screens read a chapter from its top (picture above, panel below).
    el?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: window.innerWidth < 1024 ? 'start' : 'center' });
  };

  const email = consultingEmailUrl(CONTACT_SUBJECT, CONTACT_BODY);

  return (
    <div className="pai-page min-h-screen overflow-x-clip">
      <SiteNav />

      <div className="pai-story" ref={storyRef}>
        <EnvironmentModel storyRef={storyRef} why={why} mode={mode} onStage={setStage}>
          <nav className="pai-index" aria-label="Sections on this page">
            {CHAPTERS.map((c) => {
              const on = c.stages.includes(stage);
              return (
                <button
                  key={c.name}
                  type="button"
                  className={on ? 'is-on' : undefined}
                  aria-current={on ? 'step' : undefined}
                  onClick={() => goTo(c.stages[0])}
                >
                  <span>{c.name}</span>
                  <i aria-hidden="true" />
                </button>
              );
            })}
          </nav>
          <p className="pai-caption">{caption(stage, why, mode)}</p>
        </EnvironmentModel>

        <Chapter stage="hero">
          <h1 className="pai-display pai-h1">Your AI. Your data. Your infrastructure.</h1>
          <p className="pai-lede">
            For businesses that need tighter control over sensitive data, we deploy private AI systems on dedicated
            infrastructure you own and control.
          </p>
          <div className="pai-actions">
            <a href={email} className="pai-cta">
              Explore a private deployment
              <Icon d={ARROW} />
            </a>
            <button type="button" className="pai-ghost" onClick={() => goTo('how1')}>
              How it works
            </button>
          </div>
          <p className="pai-note">
            <Icon d={LOCK} />
            No forced cloud dependency. No per-token lock-in.
          </p>
        </Chapter>

        <Chapter stage="why">
          <h2 className="pai-display pai-h2">Why companies choose private AI</h2>
          <div className="pai-reasons">
            {WHY.map((w, i) => (
              <button
                key={w.title}
                type="button"
                className={`pai-reason${i === why ? ' is-on' : ''}`}
                aria-pressed={i === why}
                onClick={() => pickWhy(i)}
                onMouseEnter={() => pickWhy(i)}
                onFocus={() => pickWhy(i)}
              >
                <span className="pai-reason-mark" aria-hidden="true" />
                <span>
                  <span className="pai-reason-title">{w.title}</span>
                  <span className="pai-reason-body">{w.body}</span>
                </span>
              </button>
            ))}
          </div>
        </Chapter>

        {HOW.map((h, i) => (
          <Chapter key={h.stage} stage={h.stage} id={i === 0 ? 'how-it-works' : undefined}>
            <p className="pai-stepno pai-display">
              {String(i + 1).padStart(2, '0')}
              <small>of {HOW.length}</small>
            </p>
            <h2 className="pai-display pai-h2 pai-h2--step">{h.title}</h2>
            <p className="pai-body">{h.body}</p>
          </Chapter>
        ))}

        <Chapter stage="compare">
          <h2 className="pai-display pai-h2">Cloud AI vs private AI</h2>
          <p className="pai-body">Switch between them and watch where each request goes.</p>
          <div className="pai-seg" role="group" aria-label="Deployment to show">
            {(['cloud', 'private'] as const).map((m) => (
              <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}>
                {m === 'cloud' ? 'Cloud AI' : 'Private AI'}
              </button>
            ))}
          </div>
          <p className="pai-mode-read" aria-live="polite">
            {MODE_READ[mode]}
          </p>
          <div className="pai-compare">
            <div className={mode === 'cloud' ? undefined : 'is-dim'}>
              <h3 className="pai-display">Cloud AI</h3>
              <ul>
                {CLOUD_ROWS.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
            <div className={mode === 'private' ? undefined : 'is-dim'}>
              <h3 className="pai-display">Private AI</h3>
              <ul>
                {PRIVATE_ROWS.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          </div>
          <p className="pai-body">
            <strong>Own the infrastructure. Pay for the compute you actually use.</strong> Rather than permanently paying
            an AI provider a margin on every request, suitable workloads can run on infrastructure you own. Ongoing costs
            come from infrastructure operation, electricity, maintenance, and the support arrangement you choose.
          </p>
          <p className="pai-quote">You decide the hardware. You control the environment. We architect, deploy, and integrate it.</p>
        </Chapter>

        <Chapter stage="honest">
          <h2 className="pai-display pai-h2">Not every workload should be local.</h2>
          <p className="pai-body">
            Private AI makes the most sense when data sensitivity, compliance, high sustained usage, latency, or
            infrastructure control justify it.
          </p>
          <p className="pai-body">For other projects, cloud models may be faster and more economical.</p>
          <p className="pai-quote">We design around the business requirement, not around one deployment ideology.</p>
        </Chapter>

        <Chapter stage="cta">
          <h2 className="pai-display pai-h2">Need AI that stays under your control?</h2>
          <p className="pai-lede">
            Tell us what you're trying to run, what data it touches, and what constraints you have. We'll tell you
            whether private AI actually makes sense and what it would take to deploy.
          </p>
          <div className="pai-actions">
            <a href={email} className="pai-cta">
              Discuss a private AI deployment
              <Icon d={ARROW} />
            </a>
          </div>
          <p className="pai-note">
            <Icon d={LOCK} />
            No obligation. Just a technical conversation.
          </p>
        </Chapter>
      </div>

      <SiteFooter />
    </div>
  );
}
