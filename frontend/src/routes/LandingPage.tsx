/**
 * The home page: the firm's story, opening on a data hall in a frame. The
 * visitor's idea, typed into the box over it, is quoted back in the next
 * section and becomes the opening line of their consultation. Then the explanations are
 * tested, the answer fits on a page, the plan is six files, and the system is
 * built. Every line is the firm's own; nothing is invented.
 */
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Rise from '../film/Rise';
import FramedHero from '../film/FramedHero';
import Shot from '../film/Shot';
import StatementBand from '../film/StatementBand';
import { PRICE_LINE } from '../data/offer';
import { saveFrontDoor } from '../utils/frontDoor';
import { usePageMeta } from '../utils/pageMeta';

const EXAMPLE_IDEA = 'A booking app for home cleaners in Dubai';

const FILES = [
  { title: 'The answer page', body: 'The answer in two lines', look: 'page' },
  { title: 'The blueprint', body: 'Each decision, with its figures', look: 'page' },
  { title: 'The technical plan', body: 'A plan any team could build from', look: 'page' },
  { title: 'The operations manual', body: 'How it runs once handed over', look: 'page' },
  { title: 'The roadmap', body: 'What comes first, and in what order', look: 'bars' },
  { title: 'The presentation', body: 'The answer, as slides', look: 'slide' },
] as const;

/** The consultation's steps, as the hero's layers and the sections below it. */
const STEPS = ['Your words', 'The test', 'The answer', 'The plan', 'The build'] as const;

const LABELS = [
  { k: 'theirs', name: 'Yours', body: 'A figure you gave us, or one read from your files.' },
  { k: 'derived', name: 'Worked out', body: 'Calculated from your figures, with the calculation shown.' },
  { k: 'ours', name: 'Our estimate', body: 'A judgement where your figures were silent, with the reason.' },
] as const;

export default function LandingPage() {
  usePageMeta(
    'Your idea, tested and built into a working business',
    'Build My Version is an AI consultancy. Describe your idea; we test whether its numbers work, write the plan and build what it needs to run. A consultation is $200.',
  );
  const navigate = useNavigate();
  const [idea, setIdea] = useState('');
  // the quote below follows the typing once the visitor pauses, not on every key
  const [settled, setSettled] = useState('');
  useEffect(() => {
    const t = window.setTimeout(() => setSettled(idea), 280);
    return () => window.clearTimeout(t);
  }, [idea]);
  const typed = settled.trim().replace(/[.?!]+$/, '');
  const sentence = typed.length > 2 ? typed : EXAMPLE_IDEA;

  const start = () => {
    saveFrontDoor(idea);
    navigate('/demo');
  };

  return (
    <>
      <FramedHero
        layers={STEPS}
        after={
          <>
            <p className="film-mark">How a consultation works</p>
            <h2 className="film-h2">From your words to a working business, in five steps.</h2>
          </>
        }
      >
        <p className="film-mark">AI consultancy · Dubai</p>
        <h1 className="film-h">Your idea, tested and built into a working business.</h1>
        <p className="film-body">
          Describe it in your own words. We test whether its numbers work, write the plan, and build what it needs to run.
        </p>
        <form
          className="film-prompt"
          onSubmit={(e) => {
            e.preventDefault();
            start();
          }}
        >
          <div className="film-prompt-in">
            <label htmlFor="home-idea">Describe your idea</label>
            <textarea
              id="home-idea"
              rows={2}
              maxLength={2000}
              value={idea}
              placeholder={EXAMPLE_IDEA}
              onChange={(e) => setIdea(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  start();
                }
              }}
            />
            <div className="film-prompt-row">
              <span>{PRICE_LINE}</span>
              <button type="submit" className="film-pill">
                Start a consultation
              </button>
            </div>
          </div>
        </form>
        <p className="film-sub">Already running a business? Describe the decision in front of you instead.</p>
      </FramedHero>

      <Shot tone="dark" title="Your words">
        <p className="film-mark">01 · Your words</p>
        <Rise className="film-h2">It starts with your words. *Nothing else.*</Rise>
        <p className="film-quote">“{sentence.charAt(0).toUpperCase() + sentence.slice(1)}.”</p>
        <p className="film-body">
          There is no form to complete first. Questions come one at a time, and each depends on your answer to the one
          before it.
        </p>
        <ul className="film-rows">
          <li>
            <b>Q.01</b>
            <span>How will it earn?</span>
          </li>
          <li>
            <b>Q.02</b>
            <span>What will it cost to run?</span>
          </li>
          <li>
            <b>Q.03</b>
            <span>What do you already know for certain?</span>
          </li>
        </ul>
      </Shot>

      <Shot tone="dark" title="The test">
        <p className="film-mark">02 · The test</p>
        <Rise className="film-h2">Every explanation is tested. *Including yours.*</Rise>
        <p className="film-body">
          We set out every cause consistent with what you told us and test each against your numbers. One your figures
          contradict is ruled out, with the reason.
        </p>
        <p className="film-body">
          The strongest goes to two reviewers whose task is to disprove it. It stays only if it survives both.
        </p>
      </Shot>

      <Shot tone="dark" title="The answer">
        <p className="film-mark">03 · The answer</p>
        <Rise className="film-h2">The answer fits on *one page.*</Rise>
        <p className="film-body">
          The question, the answer in two lines, the figures it rests on, what to do first and what we would not do.
        </p>
        <div className="film-labels">
          {LABELS.map((l) => (
            <div className="film-label" key={l.k}>
              <span className={`film-chip film-chip--${l.k}`}>{l.name}</span>
              <p>{l.body}</p>
            </div>
          ))}
        </div>
        <p className="film-sub">You can challenge it. Nothing is built until you decide.</p>
      </Shot>

      <StatementBand
        caption="Private AI · on your own servers"
        lead="Every figure in your plan says"
        rest="where it came from."
        action={
          <Link to="/approach" className="film-pill film-pill--light">
            How a consultation is run
          </Link>
        }
      />

      <Shot title="The plan" stack>
        <p className="film-mark">04 · The plan</p>
        <Rise className="film-h2">Six files. *One plan.*</Rise>
        <p className="film-body">The plan is yours, whether you build with us, with your own team or with another firm.</p>
        <ul className="film-docs">
          {FILES.map((f) => (
            <li key={f.title} className={`film-doc film-doc--${f.look}`}>
              <div className="film-doc-paper" aria-hidden="true">
                <i />
                <i />
                <i />
                <i />
                <i />
              </div>
              <b>{f.title}</b>
              <span>{f.body}</span>
            </li>
          ))}
        </ul>
      </Shot>

      <Shot title="The build">
        <p className="film-mark">05 · The build</p>
        <Rise className="film-h2">Then we *build it.*</Rise>
        <p className="film-body">
          The website, the app, the bookings and payments, the AI. Built to the plan, launched and handed over.
        </p>
        <div className="film-actions">
          <Link to="/demo" className="film-pill">
            Start a consultation
          </Link>
          <Link to="/services" className="film-pill film-pill--ghost">
            See the services
          </Link>
        </div>
        <p className="film-sub">
          {PRICE_LINE} Built by consultants and engineers: the method was written by consultants and built into software
          by engineers.
        </p>
      </Shot>
    </>
  );
}
