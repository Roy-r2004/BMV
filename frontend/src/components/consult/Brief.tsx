/**
 * The brief: before any fact-finding, the question we will answer.
 *
 * Every engagement at a serious firm starts by agreeing the question. Their
 * own words sit at the top in their hand; our framing of them sits under it,
 * with what they will walk away with and what is in and out of scope. On the
 * right, how the engagement runs and who is on it.
 */
import type { Scope } from '../../api/consultant';

const STEPS: { title: string; body: string }[] = [
  { title: 'We ask until we have everything.', body: "About 20 minutes. You'll see the list of what we need fill in as you go." },
  { title: 'You never fetch anything.', body: "Don't know a figure? We estimate it and mark it as ours. Have a file? Drop it in and we read it." },
  { title: 'We test every explanation.', body: 'Yours too. Two reviewers try to break our answer before you see it.' },
  { title: 'You get the answer and every plan.', body: 'Written while you read. You make the calls; we do the work.' },
];

function Skeleton() {
  return (
    <div aria-live="polite">
      <p className="cx-lbl">The question we'll answer</p>
      <p className="cx-muted" style={{ fontSize: 15, margin: '0 0 14px' }}>
        Writing your brief<span className="cx-typing"><i /><i /><i /></span>
      </p>
      <div style={{ display: 'grid', gap: 10 }}>
        <div className="cx-skel" style={{ width: '92%', height: 16 }} />
        <div className="cx-skel" style={{ width: '70%', height: 16 }} />
      </div>
      <div className="cx-lets">
        {[0, 1, 2].map((i) => (
          <div key={i} style={{ display: 'grid', gap: 8 }}>
            <div className="cx-skel" style={{ width: '50%' }} />
            <div className="cx-skel" style={{ width: '90%' }} />
            <div className="cx-skel" style={{ width: '70%' }} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Brief({
  firstName,
  said,
  scope,
  loading,
  onConfirm,
  onChange,
}: {
  firstName: string | null;
  said: string;
  scope: Scope | null;
  loading: boolean;
  onConfirm: () => void;
  onChange: () => void;
}) {
  const question = scope?.question?.trim() ?? '';
  const lets = scope?.lets;
  const inScope = scope?.in_scope ?? [];
  const outScope = scope?.out_scope ?? [];
  const quote = said.trim().replace(/^["“]|["”]$/g, '');

  return (
    <section className="cx-stage">
      <p className="cx-kicker">The brief</p>
      <h1 className="cx-title">
        {firstName ? `Before we start, ${firstName}, here's the question we'll answer.` : "Before we start, here's the question we'll answer."}
      </h1>
      <p className="cx-lede">
        Every engagement at a serious firm starts by agreeing the question. Get it right and everything after it is aimed at
        the decision you actually have to make.
      </p>

      <div className="cx-brief">
        <div className="cx-pane">
          <p className="cx-lbl">What you told us</p>
          <p className="cx-said">“{quote}”</p>

          <div className="cx-qmain">
            {loading ? (
              <Skeleton />
            ) : (
              <>
                <p className="cx-lbl">The question we'll answer</p>
                {question ? <h2>{question}</h2> : <p className="cx-pending">We'll pin the exact question down as we talk.</p>}
                {lets && (lets.know || lets.see || lets.have) ? (
                  <div className="cx-lets">
                    {lets.know ? <div><b>You'll know</b>{lets.know}</div> : null}
                    {lets.see ? <div><b>You'll see</b>{lets.see}</div> : null}
                    {lets.have ? <div><b>You'll have</b>{lets.have}</div> : null}
                  </div>
                ) : null}
                {inScope.length || outScope.length ? (
                  <div className="cx-scope">
                    {inScope.length ? (
                      <div>
                        <p className="cx-lbl">We'll look at</p>
                        <ul className="in">{inScope.map((s) => <li key={s}>{s}</li>)}</ul>
                      </div>
                    ) : null}
                    {outScope.length ? (
                      <div>
                        <p className="cx-lbl">We won't</p>
                        <ul className="out">{outScope.map((s) => <li key={s}>{s}</li>)}</ul>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>

        <aside className="cx-pane cx-how">
          <h3>How this works</h3>
          <ol>
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <span>{i + 1}</span>
                <div><b>{s.title}</b>{s.body}</div>
              </li>
            ))}
          </ol>
          <div className="cx-team">
            <p className="cx-lbl">Who's on it</p>
            <ul>
              <li><i>EL</i><div>Engagement lead <span>runs the questions and the answer</span></div></li>
              <li><i>AN</i><div>Analyst <span>does the arithmetic, and shows it</span></div></li>
              <li><i className="r">R</i><div>Two reviewers <span>whose only job is to break the answer</span></div></li>
            </ul>
          </div>
        </aside>
      </div>

      <div className="cx-actions cx-row">
        <button type="button" className="cx-btn cx-btn--blue" onClick={onConfirm} disabled={loading}>
          That's the question, let's start
        </button>
        <button type="button" className="cx-textbtn" onClick={onChange}>Change it</button>
      </div>
    </section>
  );
}
