import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { whatsappUrl } from '../api/client';
import type { BuildRequestContact } from '../types/buildRequest';
import {
  BUILD_ADDONS,
  BUILD_PLANS,
  addonAvailable,
  addonIncluded,
  estimateFromUsd,
  formatFromUsd,
  summarizeSelection,
  type BuildPlan,
} from '../data/buildPlans';

interface Props {
  requestId: number;
  conceptName?: string | null;
  businessName?: string;
  onRequestBuild: (contact: BuildRequestContact) => Promise<void>;
  buildRequested?: boolean;
  demoView?: boolean;
}

type Step = 'plans' | 'contact';

export default function BuildRequestCTA({
  requestId,
  conceptName,
  businessName,
  onRequestBuild,
  buildRequested,
  demoView = false,
}: Props) {
  const [step, setStep] = useState<Step>('plans');
  const [planId, setPlanId] = useState<BuildPlan['id']>('growth');
  const [addonIds, setAddonIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [requested, setRequested] = useState(buildRequested);
  const [error, setError] = useState('');
  const [contact, setContact] = useState<BuildRequestContact>({
    contact_name: '',
    email: '',
    whatsapp: '',
    notes: '',
  });

  const plan = BUILD_PLANS.find((p) => p.id === planId) || BUILD_PLANS[1];
  const estimate = useMemo(() => estimateFromUsd(planId, addonIds), [planId, addonIds]);

  const toggleAddon = (id: string) => {
    setAddonIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const selectPlan = (id: BuildPlan['id']) => {
    setPlanId(id);
    // Drop add-ons already included in the new plan
    setAddonIds((prev) =>
      prev.filter((aid) => {
        const addon = BUILD_ADDONS.find((a) => a.id === aid);
        return addon ? addonAvailable(addon, id) : false;
      }),
    );
  };

  const selectionSummary = summarizeSelection(planId, addonIds);

  const waMessage = demoView
    ? `Hi, I saw the "${conceptName || 'demo'}" example and want something similar.\n\n${selectionSummary}`
    : `Hi, I reviewed my preview (Request #${requestId}) for ${businessName || 'my business'} — concept "${conceptName || 'MVP'}".\n\nI'd like to move forward:\n${selectionSummary}\n\nPlease confirm the exact quote.`;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!contact.contact_name.trim() || !contact.email.trim()) {
      setError('Please enter your name and email so our team can reach you.');
      return;
    }
    setLoading(true);
    try {
      const userNotes = contact.notes?.trim();
      const notes = [selectionSummary, userNotes ? `Customer notes: ${userNotes}` : '']
        .filter(Boolean)
        .join('\n\n');
      await onRequestBuild({
        contact_name: contact.contact_name.trim(),
        email: contact.email.trim(),
        whatsapp: contact.whatsapp?.trim() || undefined,
        notes,
        package_id: planId,
        addon_ids: addonIds.filter((id) => {
          const a = BUILD_ADDONS.find((x) => x.id === id);
          return a ? addonAvailable(a, planId) : false;
        }),
        estimate_from_usd: estimate ?? undefined,
      });
      setRequested(true);
    } catch {
      setError('Could not submit your request. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (requested) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-8 text-center">
        <p className="text-emerald-800 font-semibold text-lg mb-2">Build request received</p>
        <p className="text-emerald-700/80 text-sm mb-3">
          You chose <span className="font-semibold">{plan.name}</span>
          {estimate != null ? ` · ${formatFromUsd(estimate)}` : ' · custom quote'}.
          Our team will confirm the exact scope and price.
        </p>
        <a
          href={whatsappUrl(waMessage)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex text-sm font-semibold text-emerald-800 underline underline-offset-2"
        >
          Continue on WhatsApp
        </a>
      </div>
    );
  }

  return (
    <section
      id="build-plans"
      className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-slate-50 via-white to-teal-50/40 pointer-events-none" />
      <div className="relative z-10 p-6 sm:p-8 lg:p-10">
        <div className="max-w-2xl">
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-teal-700">
            Next step
          </p>
          <h3 className="mt-2 text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            {demoView ? 'Want something like this built?' : 'Love this preview? Choose how we build it.'}
          </h3>
          <p className="mt-2 text-sm sm:text-base text-slate-600 leading-relaxed">
            Pick a package, add optional extras, then send your details. Prices are soft “from”
            floors — we confirm the exact quote before work starts. No checkout online.
          </p>
        </div>

        {step === 'plans' ? (
          <>
            <div className="mt-8 grid gap-4 lg:grid-cols-3">
              {BUILD_PLANS.map((p) => {
                const selected = planId === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => selectPlan(p.id)}
                    className={`text-left rounded-2xl border p-5 transition duration-200 ${
                      selected
                        ? 'border-teal-600 bg-teal-50/60 ring-2 ring-teal-600/25 shadow-md'
                        : p.highlight
                          ? 'border-slate-300 bg-slate-50/80 hover:border-teal-500/50'
                          : 'border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        {p.badge ? (
                          <span className="inline-block text-[10px] font-bold uppercase tracking-wide text-white bg-slate-900 px-2 py-0.5 rounded-full mb-2">
                            {p.badge}
                          </span>
                        ) : null}
                        <h4 className="font-bold text-lg text-slate-900">{p.name}</h4>
                        <p className="mt-1 text-sm text-slate-500 leading-snug">{p.tagline}</p>
                      </div>
                      <span
                        className={`mt-1 h-5 w-5 shrink-0 rounded-full border-2 ${
                          selected ? 'border-teal-600 bg-teal-600' : 'border-slate-300'
                        }`}
                        aria-hidden
                      />
                    </div>
                    <p className="mt-4 text-xl font-bold text-slate-900">
                      {formatFromUsd(p.fromUsd)}
                      {p.fromUsd != null ? (
                        <span className="text-xs font-medium text-slate-500 ml-1">USD</span>
                      ) : null}
                    </p>
                    <p className="mt-1 text-xs font-medium text-slate-500">{p.timeline}</p>
                    <p className="mt-3 text-xs text-slate-500 italic">{p.bestFor}</p>
                    <ul className="mt-4 space-y-2">
                      {p.includes.map((line) => (
                        <li key={line} className="flex gap-2 text-sm text-slate-700 leading-snug">
                          <span className="mt-0.5 text-teal-600 shrink-0" aria-hidden>
                            ✓
                          </span>
                          <span>{line}</span>
                        </li>
                      ))}
                    </ul>
                  </button>
                );
              })}
            </div>

            <div className="mt-10">
              <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
                <div>
                  <h4 className="font-bold text-slate-900">Add-ons</h4>
                  <p className="text-sm text-slate-500">
                    Optional extras that raise the soft “from” estimate. Growth already includes some.
                  </p>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {BUILD_ADDONS.map((addon) => {
                  const included = addonIncluded(addon, planId);
                  const available = addonAvailable(addon, planId);
                  const on = included || addonIds.includes(addon.id);
                  return (
                    <button
                      key={addon.id}
                      type="button"
                      disabled={included || !available}
                      onClick={() => toggleAddon(addon.id)}
                      className={`text-left rounded-xl border px-4 py-3.5 transition ${
                        included
                          ? 'border-teal-200 bg-teal-50/50 cursor-default'
                          : on
                            ? 'border-teal-600 bg-teal-50/40 ring-1 ring-teal-600/20'
                            : 'border-slate-200 bg-white hover:border-slate-300'
                      } ${!available && !included ? 'opacity-40' : ''}`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-slate-900 text-sm">{addon.name}</p>
                          <p className="mt-0.5 text-xs text-slate-500 leading-relaxed">
                            {addon.description}
                          </p>
                        </div>
                        <div className="text-right shrink-0">
                          {included ? (
                            <span className="text-[10px] font-bold uppercase tracking-wide text-teal-700">
                              Included
                            </span>
                          ) : (
                            <span className="text-sm font-bold text-slate-900">
                              +${addon.fromUsd.toLocaleString('en-US')}
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 px-5 py-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Soft estimate · {plan.name}
                </p>
                <p className="text-2xl font-bold text-slate-900 mt-0.5">
                  {formatFromUsd(estimate)}
                  {estimate != null ? (
                    <span className="text-sm font-medium text-slate-500 ml-1.5">USD</span>
                  ) : null}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Not a final quote — we lock price after a short scope confirm.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-2.5">
                <button
                  type="button"
                  onClick={() => setStep('contact')}
                  className="gradient-btn whitespace-nowrap"
                >
                  Continue with {plan.name}
                </button>
                <a
                  href={whatsappUrl(waMessage)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-5 py-3 rounded-xl border-2 border-slate-200 text-slate-700 font-semibold text-center hover:bg-white transition-colors text-sm whitespace-nowrap"
                >
                  WhatsApp this plan
                </a>
              </div>
            </div>
          </>
        ) : (
          <form onSubmit={handleSubmit} className="mt-8 max-w-lg space-y-4">
            <button
              type="button"
              onClick={() => setStep('plans')}
              className="text-sm font-medium text-teal-700 hover:underline"
            >
              ← Change package or add-ons
            </button>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 whitespace-pre-line">
              {selectionSummary}
            </div>
            <p className="text-xs font-semibold text-teal-700 uppercase tracking-wide">
              Contact information
            </p>
            <div className="grid sm:grid-cols-2 gap-3">
              <label className="block sm:col-span-2">
                <span className="text-xs font-medium text-slate-600 mb-1 block">Your name *</span>
                <input
                  type="text"
                  required
                  value={contact.contact_name}
                  onChange={(e) => setContact((c) => ({ ...c, contact_name: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                  placeholder="Your name"
                />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-600 mb-1 block">Email *</span>
                <input
                  type="email"
                  required
                  value={contact.email}
                  onChange={(e) => setContact((c) => ({ ...c, email: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                  placeholder="you@business.com"
                />
              </label>
              <label className="block">
                <span className="text-xs font-medium text-slate-600 mb-1 block">WhatsApp</span>
                <input
                  type="tel"
                  value={contact.whatsapp}
                  onChange={(e) => setContact((c) => ({ ...c, whatsapp: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                  placeholder="+961..."
                />
              </label>
              <label className="block sm:col-span-2">
                <span className="text-xs font-medium text-slate-600 mb-1 block">Notes (optional)</span>
                <textarea
                  rows={2}
                  value={contact.notes}
                  onChange={(e) => setContact((c) => ({ ...c, notes: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100 resize-none"
                  placeholder="Must-have date, must-have feature, budget ceiling…"
                />
              </label>
            </div>
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            <div className="flex flex-col sm:flex-row gap-3 pt-1">
              <button type="submit" disabled={loading} className="gradient-btn disabled:opacity-50">
                {loading ? 'Submitting…' : 'Submit build request'}
              </button>
              <a
                href={whatsappUrl(waMessage)}
                target="_blank"
                rel="noopener noreferrer"
                className="px-6 py-3 rounded-xl border-2 border-slate-200 text-slate-700 font-semibold text-center hover:bg-slate-50 transition-colors text-sm"
              >
                Or WhatsApp instead
              </a>
            </div>
          </form>
        )}

        {demoView && step === 'plans' ? (
          <p className="text-xs text-slate-500 mt-6">
            This is an example demo.{' '}
            <Link to="/submit" className="text-teal-700 font-medium hover:underline">
              Create your own preview
            </Link>{' '}
            for a package tailored to your business.
          </p>
        ) : null}
      </div>
    </section>
  );
}
