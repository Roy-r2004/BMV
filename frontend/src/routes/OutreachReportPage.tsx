/**
 * The private report a business opens from Roy's Instagram message: what we
 * saw, two or three changes and the AI that makes each one, and a way to book a
 * call. Made from public information only, never listed, never indexed.
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { getOutreachReport, type OutreachReport } from '../api/outreach';
import { COMPANY } from '../data/company';
import '../styles/consult.css';
import { usePageMeta } from '../utils/pageMeta';

function useNoIndex() {
  useEffect(() => {
    const meta = document.createElement('meta');
    meta.name = 'robots';
    meta.content = 'noindex,nofollow';
    document.head.appendChild(meta);
    return () => meta.remove();
  }, []);
}

function mailto(email: string, subject: string) {
  return `mailto:${email}?subject=${encodeURIComponent(subject)}`;
}

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export default function OutreachReportPage() {
  const { token = '' } = useParams<{ token: string }>();
  const [data, setData] = useState<OutreachReport | null>(null);
  const [missing, setMissing] = useState(false);
  usePageMeta(data ? `For ${data.name}` : 'A page made for you');
  useNoIndex();

  useEffect(() => {
    let cancelled = false;
    getOutreachReport(token)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setMissing(true));
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="cx">
      <header className="cx-top">
        <div className="cx-brand">
          <span className="fm-brand">
            <img src="/logo-160.png" alt="" width={36} height={36} />
            <span>{COMPANY.name}</span>
          </span>
        </div>
      </header>
      <main className="cx-wrap pb-24">
        {missing ? (
          <section className="max-w-[640px] pt-[10vh]">
            <h1 className="cx-h2">This page is no longer here.</h1>
            <p className="cx-lead mt-5">
              It may have been taken down. You can still write to us at{' '}
              <a className="cx-blue underline" href={`mailto:${COMPANY.email}`}>
                {COMPANY.email}
              </a>
              .
            </p>
          </section>
        ) : !data ? (
          <p className="cx-lead pt-[10vh]">
            Opening your page<span className="cx-typing"><i /><i /><i /></span>
          </p>
        ) : (
          <article className="max-w-[760px] pt-[8vh]">
            <p className="cx-faint text-[15px]">Made for {data.name}, {data.city}</p>
            <h1 className="cx-h1 mt-4">What AI could change for {data.name}.</h1>

            <section className="mt-12">
              <h2 className="cx-h3">What we saw</h2>
              <p className="cx-lead mt-3">{data.today}</p>
            </section>

            <section className="mt-12">
              <h2 className="cx-h3">What could change</h2>
              <ol className="mt-6 grid gap-6">
                {data.changes.map((c, i) => (
                  <li key={i} className="rounded border border-[var(--cx-line)] p-6">
                    <h3 className="text-[19px] font-semibold leading-snug">{c.change}</h3>
                    <dl className="mt-4 grid gap-3 text-[15.5px] leading-relaxed">
                      <div>
                        <dt className="cx-faint text-[13px] font-semibold">Who does it</dt>
                        <dd>{c.ai}</dd>
                      </div>
                      <div>
                        <dt className="cx-faint text-[13px] font-semibold">What it does each day</dt>
                        <dd>{c.day_to_day}</dd>
                      </div>
                      <div>
                        <dt className="cx-faint text-[13px] font-semibold">What is different for you</dt>
                        <dd>{c.difference}</dd>
                      </div>
                    </dl>
                  </li>
                ))}
              </ol>
            </section>

            <section className="mt-14">
              <a className="cx-btn cx-btn--blue" href={mailto(data.email, data.book_subject)}>
                Book a call
              </a>
              <p className="cx-muted mt-3 text-[15px]">It opens an email to {data.email}.</p>
            </section>

            <footer className="mt-16 border-t border-[var(--cx-line)] pt-6 text-[14px] leading-relaxed">
              <p className="cx-muted">
                {data.sources_note} This page was made only from public information
                {data.sources.length ? ': ' : '.'}
                {data.sources.map((s, i) => (
                  <span key={s}>
                    {i ? ', ' : ''}
                    <a className="underline" href={s} target="_blank" rel="noopener noreferrer nofollow">
                      {host(s)}
                    </a>
                  </span>
                ))}
                {data.sources.length ? '.' : ''}
              </p>
              <p className="cx-faint mt-3">
                Not useful?{' '}
                <a className="underline" href={mailto(data.email, data.remove_subject)}>
                  Ask us to remove this page
                </a>
                .
              </p>
            </footer>
          </article>
        )}
      </main>
    </div>
  );
}
