interface Step {
  step: number;
  title: string;
  description: string;
}

interface Props {
  steps: Step[];
  primaryColor?: string;
}

export default function UserJourneyMockup({ steps, primaryColor = '#2563eb' }: Props) {
  return (
    <div className="relative">
      <div className="hidden md:block absolute top-8 left-8 right-8 h-0.5 bg-slate-200" />
      <div className="grid md:grid-cols-5 gap-4">
        {steps.map((s) => (
          <div key={s.step} className="relative text-center">
            <div
              className="w-10 h-10 rounded-full text-white font-bold flex items-center justify-center mx-auto mb-3 relative z-10"
              style={{ backgroundColor: primaryColor }}
            >
              {s.step}
            </div>
            <h4 className="font-semibold text-sm mb-1">{s.title}</h4>
            <p className="text-xs text-slate-600">{s.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
