import { useState } from 'react';
import { Link } from 'react-router-dom';
import { consultingEmailUrl } from '../api/client';
import Rise from '../film/Rise';
import Shot from '../film/Shot';
import { COMPANY } from '../data/company';
import { PRICE_LINE } from '../data/offer';
import { usePageMeta } from '../utils/pageMeta';

const TOPICS = ['A consultation', 'A system build', 'Private AI', 'Something else'] as const;

/**
 * The firm has no contact backend: the form writes the email for the visitor
 * and opens it in their own email app, so nothing is sent that they did not
 * see. The address is also shown in full for anyone without an email app.
 */
export default function ContactPage() {
  usePageMeta('Contact', `Write to ${COMPANY.name} about a consultation, a system build or private AI.`);
  const [name, setName] = useState('');
  const [company, setCompany] = useState('');
  const [topic, setTopic] = useState<string>(TOPICS[0]);
  const [message, setMessage] = useState('');

  const send = () => {
    const lines = [message.trim(), '', `Name: ${name.trim()}`];
    if (company.trim()) lines.push(`Business: ${company.trim()}`);
    const body = lines.join('\n');
    window.location.href = consultingEmailUrl(`${topic}${company.trim() ? `: ${company.trim()}` : ''}`, body);
  };

  return (
    <>
      <Shot title="Write to us" first wide>
        <p className="film-mark">Contact</p>
        <Rise as="h1" className="film-h2">
          Write to us about *the decision in front of you.*
        </Rise>
        <p className="film-body">
          Tell us what you are trying to work out, or what you would like built. If you already know the question, you can
          start a consultation straight away.
        </p>
        <form
          className="film-form"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <div className="film-field">
            <label htmlFor="c-name">Your name</label>
            <input id="c-name" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="film-field">
            <label htmlFor="c-company">Business</label>
            <input id="c-company" autoComplete="organization" value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>
          <div className="film-field">
            <label htmlFor="c-topic">What it concerns</label>
            <select id="c-topic" value={topic} onChange={(e) => setTopic(e.target.value)}>
              {TOPICS.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </div>
          <div className="film-field">
            <label htmlFor="c-message">Message</label>
            <textarea id="c-message" rows={4} required value={message} onChange={(e) => setMessage(e.target.value)} />
            <small>Pressing the button opens this message in your email app, addressed to {COMPANY.email}.</small>
          </div>
          <div className="film-actions">
            <button type="submit" className="film-pill">
              Write the email
            </button>
          </div>
        </form>
        <dl className="film-facts">
          <div>
            <dt>Email</dt>
            <dd>
              <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a>
            </dd>
          </div>
          <div>
            <dt>Company</dt>
            <dd>{COMPANY.name}</dd>
          </div>
          <div>
            <dt>Registered</dt>
            <dd>Dubai, United Arab Emirates</dd>
          </div>
        </dl>
        <p className="film-body">
          <b>Ready to start?</b> A consultation begins with your question, and you do not need to write to us first.{' '}
          {PRICE_LINE}
        </p>
        <div className="film-actions">
          <Link to="/demo" className="film-pill film-pill--ghost">
            Start a consultation
          </Link>
        </div>
      </Shot>
    </>
  );
}
