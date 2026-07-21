import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { markOwnRequest } from '../utils/ownRequest';
import { AnimatePresence, motion } from 'framer-motion';
import { createRequest } from '../api/requests';
import FileUpload from './FileUpload';
import FormProgress, { type StepMeta } from './form/FormProgress';
import OptionPills from './form/OptionPills';
import GeneratingOverlay from './form/GeneratingOverlay';
import {
  IconArrowLeft,
  IconArrowRight,
  IconBrain,
  IconClock,
  IconCoins,
  IconMinus,
  IconSend,
  IconShield,
  IconSparkles,
  STEP_ICONS,
} from './icons/SubmitIcons';

const STEPS: StepMeta[] = [
  { id: 'business', label: 'Business', subtitle: 'Tell us who you are' },
  { id: 'challenge', label: 'Challenge', subtitle: 'What you need solved' },
  { id: 'inspiration', label: 'Inspiration', subtitle: 'A tool you admire' },
  { id: 'project', label: 'Project', subtitle: 'Scope & timeline' },
  { id: 'contact', label: 'Contact', subtitle: 'Where to send your preview' },
];

const BUDGET_OPTIONS = ['Starter scope', 'Standard scope', 'Full build', 'Not sure yet'];
const TIMELINE_OPTIONS = ['ASAP (2–4 weeks)', '1–2 months', '2–3 months', 'Flexible'];
const AI_OPTIONS = ['Yes, definitely', 'Maybe, if it adds value', 'No, keep it simple'];

const AI_MAP: Record<string, string> = {
  'Yes, definitely': 'yes',
  'Maybe, if it adds value': 'maybe',
  'No, keep it simple': 'no',
};

const AI_REVERSE: Record<string, string> = {
  yes: 'Yes, definitely',
  maybe: 'Maybe, if it adds value',
  no: 'No, keep it simple',
};

const AI_ICONS = {
  'Yes, definitely': <IconSparkles className="w-4 h-4" />,
  'Maybe, if it adds value': <IconBrain className="w-4 h-4" />,
  'No, keep it simple': <IconMinus className="w-4 h-4" />,
};

const BUDGET_ICONS = {
  'Starter scope': <IconCoins className="w-4 h-4" />,
  'Standard scope': <IconCoins className="w-4 h-4" />,
  'Full build': <IconCoins className="w-4 h-4" />,
  'Not sure yet': <IconCoins className="w-4 h-4" />,
};

const TIMELINE_ICONS = {
  'ASAP (2–4 weeks)': <IconClock className="w-4 h-4" />,
  '1–2 months': <IconClock className="w-4 h-4" />,
  '2–3 months': <IconClock className="w-4 h-4" />,
  Flexible: <IconClock className="w-4 h-4" />,
};

const PROJECT_TYPES = [
  {
    id: 'new',
    label: 'Build from scratch',
    hint: 'I have an idea for a new product or tool',
    icon: (
      <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.75}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
      </svg>
    ),
  },
  {
    id: 'enhance',
    label: 'Improve existing',
    hint: 'I have a product and want to add a feature',
    icon: (
      <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.75}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
      </svg>
    ),
  },
  {
    id: 'automate',
    label: 'Automate a process',
    hint: 'I do something manually and want it automated',
    icon: (
      <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.75}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
      </svg>
    ),
  },
];

interface FormData {
  project_type: string;
  existing_product_url: string;
  business_name: string;
  industry: string;
  business_description: string;
  target_customers: string;
  main_problem: string;
  desired_outcome: string;
  reference_url: string;
  what_you_like: string;
  needs_ai: string;
  budget_range: string;
  timeline: string;
  email: string;
  whatsapp: string;
}

const INITIAL: FormData = {
  project_type: 'new',
  existing_product_url: '',
  business_name: '',
  industry: '',
  business_description: '',
  target_customers: '',
  main_problem: '',
  desired_outcome: '',
  reference_url: '',
  what_you_like: '',
  needs_ai: 'yes',
  budget_range: 'Starter scope',
  timeline: 'Flexible',
  email: '',
  whatsapp: '',
};

const easeOut = [0.22, 1, 0.36, 1] as const;

const slideVariants = {
  enter: (dir: number) => ({ opacity: 0, x: dir > 0 ? 16 : -16 }),
  center: { opacity: 1, x: 0 },
  exit: (dir: number) => ({ opacity: 0, x: dir > 0 ? -16 : 16 }),
};

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="submit-field">
      <label className="block text-sm font-semibold mb-2 text-navy">
        {label}
        {required && <span className="text-cyan-500 ml-0.5">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-500 mt-2 leading-relaxed">{hint}</p>}
    </div>
  );
}

const inputClass =
  'submit-input w-full px-4 py-3.5 rounded-xl border border-slate-200/90 bg-white text-navy placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/15 outline-none transition-colors text-base shadow-sm';

export interface SubmitWizardProps {
  variant?: 'page' | 'modal';
  defaultIndustry?: string;
  solutionId?: string;
  solutionName?: string;
  onClose?: () => void;
}

export default function SubmitWizard({
  variant = 'page',
  defaultIndustry,
  solutionId,
  solutionName,
}: SubmitWizardProps = {}) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(1);
  const [data, setData] = useState<FormData>(INITIAL);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [fieldError, setFieldError] = useState('');

  useEffect(() => {
    const industry = defaultIndustry || searchParams.get('industry');
    if (!industry && !solutionName) return;
    setData((d) => ({
      ...d,
      industry: d.industry || industry || '',
      needs_ai: d.needs_ai || 'yes',
      project_type: d.project_type || 'new',
      reference_url: d.reference_url || (solutionId ? `https://buildmyversion.com/solutions/${solutionId}` : ''),
      what_you_like:
        d.what_you_like
        || (solutionName
          ? `The ${solutionName} demo — AI automations, booking flow, and admin dashboard.`
          : ''),
      main_problem:
        d.main_problem
        || (solutionName
          ? `Interested in the ${solutionName} ready-made software from BuildMyVersion Solutions.`
          : ''),
    }));
  }, [searchParams, defaultIndustry, solutionName]);

  const update = (key: keyof FormData, value: string) => {
    setData((d) => ({ ...d, [key]: value }));
    setFieldError('');
  };

  const hasReference = Boolean(data.reference_url.trim() || file);

  const validateStep = (): boolean => {
    if (step === 0) {
      if (!data.business_name.trim()) {
        setFieldError('Please enter your business name.');
        return false;
      }
      if (!data.business_description.trim()) {
        setFieldError('Tell us a bit about what your business does.');
        return false;
      }
    }
    if (step === 2 && hasReference && !data.what_you_like.trim()) {
      setFieldError('Tell us what you liked about your reference — it helps us match the experience more accurately.');
      return false;
    }
    if (step === 4) {
      if (!data.email.trim()) {
        setFieldError('We need your email to send the preview.');
        return false;
      }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) {
        setFieldError('Please enter a valid email address.');
        return false;
      }
    }
    setFieldError('');
    return true;
  };

  const scrollWizardIntoView = () => {
    if (typeof window === 'undefined') return;
    if (window.matchMedia('(max-width: 767px)').matches) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const goNext = () => {
    if (!validateStep()) return;
    setDirection(1);
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
    scrollWizardIntoView();
  };

  const goBack = () => {
    setFieldError('');
    setDirection(-1);
    setStep((s) => Math.max(s - 1, 0));
    scrollWizardIntoView();
  };

  const handleSubmit = async () => {
    if (!validateStep()) return;
    setLoading(true);
    setError('');

    const fd = new FormData();
    fd.set('business_name', data.business_name);
    fd.set('business_description', data.business_description);
    fd.set('email', data.email);
    fd.set('project_type', data.project_type);
    if (data.existing_product_url) fd.set('existing_product_url', data.existing_product_url);
    if (data.industry) fd.set('industry', data.industry);
    if (data.target_customers) fd.set('target_customers', data.target_customers);
    if (data.main_problem) fd.set('main_problem', data.main_problem);
    if (data.reference_url) fd.set('reference_url', data.reference_url);
    else if (solutionId) fd.set('reference_url', `https://buildmyversion.com/solutions/${solutionId}`);
    if (data.what_you_like) fd.set('what_you_like', data.what_you_like);
    else if (solutionName) {
      fd.set('what_you_like', `The ${solutionName} demo — AI automations, booking flow, and admin dashboard.`);
    }
    if (data.desired_outcome) fd.set('desired_outcome', data.desired_outcome);
    if (data.needs_ai) fd.set('needs_ai', data.needs_ai);
    if (data.budget_range) fd.set('budget_range', data.budget_range);
    if (data.timeline) fd.set('timeline', data.timeline);
    if (data.whatsapp) fd.set('whatsapp', data.whatsapp);
    if (file) fd.set('reference_file', file);

    try {
      const result = await createRequest(fd);
      markOwnRequest(result.id);
      navigate(`/result/${result.id}`);
    } catch {
      setError('Something went wrong. Please try again.');
      setLoading(false);
    }
  };

  const isLast = step === STEPS.length - 1;
  const currentStep = STEPS[step];
  const StepIcon = () => STEP_ICONS[step];

  const keyHandlersRef = useRef({ loading, isLast, goNext, handleSubmit });
  keyHandlersRef.current = { loading, isLast, goNext, handleSubmit };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const h = keyHandlersRef.current;
      if (e.key !== 'Enter' || e.shiftKey || h.loading) return;
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'TEXTAREA') return;
      e.preventDefault();
      if (h.isLast) void h.handleSubmit();
      else h.goNext();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <>
      {loading && <GeneratingOverlay businessName={data.business_name} />}

      <div className="space-y-4 sm:space-y-6">
        <FormProgress steps={STEPS} current={step} />

        <div className={`submit-wizard-panel rounded-3xl bg-white border border-slate-200/80 shadow-lg shadow-slate-200/60 p-6 sm:p-8 lg:p-10 flex flex-col relative overflow-hidden ${variant === 'page' ? 'sm:min-h-[460px]' : 'min-h-0'}`}>

          <div className="mb-5 sm:mb-8 relative flex items-start gap-3 sm:gap-4">
            <div className="shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-xl sm:rounded-2xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white flex items-center justify-center shadow-md shadow-blue-500/25">
              <StepIcon />
            </div>
            <div className="min-w-0 pt-0.5">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-500/80 mb-0.5 sm:mb-1">
                {currentStep.label}
              </p>
              <h2 className="text-lg sm:text-2xl lg:text-[1.65rem] font-bold text-navy leading-tight">
                {currentStep.subtitle}
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 mt-1 sm:mt-1.5 leading-snug">{stepHint(step)}</p>
            </div>
          </div>

          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 p-3.5 rounded-xl text-sm relative">
              {error}
            </div>
          )}
          {fieldError && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-4 bg-amber-50 border border-amber-200 text-amber-800 p-3.5 rounded-xl text-sm relative"
            >
              {fieldError}
            </motion.div>
          )}

          <div className="flex-1 relative overflow-hidden">
            <AnimatePresence mode="wait" custom={direction}>
              <motion.div
                key={step}
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.28, ease: easeOut }}
                className="space-y-4 sm:space-y-5"
              >
                {step === 0 && (
                  <>
                    {/* Project type selector */}
                    <Field label="What are you looking to do?">
                      <div className="submit-project-types grid grid-cols-3 gap-3">
                        {PROJECT_TYPES.map((pt) => (
                          <button
                            key={pt.id}
                            type="button"
                            onClick={() => update('project_type', pt.id)}
                            className={`flex flex-col items-center gap-2 rounded-2xl border-2 p-4 text-center transition-colors duration-200 ${
                              data.project_type === pt.id
                                ? 'border-blue-500 bg-blue-50/80 text-blue-700 shadow-sm shadow-blue-200'
                                : 'border-slate-200 bg-white text-slate-600'
                            }`}
                          >
                            <span className={data.project_type === pt.id ? 'text-blue-600' : 'text-slate-400'}>
                              {pt.icon}
                            </span>
                            <span className="text-xs font-bold leading-tight">{pt.label}</span>
                          </button>
                        ))}
                      </div>
                      <p className="text-xs text-slate-400 mt-2 text-center">
                        {PROJECT_TYPES.find((p) => p.id === data.project_type)?.hint}
                      </p>
                    </Field>

                    <div className="grid sm:grid-cols-2 gap-5">
                      <Field label="Business name" required>
                        <input
                          value={data.business_name}
                          onChange={(e) => update('business_name', e.target.value)}
                          className={inputClass}
                          placeholder="e.g. Glow Aesthetic Clinic"
                          autoFocus
                        />
                      </Field>
                      <Field label="Industry">
                        <input
                          value={data.industry}
                          onChange={(e) => update('industry', e.target.value)}
                          className={inputClass}
                          placeholder="Healthcare, Fintech, E-commerce..."
                        />
                      </Field>
                    </div>

                    {/* Existing product URL — shown when enhancing */}
                    <AnimatePresence>
                      {data.project_type === 'enhance' && (
                        <motion.div
                          key="existing-url"
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.3, ease: easeOut }}
                        >
                          <Field
                            label="Your existing product URL"
                            hint="Link to your current website, app, or tool we should improve."
                          >
                            <input
                              value={data.existing_product_url}
                              onChange={(e) => update('existing_product_url', e.target.value)}
                              type="url"
                              className={inputClass}
                              placeholder="https://your-current-site.com"
                            />
                          </Field>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    <Field
                      label={
                        data.project_type === 'enhance'
                          ? 'What does your existing product do?'
                          : data.project_type === 'automate'
                          ? 'What process do you want to automate?'
                          : 'What does your business do?'
                      }
                      required
                      hint="A sentence or two is perfect — we'll expand on it."
                    >
                      <textarea
                        value={data.business_description}
                        onChange={(e) => update('business_description', e.target.value)}
                        rows={3}
                        className={inputClass}
                        placeholder={
                          data.project_type === 'enhance'
                            ? 'We have a booking platform for clinics and want to add an AI follow-up feature...'
                            : data.project_type === 'automate'
                            ? 'We manually track 200 client leads in spreadsheets every week and want this automated...'
                            : 'We run an aesthetic clinic offering laser treatments and skincare consultations...'
                        }
                      />
                    </Field>
                  </>
                )}

                {step === 1 && (
                  <>
                    <Field label="Who are your customers?" hint="Age, location, type of client — whatever helps us picture them.">
                      <input
                        value={data.target_customers}
                        onChange={(e) => update('target_customers', e.target.value)}
                        className={inputClass}
                        placeholder={
                          data.project_type === 'automate'
                            ? 'e.g. Our internal sales team of 12 people'
                            : 'e.g. Women aged 25–45 in Dubai interested in skincare'
                        }
                        autoFocus
                      />
                    </Field>
                    <Field
                      label={
                        data.project_type === 'enhance'
                          ? "What's missing or broken in your current product?"
                          : data.project_type === 'automate'
                          ? 'What takes too long or causes errors today?'
                          : "What's the main problem you want to solve?"
                      }
                    >
                      <textarea
                        value={data.main_problem}
                        onChange={(e) => update('main_problem', e.target.value)}
                        rows={2}
                        className={inputClass}
                        placeholder={
                          data.project_type === 'enhance'
                            ? 'e.g. No automated follow-up after bookings, clients drop off'
                            : data.project_type === 'automate'
                            ? 'e.g. We copy-paste leads from 3 sources into Excel every day — takes 2 hours'
                            : 'e.g. We lose leads from Instagram DMs and WhatsApp messages'
                        }
                      />
                    </Field>
                    <Field
                      label="What would success look like?"
                      hint="Dream outcome — we'll design toward this."
                    >
                      <textarea
                        value={data.desired_outcome}
                        onChange={(e) => update('desired_outcome', e.target.value)}
                        rows={2}
                        className={inputClass}
                        placeholder={
                          data.project_type === 'enhance'
                            ? 'e.g. 30% more repeat bookings from automated reminders'
                            : data.project_type === 'automate'
                            ? 'e.g. One dashboard that shows all leads, auto-scored and assigned'
                            : 'e.g. Turn social inquiries into booked appointments automatically'
                        }
                      />
                    </Field>
                  </>
                )}

                {step === 2 && (
                  <>
                    <Field
                      label="Link to a tool you like"
                      hint="Any app, dashboard, chatbot, booking system, or website that inspires you."
                    >
                      <input
                        value={data.reference_url}
                        onChange={(e) => update('reference_url', e.target.value)}
                        type="url"
                        className={inputClass}
                        placeholder="https://..."
                        autoFocus
                      />
                    </Field>
                    <Field label="Or upload a screenshot / video">
                      <FileUpload onFileSelect={setFile} />
                    </Field>
                    <AnimatePresence>
                      {hasReference && (
                        <motion.div
                          key="what-you-like"
                          initial={{ opacity: 0, height: 0, y: -8 }}
                          animate={{ opacity: 1, height: 'auto', y: 0 }}
                          exit={{ opacity: 0, height: 0, y: -8 }}
                          transition={{ duration: 0.35, ease: easeOut }}
                        >
                          <Field
                            label="What did you like about it?"
                            required
                            hint="Be specific — layout, flow, colors, features, or anything that stood out. This helps us match your taste more accurately."
                          >
                            <textarea
                              value={data.what_you_like}
                              onChange={(e) => update('what_you_like', e.target.value)}
                              rows={3}
                              className={inputClass}
                              placeholder="e.g. The clean booking flow, the AI chat assistant, the dashboard layout, the color palette..."
                              autoFocus
                            />
                          </Field>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </>
                )}

                {step === 3 && (
                  <>
                    <Field label="Should we include AI features?">
                      <OptionPills
                        name="needs_ai"
                        options={AI_OPTIONS}
                        value={AI_REVERSE[data.needs_ai] || AI_OPTIONS[0]}
                        onChange={(v) => update('needs_ai', AI_MAP[v])}
                        icons={AI_ICONS}
                      />
                    </Field>
                    <Field label="Project scope">
                      <OptionPills
                        name="budget_range"
                        options={BUDGET_OPTIONS}
                        value={data.budget_range}
                        onChange={(v) => update('budget_range', v)}
                        icons={BUDGET_ICONS}
                      />
                    </Field>
                    <Field label="When do you want to launch?">
                      <OptionPills
                        name="timeline"
                        options={TIMELINE_OPTIONS}
                        value={data.timeline}
                        onChange={(v) => update('timeline', v)}
                        icons={TIMELINE_ICONS}
                      />
                    </Field>
                  </>
                )}

                {step === 4 && (
                  <>
                    <div className="grid sm:grid-cols-2 gap-5">
                      <Field label="Email" required hint="We'll send your preview here.">
                        <input
                          value={data.email}
                          onChange={(e) => update('email', e.target.value)}
                          type="email"
                          className={inputClass}
                          placeholder="you@business.com"
                          autoFocus
                        />
                      </Field>
                      <Field label="WhatsApp" hint="Optional — our team can reach you directly.">
                        <input
                          value={data.whatsapp}
                          onChange={(e) => update('whatsapp', e.target.value)}
                          className={inputClass}
                          placeholder="+961..."
                        />
                      </Field>
                    </div>

                    <SummaryCard data={data} hasFile={!!file} />

                    <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50/80 p-4">
                      <IconShield className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                      <p className="text-xs text-slate-500 leading-relaxed">
                        We do not copy proprietary code, private designs, brand assets, or copyrighted content.
                        Your reference helps us understand the experience you want — then we design something custom for you.
                      </p>
                    </div>
                  </>
                )}
              </motion.div>
            </AnimatePresence>
          </div>

          <div className="submit-wizard-actions--inline relative flex items-center justify-between gap-3 mt-8 pt-7 border-t border-slate-200/60">
            <button
              type="button"
              onClick={goBack}
              disabled={step === 0 || loading}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium text-slate-600 hover:text-navy hover:bg-white/80 disabled:opacity-0 disabled:pointer-events-none transition-colors border border-transparent hover:border-slate-200/80"
            >
              <IconArrowLeft />
              Back
            </button>

            {isLast ? (
              <button
                type="button"
                onClick={() => void handleSubmit()}
                disabled={loading}
                className="gradient-btn text-sm px-6 sm:px-8 py-3 disabled:opacity-50 inline-flex items-center gap-2"
              >
                <IconSend className="w-4 h-4" />
                Create My Business Version
              </button>
            ) : (
              <button
                type="button"
                onClick={goNext}
                className="gradient-btn text-sm px-6 sm:px-8 py-3 inline-flex items-center gap-2"
              >
                Continue
                <IconArrowRight />
              </button>
            )}
            {!isLast && (
              <span className="hidden sm:flex absolute left-1/2 -translate-x-1/2 items-center gap-1 text-[10px] text-slate-400 pointer-events-none">
                Press <kbd className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[9px]">↵</kbd> to continue
              </span>
            )}
          </div>
        </div>
      </div>

      {variant === 'page' && (
        <div className="submit-wizard-cta md:hidden" role="navigation" aria-label="Form actions">
          <button
            type="button"
            className="submit-cta-back"
            onClick={goBack}
            disabled={step === 0 || loading}
            aria-label="Back"
          >
            <IconArrowLeft />
          </button>
          {isLast ? (
            <button
              type="button"
              className="submit-cta-next"
              onClick={() => void handleSubmit()}
              disabled={loading}
            >
              <IconSend className="w-4 h-4" />
              Create preview
            </button>
          ) : (
            <button type="button" className="submit-cta-next" onClick={goNext}>
              Continue
              <IconArrowRight />
            </button>
          )}
        </div>
      )}
    </>
  );
}

function stepHint(step: number): string {
  const hints = [
    'Start with the basics — this helps AI understand your world.',
    'The clearer the problem, the sharper your custom version.',
    'Share a link or screenshot — then tell us what you liked so we can match it accurately.',
    'No commitment yet — just helps us tailor the preview.',
    'Review everything, then we generate your free preview.',
  ];
  return hints[step] || '';
}

const PROJECT_TYPE_LABELS: Record<string, string> = {
  new: 'Build from scratch',
  enhance: 'Improve existing product',
  automate: 'Automate a process',
};

function SummaryCard({ data, hasFile }: { data: FormData; hasFile: boolean }) {
  const rows = [
    { label: 'Project', value: PROJECT_TYPE_LABELS[data.project_type] || data.project_type },
    { label: 'Business', value: data.business_name },
    { label: 'Industry', value: data.industry },
    { label: 'Existing URL', value: data.existing_product_url },
    { label: 'Reference', value: data.reference_url || (hasFile ? 'Screenshot uploaded' : '—') },
    { label: 'What you liked', value: data.what_you_like },
    { label: 'Scope', value: data.budget_range },
    { label: 'Timeline', value: data.timeline },
  ].filter((r) => r.value && r.value !== '—');

  return (
    <div className="submit-summary rounded-2xl border border-blue-200/60 p-5 sm:p-6 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-blue-600/[0.04] via-cyan-500/[0.06] to-blue-400/[0.03] pointer-events-none" />
      <div className="relative">
        <p className="text-[10px] font-bold text-blue-600 uppercase tracking-[0.2em] mb-4">Your preview request</p>
        <dl className="space-y-3">
          {rows.map((r, i) => (
            <motion.div
              key={r.label}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05, duration: 0.35 }}
              className="flex gap-4 text-sm border-b border-blue-100/50 pb-3 last:border-0 last:pb-0"
            >
              <dt className="text-slate-500 shrink-0 w-24 text-xs font-medium uppercase tracking-wide pt-0.5">{r.label}</dt>
              <dd className="text-navy font-semibold truncate">{r.value}</dd>
            </motion.div>
          ))}
        </dl>
      </div>
    </div>
  );
}
