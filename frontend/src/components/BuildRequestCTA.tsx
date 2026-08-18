import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { consultingEmailUrl } from '../api/client';
import type { BuildRequestContact } from '../types/buildRequest';
import type { BuildPlansPayload } from '../data/buildPlans';
import {
  addonAvailable,
  addonIncluded,
  normalizeBuildPlansPayload,
  summarizeSelection,
  type BuildAddonContext,
  type BuildPlan,
} from '../data/buildPlans';

interface Props {
  requestId: number;
  conceptName?: string | null;
  businessName?: string;
  industry?: string | null;
  mainProblem?: string | null;
  desiredOutcome?: string | null;
  previewFeatures?: string[];
  aiFeatures?: BuildAddonContext['aiFeatures'];
  roleLabels?: string[];
  /** AI-written plans from the pipeline (no prices). */
  buildPlans?: BuildPlansPayload | null;
  onRequestBuild: (contact: BuildRequestContact) => Promise<void>;
  onRegeneratePlans?: () => Promise<void>;
  buildRequested?: boolean;
  demoView?: boolean;
}

type Step = 'plans' | 'contact';

export default function BuildRequestCTA({
  requestId,
  conceptName,
  businessName,
  industry,
  mainProblem,
  desiredOutcome,
  previewFeatures,
  aiFeatures,
  roleLabels,
  buildPlans,
  onRequestBuild,
  onRegeneratePlans,
  buildRequested,
  demoView = false,
}: Props) {
  const [step, setStep] = useState<Step>('plans');
  const [planId, setPlanId] = useState<BuildPlan['id']>('growth');
  const [addonIds, setAddonIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [regenLoading, setRegenLoading] = useState(false);
  const [requested, setRequested] = useState(buildRequested);
  const [error, setError] = useState('');
  const [contact, setContact] = useState<BuildRequestContact>({
    contact_name: '',
    email: '',
    whatsapp: '',
    notes: '',
  });

  const fallbackCtx = useMemo(
    () => ({
      businessName,
      conceptName,
      industry,
      mainProblem,
      desiredOutcome,
      previewFeatures,
      aiFeatures,
      roleLabels,
    }),
    [
      businessName,
      conceptName,
      industry,
      mainProblem,
      desiredOutcome,
      previewFeatures,
      aiFeatures,
      roleLabels,
    ],
  );

  const { plans, addons, recommendedPlanId } = useMemo(
    () => normalizeBuildPlansPayload(buildPlans, fallbackCtx),
    [buildPlans, fallbackCtx],
  );

  useEffect(() => {
    setPlanId(recommendedPlanId);
    setAddonIds([]);
  }, [recommendedPlanId, buildPlans]);

  const plan = plans.find((p) => p.id === planId) || plans[1];

  const toggleAddon = (id: string) => {
    setAddonIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const selectPlan = (id: BuildPlan['id']) => {
    setPlanId(id);
    setAddonIds((prev) =>
      prev.filter((aid) => {
        const addon = addons.find((a) => a.id === aid);
        return addon ? addonAvailable(addon, id) : false;
      }),
    );
  };

  const selectionSummary = summarizeSelection(planId, addonIds, addons, plans);

  const emailSubject = demoView
    ? `Build inquiry — ${conceptName || 'demo'}`
    : `Build request — ${businessName || 'my business'} (preview #${requestId})`;
  const emailBody = demoView
    ? `Hi,\n\nI saw the "${conceptName || 'demo'}" example and want something similar.\n\n${selectionSummary}\n`
    : `Hi,\n\nI reviewed my preview (Request #${requestId}) for ${businessName || 'my business'} — concept "${conceptName || 'MVP'}".\n\nI'd like to move forward:\n${selectionSummary}\n\nPlease send the exact quote.\n`;
  const emailHref = consultingEmailUrl(emailSubject, emailBody);

  const handleRegenerate = async () => {
    if (!onRegeneratePlans) return;
    setRegenLoading(true);
    setError('');
    try {
      await onRegeneratePlans();
    } catch {
      setError('Could not regenerate plans. Please try again.');
    } finally {
      setRegenLoading(false);
    }
  };

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
          const a = addons.find((x) => x.id === id);
          return a ? addonAvailable(a, planId) : false;
        }),
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
          You chose <span className="font-semibold">{plan.name}</span>. Our team will confirm
          scope and pricing with you.
        </p>
        <a
          href={emailHref}
          className="inline-flex text-sm font-semibold text-emerald-800 underline underline-offset-2"
        >
          Continue by email
        </a>
      </div>
    );
  }

  return (
    <section
      id="build-plans"
      className="relative scroll-mt-32 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-slate-50 via-white to-teal-50/40 pointer-events-none" />
      <div className="relative z-10 p-6 sm:p-8 lg:p-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-teal-700">
              Next step
            </p>
            <h3 className="mt-2 text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
              {demoView
                ? 'Want something like this built?'
                : 'Love this preview? Choose how we build it.'}
            </h3>
            <p className="mt-2 text-sm sm:text-base text-slate-600 leading-relaxed">
              Packages and add-ons are written from your live preview. No public prices — we quote
              after you choose and we confirm scope.
            </p>
          </div>
          {onRegeneratePlans && !demoView ? (
            <button
              type="button"
              onClick={handleRegenerate}
              disabled={regenLoading}
              className="shrink-0 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {regenLoading ? 'Regenerating…' : 'Regenerate for this preview'}
            </button>
          ) : null}
        </div>

        {step === 'plans' ? (
          <>
            <div className="mt-8 grid gap-4 lg:grid-cols-3">
              {plans.map((p) => {
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
                    <p className="mt-4 text-xs font-medium text-slate-500">{p.timeline}</p>
                    <p className="mt-3 text-xs text-slate-500 italic">{p.bestFor}</p>
                    <p className="mt-4 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">
                      What’s included
                    </p>
                    <ul className="mt-2 space-y-2">
                      {p.includes.map((line) => (
                        <li key={line} className="flex gap-2 text-sm text-slate-700 leading-snug">
                          <span className="mt-0.5 text-teal-600 shrink-0 font-bold" aria-hidden>
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

            <div className="mt-10 space-y-8">
              {(() => {
                const includedAddons = addons.filter((a) => addonIncluded(a, planId));
                const optionalAddons = addons.filter((a) => addonAvailable(a, planId));
                return (
                  <>
                    {includedAddons.length > 0 ? (
                      <div>
                        <div className="mb-3">
                          <h4 className="font-bold text-slate-900">Included in {plan.name}</h4>
                          <p className="text-sm text-slate-500">
                            Already in your package — written from this preview.
                          </p>
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2">
                          {includedAddons.map((addon) => (
                            <div
                              key={addon.id}
                              className="rounded-xl border border-teal-200 bg-teal-50/60 px-4 py-3.5"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="font-semibold text-slate-900 text-sm">{addon.name}</p>
                                  <p className="mt-0.5 text-xs text-slate-600 leading-relaxed">
                                    {addon.description}
                                  </p>
                                  {addon.whyForYou ? (
                                    <p className="mt-2 text-[11px] font-medium text-teal-800/80 leading-snug">
                                      Why for you: {addon.whyForYou}
                                    </p>
                                  ) : null}
                                </div>
                                <span className="shrink-0 rounded-full bg-teal-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                                  Included
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : planId === 'custom' ? (
                      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                        Custom / Scale includes everything we agree on a scope call — pick optional
                        upgrades below as a starting wishlist.
                      </div>
                    ) : null}

                    {optionalAddons.length > 0 ? (
                      <div>
                        <div className="mb-3">
                          <h4 className="font-bold text-slate-900">
                            Optional upgrades for {businessName || conceptName || 'this business'}
                          </h4>
                          <p className="text-sm text-slate-500">
                            Toggle extras you want on the quote — pricing confirmed with our team.
                          </p>
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2">
                          {optionalAddons.map((addon) => {
                            const on = addonIds.includes(addon.id);
                            return (
                              <button
                                key={addon.id}
                                type="button"
                                onClick={() => toggleAddon(addon.id)}
                                className={`text-left rounded-xl border px-4 py-3.5 transition ${
                                  on
                                    ? 'border-teal-600 bg-teal-50/40 ring-1 ring-teal-600/20'
                                    : 'border-slate-200 bg-white hover:border-slate-300'
                                }`}
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div>
                                    <p className="font-semibold text-slate-900 text-sm">{addon.name}</p>
                                    <p className="mt-0.5 text-xs text-slate-500 leading-relaxed">
                                      {addon.description}
                                    </p>
                                    {addon.whyForYou ? (
                                      <p className="mt-2 text-[11px] font-medium text-teal-800/80 leading-snug">
                                        Why for you: {addon.whyForYou}
                                      </p>
                                    ) : null}
                                  </div>
                                  <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400 shrink-0">
                                    {on ? 'Added' : 'Add'}
                                  </p>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                  </>
                );
              })()}
            </div>

            <div className="mt-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 px-5 py-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Selected · {plan.name}
                </p>
                <p className="text-sm text-slate-600 mt-1">
                  We’ll confirm exact scope and pricing after you reach out.
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
                  href={emailHref}
                  className="px-5 py-3 rounded-xl border-2 border-slate-200 text-slate-700 font-semibold text-center hover:bg-white transition-colors text-sm whitespace-nowrap"
                >
                  Email us this plan
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
                  placeholder="Must-have date, must-have feature…"
                />
              </label>
            </div>
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            <div className="flex flex-col sm:flex-row gap-3 pt-1">
              <button type="submit" disabled={loading} className="gradient-btn disabled:opacity-50">
                {loading ? 'Submitting…' : 'Submit build request'}
              </button>
              <a
                href={emailHref}
                className="px-6 py-3 rounded-xl border-2 border-slate-200 text-slate-700 font-semibold text-center hover:bg-slate-50 transition-colors text-sm"
              >
                Or email us instead
              </a>
            </div>
          </form>
        )}

        {error && step === 'plans' ? <p className="text-sm text-red-600 mt-4">{error}</p> : null}

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
