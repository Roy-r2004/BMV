/**
 * The landing page: the honesty is what it sells.
 *
 * It opens where the consultation opens — "What are you trying to work out?"
 * — beside one example answer drawn in 3D, so a visitor sees the product
 * before reading about it. Then: their own idea tested like any other, the
 * findings that were not software, how it works, everything they walk away
 * with (real screens and real pages from one engagement), pricing, and the
 * question again.
 *
 * Every figure on it belongs to the one example, and says so.
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import WeekScene from '../components/home/WeekScene';
import { saveFrontDoor } from '../utils/frontDoor';
import '../styles/home.css';

function Ask({ big = false }: { big?: boolean }) {
  const navigate = useNavigate();
  const [text, setText] = useState('');
  const start = () => {
    saveFrontDoor(text);
    navigate('/demo');
  };
  return (
    <form
      className={`home-ask${big ? ' big' : ''}`}
      onSubmit={(e) => {
        e.preventDefault();
        start();
      }}
    >
      {!big ? <label htmlFor="home-ask-top">What are you trying to work out?</label> : null}
      <div className="home-box">
        <textarea
          id={big ? 'home-ask-bottom' : 'home-ask-top'}
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              start();
            }
          }}
          placeholder={big ? "Say it the way you'd say it across a table." : 'e.g. "We keep missing calls in the evening." or "I want to open a second clinic but can\'t tell if the numbers work."'}
          aria-label="What are you trying to work out?"
        />
        <div className="home-box-row">
          <span>{big ? 'Free. About 15 minutes to an honest answer.' : 'A problem, a decision, or something you want to start.'}</span>
          <button type="submit" className="home-btn blue">Start the conversation</button>
        </div>
      </div>
    </form>
  );
}

function Circle() {
  return (
    <svg className="home-circle" viewBox="0 0 1000 200" preserveAspectRatio="none" aria-hidden="true">
      <path
        d="M140 22 C 380 2, 820 6, 968 34 C 1012 48, 1004 150, 950 176 C 760 206, 260 204, 40 182 C -6 170, -8 70, 52 38 C 90 18, 150 14, 196 12"
        fill="none" stroke="#2563EB" strokeWidth="2.6" strokeLinecap="round" vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

const GETS = [
  { t: 'Your honest answer', d: 'The finding in two lines, the evidence in your own figures, and what the fix is worth, with the working shown.', w: 'Every consultation' },
  { t: 'Monday plan and pilot tracker', d: 'What to do this week, the message to send, and the numbers to log each week until you know.', w: 'Every consultation' },
  { t: 'The blueprint', d: 'What to build, module by module, in what order, and how it makes or saves money.', w: 'With the package' },
  { t: 'The technical plan', d: 'Every module and AI agent specced for whoever builds it: data, tools, guardrails and the build order.', w: 'With the package' },
  { t: 'The operations manual', d: 'Who does what, every day: the procedures, the checklists and the forms your staff actually use.', w: 'With the package' },
  { t: 'Your product screens', d: 'Your software drawn for your business, with your services and your numbers, each screen checked twice.', w: 'With the package' },
  { t: 'The execution playbook', d: 'The steps in order, and who takes each one: you, us, or a partner. Quick wins first.', w: 'With the package' },
  { t: 'Your AI team', d: 'The AI employees the system needs, what each one decides alone, and where it hands over to a person.', w: 'With the package' },
];

export default function LandingPage() {
  const [revealed, setRevealed] = useState(false);

  return (
    <div className="home">
      <SiteNav />

      <header className="home-hero">
        <div className="home-wrap home-hero-grid">
          <div>
            <h1 className="home-display home-h1">
              Before you build or open anything, find out what will <em>actually work.</em>
            </h1>
            <p className="home-lead">
              Running a business or planning one, tell us what you're trying to work out. We test every
              explanation against your own numbers, yours included, and say so plainly when the answer
              isn't software.
            </p>
            <Ask />
            <div className="home-trust">
              <p><b>Free</b> to find out</p>
              <p><b>About 15 minutes</b> to an honest answer</p>
              <p><b>Nothing built</b> until you say so</p>
            </div>
          </div>

          <div>
            <div className={`home-answer${revealed ? ' revealed' : ''}`}>
              <span className="home-chip dim">Example consultation</span>
              <p className="home-for">A reformer pilates studio. The owner came in asking for a booking app.</p>
              <div className="home-heads">
                <p className="home-pre home-display">Her week, as she described it.</p>
                <h2 className="home-finding home-display">
                  You're not short of clients.<span>You're full.</span>
                </h2>
              </div>
              <WeekScene onReveal={() => setRevealed(true)} />
              <div className="home-band">
                <div><b>384 of 432</b><span>spots taken every week</span></div>
                <div className="move"><b>≈ $45,000 a year</b><span>moving 6pm and 7pm to $28, if regulars stay</span></div>
              </div>
            </div>
            <p className="home-under">
              Her week, drawn only from what she told us. The answer was a six-week price pilot, not an app.
            </p>
          </div>
        </div>
      </header>

      <section className="home-s home-paths">
        <div className="home-wrap">
          <h2 className="home-display home-h2">Running a business, or opening one.</h2>
          <p className="home-intro">
            The same consultation, asked differently. A business that trades has volumes, prices and a
            ceiling to test. One being planned has a price it means to charge and a capacity it is
            building toward, and those get tested before you spend.
          </p>
          <div className="home-path-grid">
            <div className="home-path">
              <span className="home-chip blue">Already trading</span>
              <h3>We find what's really holding it back.</h3>
              <ul>
                <li>Your volumes, prices and ceiling, from your answers or your own booking export</li>
                <li>Every explanation tested against them, including the one you walked in with</li>
                <li>A fix you can pilot on Monday, and the number that tells you it worked</li>
              </ul>
              <p className="home-path-eg">"You're not short of clients. You're full."</p>
              <Link to="/demo" className="home-btn sm">Start with your business</Link>
            </div>
            <div className="home-path open">
              <span className="home-chip green">Opening something new</span>
              <h3>We test the plan before you spend on it.</h3>
              <ul>
                <li>The price you plan to charge and the capacity you're building toward</li>
                <li>Whether the numbers hold at the volume you can realistically reach, and when</li>
                <li>What to prove in the first weeks, before the lease, the hire or the build</li>
              </ul>
              <p className="home-path-eg">"The second clinic can work. Not at your current prices."</p>
              <Link to="/demo" className="home-btn blue sm">Start with your plan</Link>
            </div>
          </div>
        </div>
      </section>

      <section className="home-s home-tested">
        <div className="home-wrap home-two">
          <div>
            <h2 className="home-display home-h2">Your idea gets tested like any other.</h2>
            <p className="home-intro">
              We write out every explanation that fits what you told us, test each one against your own
              figures, and give the strongest to two reviewers whose only job is to break it. You watch it
              happen, live.
            </p>
            <p className="home-intro">
              People are usually right about the symptom and often wrong about the cause. That's not a
              criticism. It's why you'd hire a consultant.
            </p>
          </div>
          <div>
            <div className="home-hyp out">
              <span className="n">1</span>
              <div><div className="chips"><span className="home-chip blue">What you told us</span></div><p className="s1">Booking admin is costing you evening clients.</p></div>
              <div><span className="home-chip amber">Doesn't hold up</span><p className="why">The evenings are already full. A booking app can't add spots to a class that's sold out.</p></div>
            </div>
            <div className="home-hyp">
              <span className="n">2</span>
              <div><div className="chips"><span className="home-chip dim">Capacity</span></div><p className="s1">You're at your ceiling: 12 reformers, 36 classes a week.</p></div>
              <div><span className="home-chip green">Supported</span><p className="why">12 × 6 × 6 = 432 spots. Every evening has a waiting list.</p></div>
            </div>
            <div className="home-hyp lead">
              <Circle />
              <span className="home-best home-hand">holds up best</span>
              <span className="n">3</span>
              <div><div className="chips"><span className="home-chip dim">Price</span><span className="home-chip dim">Software can't fix this</span></div><p className="s1">She charges $10 less than two comparable studios, so the evenings sell out.</p></div>
              <div><span className="home-chip green">Supported</span><p className="why">$22 here, $32 nearby, and a waiting list at 6pm and 7pm.</p></div>
            </div>
            <div className="home-margin">
              <div><h4>Does anything else explain it?</h4><p className="home-hand">Tried location and class times. Neither explains a waiting list at her price.</p><p className="home-hand held">held ✓</p></div>
              <div><h4>Are we just agreeing with her?</h4><p className="home-hand">No. It contradicts what she walked in with. It rests on her figures, not her words.</p><p className="home-hand held">held ✓</p></div>
            </div>
          </div>
        </div>
      </section>

      <section className="home-s home-tint" id="examples">
        <div className="home-wrap">
          <h2 className="home-display home-h2">Sometimes the answer isn't software.</h2>
          <p className="home-intro">
            We build software, so recommending it when it won't help is the most expensive mistake we could
            make. When the fix is a price, a process or a person, you read that in the first sentence.
          </p>
          <div className="home-finds">
            {[
              { who: 'A reformer pilates studio', came: 'Came in asking for a booking app.', a: "You're not short of clients.", b: "You're full.", kind: 'Pricing', tone: 'amber', next: 'Next: a six-week price pilot' },
              { who: 'A family dental clinic', came: 'Came in asking for more ads.', a: 'Your ads work.', b: "Your follow-up doesn't.", kind: 'Software', tone: 'blue', next: 'Next: we build the recall system' },
              { who: 'A café, not open yet', came: 'Came in asking for an ordering app.', a: 'The location works.', b: "The rent doesn't, without breakfast.", kind: 'Opening', tone: 'green', next: 'Next: a four-week breakfast trial' },
            ].map((f) => (
              <div className="home-find" key={f.who}>
                <p className="who">{f.who}</p>
                <p className="came">{f.came}</p>
                <h3>{f.a}<span>{f.b}</span></h3>
                <div className="next"><span className={`home-chip ${f.tone}`}>{f.kind}</span><b>{f.next}</b></div>
              </div>
            ))}
          </div>
          <p className="home-fine">Illustrative examples. Your answer comes from your numbers, and we never invent one.</p>
        </div>
      </section>

      <section className="home-s" id="how">
        <div className="home-wrap">
          <h2 className="home-display home-h2">How it works.</h2>
          <p className="home-intro">
            About fifteen minutes to an honest answer. Building only starts if you choose it, and it's one
            click away whatever we find.
          </p>
          <ol className="home-steps">
            {[
              { h: 'One question', p: "What you're trying to work out, in your own words. No forms.", t: '2 min' },
              { h: 'A short conversation', p: 'One question at a time. Your figures fill in beside you as you answer.', t: '5 min' },
              { h: 'Watch it think', p: 'Explanations tested and struck out. Two reviewers argue in the margin.', t: '2 min' },
              { h: 'Your answer', p: 'The finding in two lines, your own week drawn, and what the fix is worth.', t: 'You decide', gate: true },
              { h: 'Your package', p: "Monday's steps, the documents, your screens, and a tracker for the pilot.", t: '10 min, if you choose' },
            ].map((s, i) => (
              <li className={`home-step${s.gate ? ' gate' : ''}`} key={s.h}>
                <span className="no">{i + 1}</span>
                <h3>{s.h}</h3>
                <p>{s.p}</p>
                <span className="t">{s.t}</span>
              </li>
            ))}
          </ol>
          <div className="home-gateline">
            <p><b>Nothing is built before you've read the answer.</b> <span>You can correct it, send us a file, or ask us to think again.</span></p>
            <Link to="/demo" className="home-btn blue sm">Start the conversation</Link>
          </div>
        </div>
      </section>

      <section className="home-s">
        <div className="home-wrap">
          <h2 className="home-display home-h2">Everything you walk away with.</h2>
          <p className="home-intro">
            Whatever the answer, you leave with more than a paragraph. These are real screens and real pages
            from one engagement.
          </p>
          <div className="home-show">
            <div className="home-screens">
              <figure className="home-shot s3"><img src="/landing/screen-analytics.jpg" alt="Analytics screen drawn for the studio" loading="lazy" /></figure>
              <figure className="home-shot main">
                <div className="bar"><i /><i /><i /><span>Halo Flow: dashboard</span></div>
                <img src="/landing/screen-dashboard.jpg" alt="The dashboard drawn for the studio" loading="lazy" />
              </figure>
              <figure className="home-shot s2"><img src="/landing/screen-schedule.jpg" alt="Schedule screen drawn for the studio" loading="lazy" /></figure>
              <p className="home-cap home-hand">your software, drawn for your business</p>
            </div>
            <div className="home-pages">
              <img className="pg p1" src="/landing/doc-pilot-2.jpg" alt="A page of the pilot plan" loading="lazy" />
              <img className="pg p2" src="/landing/doc-blueprint-4.jpg" alt="A page of the blueprint" loading="lazy" />
              <img className="pg p3" src="/landing/doc-technical-4.jpg" alt="A page of the technical plan" loading="lazy" />
              <img className="pg p4" src="/landing/doc-operations-3.jpg" alt="A page of the operations manual" loading="lazy" />
              <p className="home-cap home-hand">every page written for you</p>
            </div>
          </div>
          <div className="home-gets">
            {GETS.map((g) => (
              <div className="home-get" key={g.t}>
                <h3>{g.t}</h3>
                <p>{g.d}</p>
                <span className="when">{g.w}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="home-s">
        <div className="home-wrap home-two home-pack">
          <div>
            <h2 className="home-display home-h2">It opens with Monday.</h2>
            <p className="home-intro">
              Most consultancies bury the first step on page forty. Your package starts with what you can do
              this week, before any software exists.
            </p>
            <div className="home-list">
              <div><b>Every number is yours</b><span>Your figures, arithmetic on them with the working shown, or a number we propose and label as ours.</span></div>
              <div><b>Assumptions are marked</b><span>Whatever we couldn't check is listed, and the pilot is how you settle it.</span></div>
              <div><b>Share it with a partner</b><span>A read-only link you can send, and turn off whenever you like.</span></div>
            </div>
          </div>
          <div className="home-monday">
            <h3>Start here on Monday</h3>
            <p className="sub">None of these needs the software to be built first.</p>
            <ol>
              <li><span className="k">1</span><div><b>Tell your 6pm and 7pm regulars the new $28 price, starting in two weeks.</b><span>The message is written for you.</span></div></li>
              <li><span className="k">2</span><div><b>Keep every daytime class at $22.</b><span>Changing only the evenings lets you read the effect cleanly.</span></div></li>
              <li><span className="k">3</span><div><b>Log fill and the waiting list each week for six weeks.</b><span>At the end, the rule you agreed on up front tells you whether to keep $28.</span></div></li>
            </ol>
          </div>
        </div>
      </section>

      <section className="home-s home-tint" id="pricing">
        <div className="home-wrap">
          <h2 className="home-display home-h2 wide">The consultation is free. Building is quoted with you.</h2>
          <p className="home-intro">No checkout, no card. If you want it built, we write the scope together after you've read the answer.</p>
          <div className="home-plans">
            <div className="home-plan free">
              <p className="nm">The consultation</p><p className="pr">Free</p>
              <ul><li>Your honest answer, with the working</li><li>Your Monday plan and pilot tracker</li><li>Blueprint, technical plan, operations manual</li><li>Product screens drawn for you</li></ul>
              <div className="cta"><Link to="/demo" className="home-btn blue sm">Start the conversation</Link></div>
            </div>
            <div className="home-plan"><p className="nm">Launch</p><p className="pr">4 to 8 weeks, quoted</p><ul><li>The core of your package, built for real</li><li>Owner and admin basics</li><li>Payments on your main path</li></ul></div>
            <div className="home-plan"><p className="nm">Growth</p><p className="pr">8 to 12 weeks, quoted</p><ul><li>Everything in Launch</li><li>Staff dashboards and automations</li><li>Care after launch</li></ul></div>
            <div className="home-plan"><p className="nm">Custom</p><p className="pr">Scoped together</p><ul><li>Integrations and multiple locations</li><li>Advanced roles and reporting</li><li>An ongoing product team</li></ul></div>
          </div>
        </div>
      </section>

      <section className="home-last">
        <div className="home-wrap">
          <h2 className="home-display">What are you trying to work out?</h2>
          <p>A problem that's costing you, a decision you're stuck on, or something you want to start.</p>
          <Ask big />
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
