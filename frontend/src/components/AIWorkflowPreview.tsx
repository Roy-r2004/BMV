interface Step {
  step: number;
  title: string;
  description: string;
}

interface Props {
  steps: Step[];
  primaryColor?: string;
}

export default function AIWorkflowPreview({ steps, primaryColor = '#2563eb' }: Props) {
  return (
    <div className="space-y-3">
      {steps.map((s, i) => (
        <div key={s.step} className="flex items-start gap-4">
          <div className="flex flex-col items-center">
            <div
              className="w-8 h-8 rounded-full text-white text-sm font-bold flex items-center justify-center shrink-0"
              style={{ backgroundColor: primaryColor }}
            >
              {s.step}
            </div>
            {i < steps.length - 1 && <div className="w-0.5 h-8 bg-slate-200 mt-1" />}
          </div>
          <div className="card p-4 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-medium text-accent-teal bg-teal-50 px-2 py-0.5 rounded">AI</span>
              <h4 className="font-semibold text-sm">{s.title}</h4>
            </div>
            <p className="text-xs text-slate-600">{s.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
