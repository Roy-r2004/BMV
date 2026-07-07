import { useState } from 'react';
import { Link } from 'react-router-dom';
import { whatsappUrl } from '../api/client';
import type { BuildRequestContact } from '../types/buildRequest';

interface Props {
  requestId: number;
  conceptName?: string | null;
  businessName?: string;
  onRequestBuild: (contact: BuildRequestContact) => Promise<void>;
  buildRequested?: boolean;
  demoView?: boolean;
}

export default function BuildRequestCTA({
  requestId,
  conceptName,
  businessName,
  onRequestBuild,
  buildRequested,
  demoView = false,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [requested, setRequested] = useState(buildRequested);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState('');
  const [contact, setContact] = useState<BuildRequestContact>({
    contact_name: '',
    email: '',
    whatsapp: '',
    notes: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!contact.contact_name.trim() || !contact.email.trim()) {
      setError('Please enter your name and email so our team can reach you.');
      return;
    }

    setLoading(true);
    try {
      await onRequestBuild({
        contact_name: contact.contact_name.trim(),
        email: contact.email.trim(),
        whatsapp: contact.whatsapp?.trim() || undefined,
        notes: contact.notes?.trim() || undefined,
      });
      setRequested(true);
      setShowForm(false);
    } catch {
      setError('Could not submit your request. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const waMessage = demoView
    ? `Hi, I saw the "${conceptName || 'demo'}" example on your site and want something similar built for my business.`
    : `Hi, I just reviewed my custom MVP preview (Request #${requestId}). I'd like to discuss building "${conceptName || 'my custom MVP'}" for ${businessName || 'my business'}.`;

  if (requested) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-8 text-center">
        <p className="text-emerald-800 font-semibold text-lg mb-2">Build request received!</p>
        <p className="text-emerald-700/80 text-sm">Our team will reach out using the contact details you provided.</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 relative overflow-hidden shadow-sm">
      <div className="absolute inset-0 bg-gradient-to-br from-indigo-50/80 via-transparent to-cyan-50/60 pointer-events-none" />
      <div className="relative z-10">
        <h3 className="text-xl sm:text-2xl font-bold mb-2 text-slate-900">
          {demoView ? 'Want something like this built for you?' : 'Want this built for your business?'}
        </h3>
        <p className="text-slate-600 mb-5 max-w-xl text-sm leading-relaxed">
          {demoView
            ? 'This is an example demo. Request a build and share your contact details — our team will follow up to scope your own version.'
            : 'When you\'re happy with your preview, request a build. We\'ll need your contact details so our team can follow up.'}
        </p>

        {!showForm ? (
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              type="button"
              onClick={() => setShowForm(true)}
              className="gradient-btn"
            >
              Request our team to build this
            </button>
            <a
              href={whatsappUrl(waMessage)}
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3 rounded-xl border-2 border-slate-200 text-slate-700 font-semibold text-center hover:bg-slate-50 transition-colors text-sm"
            >
              Discuss on WhatsApp
            </a>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 max-w-lg">
            <p className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">
              Contact information required
            </p>
            <div className="grid sm:grid-cols-2 gap-3">
              <label className="block sm:col-span-2">
                <span className="text-xs font-medium text-slate-600 mb-1 block">Your name *</span>
                <input
                  type="text"
                  required
                  value={contact.contact_name}
                  onChange={(e) => setContact((c) => ({ ...c, contact_name: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                  placeholder="Roy Mansour"
                />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-600 mb-1 block">Email *</span>
                <input
                  type="email"
                  required
                  value={contact.email}
                  onChange={(e) => setContact((c) => ({ ...c, email: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                  placeholder="you@business.com"
                />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-600 mb-1 block">WhatsApp</span>
                <input
                  type="tel"
                  value={contact.whatsapp}
                  onChange={(e) => setContact((c) => ({ ...c, whatsapp: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                  placeholder="+961..."
                />
              </label>
              <label className="block sm:col-span-2">
                <span className="text-xs font-medium text-slate-600 mb-1 block">Notes (optional)</span>
                <textarea
                  rows={2}
                  value={contact.notes}
                  onChange={(e) => setContact((c) => ({ ...c, notes: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 resize-none"
                  placeholder="Timeline, budget, or anything else we should know"
                />
              </label>
            </div>

            {error && <p className="text-sm text-red-600">{error}</p>}

            <div className="flex flex-col sm:flex-row gap-3 pt-1">
              <button type="submit" disabled={loading} className="gradient-btn disabled:opacity-50">
                {loading ? 'Submitting…' : 'Submit build request'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="px-6 py-3 rounded-xl text-sm font-medium text-slate-600 hover:bg-slate-100 transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {demoView && !showForm && (
          <p className="text-xs text-slate-500 mt-4">
            Want to refine with AI first?{' '}
            <Link to="/submit" className="text-indigo-600 font-medium hover:underline">
              Create your own version
            </Link>
            {' '}— the refine chatbot is included there.
          </p>
        )}
      </div>
    </div>
  );
}
