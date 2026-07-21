import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  getRequest,
  updateRequest,
  generateAction,
  getWhatsAppMessage,
} from '../api/admin';
import type { RequestDetail } from '../types/request';
import RequestStatusBadge from '../components/RequestStatusBadge';
import MarkdownViewer from '../components/MarkdownViewer';
import CopyButton from '../components/CopyButton';
import VisualDemoPreview from '../components/VisualDemoPreview';
import type { VisualDemo } from '../types/request';

const STATUS_OPTIONS = ['new', 'reviewing', 'proposal sent', 'accepted', 'in progress', 'delivered', 'lost'];

const GENERATE_ACTIONS = [
  { key: 'analyze-screenshot', label: 'Generate Analysis' },
  { key: 'generate-blueprint', label: 'Regenerate Blueprint' },
  { key: 'generate-visual-demo', label: 'Generate Visual Demo' },
  { key: 'generate-technical-plan', label: 'Generate Technical Plan' },
  { key: 'generate-proposal', label: 'Generate Proposal (admin)' },
  { key: 'generate-build-plans', label: 'Generate Build Plans' },
  { key: 'generate-full', label: 'Generate Full Pipeline' },
];

export default function AdminRequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [request, setRequest] = useState<RequestDetail | null>(null);
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState('');
  const [proposal, setProposal] = useState('');
  const [generating, setGenerating] = useState('');
  const [waMessage, setWaMessage] = useState('');

  const load = async () => {
    if (!id) return;
    try {
      const data = await getRequest(Number(id));
      setRequest(data);
      setNotes(data.admin_notes || '');
      setStatus(data.status);
      setProposal(data.proposal_draft || '');
      const wa = await getWhatsAppMessage(Number(id));
      setWaMessage(wa.message);
    } catch {
      navigate('/admin/login');
    }
  };

  useEffect(() => {
    if (!sessionStorage.getItem('admin_password')) {
      navigate('/admin/login');
      return;
    }
    load();
  }, [id, navigate]);

  const handleSave = async () => {
    if (!id) return;
    await updateRequest(Number(id), { status, admin_notes: notes, proposal_draft: proposal });
    load();
  };

  const handleGenerate = async (action: string) => {
    if (!id) return;
    setGenerating(action);
    try {
      await generateAction(Number(id), action);
      await load();
    } finally {
      setGenerating('');
    }
  };

  if (!request) return <p className="text-center py-8">Loading...</p>;

  let visualDemo: VisualDemo | null = null;
  if (request.visual_demo_json) {
    try {
      visualDemo = JSON.parse(request.visual_demo_json);
    } catch { /* ignore */ }
  }

  return (
    <div>
      <Link to="/admin" className="text-accent text-sm hover:underline mb-4 inline-block">&larr; Back to requests</Link>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{request.business_name}</h1>
          <p className="text-slate-500">Request #{request.id}</p>
        </div>
        <RequestStatusBadge status={request.status} />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="card p-6">
            <h2 className="font-bold mb-4">Submitted Information</h2>
            <dl className="grid sm:grid-cols-2 gap-3 text-sm">
              {[
                ['Industry', request.industry], ['Email', request.email], ['WhatsApp', request.whatsapp],
                ['Project scope', request.budget_range], ['Timeline', request.timeline], ['Needs AI', request.needs_ai],
                ['Reference URL', request.reference_url],
              ].map(([label, value]) => (
                <div key={label as string}>
                  <dt className="text-slate-500">{label}</dt>
                  <dd className="font-medium">{value || '—'}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-4 space-y-3 text-sm">
              <div><span className="text-slate-500">Description:</span> {request.business_description}</div>
              <div><span className="text-slate-500">Problem:</span> {request.main_problem || '—'}</div>
              <div><span className="text-slate-500">What they like:</span> {request.what_you_like || '—'}</div>
              <div><span className="text-slate-500">Desired outcome:</span> {request.desired_outcome || '—'}</div>
            </div>
          </div>

          {request.screenshot_analysis && (
            <div className="card p-6">
              <h2 className="font-bold mb-4">Screenshot Analysis</h2>
              <MarkdownViewer content={request.screenshot_analysis} />
            </div>
          )}

          {request.mvp_blueprint && (
            <div className="card p-6">
              <h2 className="font-bold mb-4">MVP Blueprint</h2>
              <MarkdownViewer content={request.mvp_blueprint} />
            </div>
          )}

          {visualDemo && (
            <div className="card p-6">
              <h2 className="font-bold mb-4">Visual Demo Preview</h2>
              <VisualDemoPreview demo={visualDemo} />
            </div>
          )}

          {request.technical_plan && (
            <div className="card p-6">
              <h2 className="font-bold mb-4">Technical Plan</h2>
              <MarkdownViewer content={request.technical_plan} />
            </div>
          )}

          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold">Proposal Draft</h2>
              <CopyButton text={proposal} label="Copy Proposal" />
            </div>
            <textarea
              value={proposal}
              onChange={(e) => setProposal(e.target.value)}
              rows={12}
              className="w-full px-4 py-3 rounded-xl border border-slate-200 text-sm font-mono"
            />
          </div>
        </div>

        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="font-bold mb-4">Actions</h2>
            <div className="space-y-2">
              {GENERATE_ACTIONS.map((a) => (
                <button
                  key={a.key}
                  onClick={() => handleGenerate(a.key)}
                  disabled={!!generating}
                  className="w-full px-4 py-2 text-sm font-medium rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-50 text-left"
                >
                  {generating === a.key ? 'Generating...' : a.label}
                </button>
              ))}
            </div>
          </div>

          <div className="card p-6">
            <h2 className="font-bold mb-4">Status & Notes</h2>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full px-4 py-2 rounded-lg border border-slate-200 mb-3 text-sm"
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s} className="capitalize">{s}</option>
              ))}
            </select>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              placeholder="Admin notes..."
              className="w-full px-4 py-3 rounded-xl border border-slate-200 text-sm mb-3"
            />
            <button onClick={handleSave} className="gradient-btn w-full text-sm py-2">
              Save Notes & Status
            </button>
          </div>

          <div className="card p-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-bold text-sm">WhatsApp Reply</h2>
              <CopyButton text={waMessage} label="Copy WhatsApp Reply" />
            </div>
            <p className="text-sm text-slate-600 whitespace-pre-line">{waMessage}</p>
          </div>

          {request.build_requested && (
            <div className="card p-4 bg-green-50 border-green-200">
              <p className="text-green-700 font-semibold text-sm">Build requested!</p>
              <p className="text-green-600 text-xs">
                {request.build_requested_at && new Date(request.build_requested_at).toLocaleString()}
              </p>
            </div>
          )}

          <div className="card p-6 text-sm space-y-2">
            <div><span className="text-slate-500">Fit score:</span> <strong>{request.business_fit_score ?? '—'}</strong></div>
            <div><span className="text-slate-500">Concept:</span> <strong>{request.concept_name || '—'}</strong></div>
            <Link to={`/result/${request.id}`} target="_blank" className="text-accent hover:underline block mt-2">
              View public preview &rarr;
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
