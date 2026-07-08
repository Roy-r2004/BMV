import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { createRequest } from '../../api/requests';
import { markOwnRequest } from '../../utils/ownRequest';

interface Props {
  industry: string;
  solutionId: string;
  solutionName: string;
  onClose: () => void;
}

const inputClass =
  'submit-input w-full px-4 py-3.5 rounded-xl border border-slate-200/90 bg-white/95 text-navy placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 outline-none transition-all text-[15px] shadow-sm';

export default function SolutionRequestForm({ industry, solutionId, solutionName, onClose }: Props) {
  const navigate = useNavigate();
  const [businessName, setBusinessName] = useState('');
  const [businessDetails, setBusinessDetails] = useState('');
  const [email, setEmail] = useState('');
  const [whatsapp, setWhatsapp] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [fieldError, setFieldError] = useState('');

  const validate = (): boolean => {
    if (!businessName.trim()) {
      setFieldError('Please enter your company name.');
      return false;
    }
    if (!businessDetails.trim()) {
      setFieldError('Tell us a bit about your company — location, services, team size, anything helpful.');
      return false;
    }
    if (!email.trim()) {
      setFieldError('We need your email to get back to you.');
      return false;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setFieldError('Please enter a valid email address.');
      return false;
    }
    setFieldError('');
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    setError('');

    const fd = new FormData();
    fd.set('business_name', businessName.trim());
    fd.set('business_description', businessDetails.trim());
    fd.set('email', email.trim());
    fd.set('industry', industry);
    fd.set('project_type', 'new');
    fd.set('needs_ai', 'yes');
    fd.set('reference_url', `https://buildmyversion.com/solutions/${solutionId}`);
    fd.set('what_you_like', `Selected the ${solutionName} demo on BuildMyVersion Solutions — wants this software customized for their business.`);
    fd.set('main_problem', `Wants to deploy the ${solutionName} ready-made platform for their business.`);
    fd.set('desired_outcome', `Launch ${solutionName} software branded and configured for ${businessName.trim()}.`);
    if (whatsapp.trim()) fd.set('whatsapp', whatsapp.trim());

    try {
      const result = await createRequest(fd);
      markOwnRequest(result.id);
      onClose();
      navigate(`/result/${result.id}`);
    } catch {
      setError('Something went wrong. Please try again.');
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="solution-request-form">
      <div className="solution-request-form__context">
        <span className="solution-request-form__check">✓</span>
        <p>
          You&apos;ve seen the <strong>{solutionName}</strong> demo — this request is to get that software for your business.
          No need to describe the product again.
        </p>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 p-3.5 rounded-xl text-sm">
          {error}
        </div>
      )}
      {fieldError && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-4 bg-amber-50 border border-amber-200 text-amber-800 p-3.5 rounded-xl text-sm"
        >
          {fieldError}
        </motion.div>
      )}

      <div className="solution-request-form__fields">
        <label className="solution-request-form__label">
          Company name <span className="text-cyan-500">*</span>
          <input
            value={businessName}
            onChange={(e) => { setBusinessName(e.target.value); setFieldError(''); }}
            className={inputClass}
            placeholder="e.g. Harbor Wellness Clinic"
            autoFocus
            disabled={loading}
          />
        </label>

        <label className="solution-request-form__label">
          About your company <span className="text-cyan-500">*</span>
          <textarea
            value={businessDetails}
            onChange={(e) => { setBusinessDetails(e.target.value); setFieldError(''); }}
            rows={3}
            className={inputClass}
            placeholder="What you do, where you're based, team size, anything we should know to customize your version..."
            disabled={loading}
          />
        </label>

        <div className="solution-request-form__row">
          <label className="solution-request-form__label">
            Email <span className="text-cyan-500">*</span>
            <input
              type="email"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setFieldError(''); }}
              className={inputClass}
              placeholder="you@company.com"
              disabled={loading}
            />
          </label>

          <label className="solution-request-form__label">
            WhatsApp / phone
            <span className="solution-request-form__optional">optional</span>
            <input
              value={whatsapp}
              onChange={(e) => setWhatsapp(e.target.value)}
              className={inputClass}
              placeholder="+961..."
              disabled={loading}
            />
          </label>
        </div>
      </div>

      <p className="solution-request-form__note">
        We&apos;ll reach out to customize branding, settings, and integrations — then launch your version.
      </p>

      <div className="solution-request-form__actions">
        <button type="button" className="solution-request-form__cancel" onClick={onClose} disabled={loading}>
          Cancel
        </button>
        <button type="submit" className="gradient-btn text-sm px-8 py-3 disabled:opacity-50" disabled={loading}>
          {loading ? 'Sending…' : 'Request this software'}
        </button>
      </div>
    </form>
  );
}
