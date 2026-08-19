import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import { useAuth } from '../context/AuthContext';
import {
  fetchMyEngagements,
  studioResultPath,
  type StudioMineEntry,
} from '../api/consultant';

// The signed-in client's home for their runs. Every engagement lives at an
// unguessable slug only this account can open, so the list is the way back
// in — a bookmark that never goes stale.

function statusOf(m: StudioMineEntry): { label: string; tone: string } {
  if (m.is_generating)
    return { label: 'Generating…', tone: 'text-blue-700 bg-blue-50 border-blue-200' };
  if (m.status === 'failed')
    return { label: 'Needs attention', tone: 'text-amber-700 bg-amber-50 border-amber-200' };
  if (m.review_status === 'pending')
    return { label: 'In review', tone: 'text-violet-700 bg-violet-50 border-violet-200' };
  return { label: 'Ready', tone: 'text-emerald-700 bg-emerald-50 border-emerald-200' };
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function EngagementsPage() {
  const navigate = useNavigate();
  const { isAuthenticated, loading: authLoading } = useAuth();
  const [rows, setRows] = useState<StudioMineEntry[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (authLoading || !isAuthenticated) return;
    let cancelled = false;
    fetchMyEngagements()
      .then((list) => {
        if (!cancelled) setRows(list);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, isAuthenticated]);

  return (
    <div className="min-h-screen bg-white overflow-x-hidden">
      <SiteNav />
      <main className="pt-24 sm:pt-28 pb-20 min-h-[70vh]">
        <div className="container-max px-4 sm:px-6">
          <motion.header
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="mb-8 sm:mb-10"
          >
            <p className="text-blue-600 font-medium mb-2 tracking-[0.2em] uppercase text-xs">
              Private to your account
            </p>
            <h1 className="text-3xl sm:text-4xl font-bold text-navy">Your engagements</h1>
            <p className="text-slate-600 mt-3 max-w-2xl">
              Every engagement you commission lives here — private to this account, at an
              address only you can open.
            </p>
          </motion.header>

          {authLoading && null}

          {!authLoading && !isAuthenticated && (
            <div className="max-w-xl rounded-2xl border border-slate-200 bg-slate-50/60 p-8">
              <h2 className="text-xl font-bold text-navy mb-2">Sign in to see your engagements</h2>
              <p className="text-slate-600 mb-6">
                Engagements are private to the account that created them. Sign in and yours
                will be waiting.
              </p>
              <div className="flex flex-wrap gap-3">
                <Link
                  to="/login"
                  state={{ from: '/engagements' }}
                  className="inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-blue-500/25"
                >
                  Sign in
                </Link>
                <Link
                  to="/signup"
                  state={{ from: '/engagements' }}
                  className="inline-flex items-center justify-center rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-semibold text-slate-700 hover:border-blue-300 hover:bg-blue-50"
                >
                  Create an account
                </Link>
              </div>
            </div>
          )}

          {!authLoading && isAuthenticated && failed && (
            <p className="text-slate-600">
              Your engagements could not be loaded just now — refresh this page in a moment.
            </p>
          )}

          {!authLoading && isAuthenticated && !failed && rows && rows.length === 0 && (
            <div className="max-w-xl rounded-2xl border border-slate-200 bg-slate-50/60 p-8">
              <h2 className="text-xl font-bold text-navy mb-2">No engagements yet</h2>
              <p className="text-slate-600 mb-6">
                Commission your first one: a full consulting engagement for your business —
                the screens, the blueprint, the technical plan and the operations manual.
              </p>
              <Link
                to="/demo"
                className="inline-flex items-center justify-center rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-blue-500/25"
              >
                Start your engagement
              </Link>
            </div>
          )}

          {!authLoading && isAuthenticated && !failed && rows && rows.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {rows.map((m, i) => {
                const s = statusOf(m);
                const date = formatDate(m.created_at);
                return (
                  <motion.button
                    key={m.id}
                    type="button"
                    initial={{ opacity: 0, y: 14 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.35, delay: Math.min(i * 0.05, 0.3) }}
                    onClick={() => navigate(studioResultPath(m.public_id ?? m.id))}
                    className="group text-left rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:border-blue-300 hover:shadow-lg hover:shadow-blue-500/10"
                  >
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <span
                        className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${s.tone}`}
                      >
                        {s.label}
                      </span>
                      {date && <span className="text-xs text-slate-400 shrink-0">{date}</span>}
                    </div>
                    <h2 className="text-lg font-bold text-navy leading-snug group-hover:text-blue-700 transition-colors">
                      {m.concept_name || m.business_name}
                    </h2>
                    {m.concept_name && (
                      <p className="text-sm text-slate-500 mt-0.5">{m.business_name}</p>
                    )}
                    <p className="mt-4 text-sm font-medium text-blue-600">
                      Open engagement
                      <span aria-hidden="true" className="inline-block transition-transform group-hover:translate-x-0.5">
                        {' '}
                        →
                      </span>
                    </p>
                  </motion.button>
                );
              })}
            </div>
          )}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
