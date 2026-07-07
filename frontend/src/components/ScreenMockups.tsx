interface Screen {
  screen_name: string;
  screen_type: string;
  description: string;
  visible_elements: string[];
}

interface Props {
  screens: Screen[];
  primaryColor?: string;
}

const TYPE_COLORS: Record<string, string> = {
  landing: 'from-blue-500 to-blue-600',
  chat: 'from-teal-500 to-teal-600',
  dashboard: 'from-purple-500 to-purple-600',
  booking: 'from-orange-500 to-orange-600',
  portal: 'from-indigo-500 to-indigo-600',
  default: 'from-slate-500 to-slate-600',
};

export default function ScreenMockups({ screens, primaryColor = '#2563eb' }: Props) {
  return (
    <div className="grid md:grid-cols-2 gap-6">
      {screens.map((screen, i) => (
        <div key={i} className="card overflow-hidden">
          <div className={`h-2 bg-gradient-to-r ${TYPE_COLORS[screen.screen_type] || TYPE_COLORS.default}`} />
          <div className="p-5">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-semibold">{screen.screen_name}</h4>
              <span className="text-xs bg-slate-100 px-2 py-1 rounded capitalize">{screen.screen_type}</span>
            </div>
            <p className="text-sm text-slate-600 mb-4">{screen.description}</p>
            <div className="bg-slate-50 rounded-xl p-4 border border-slate-100 min-h-[120px]">
              <div className="space-y-2">
                {screen.visible_elements.map((el, j) => (
                  <div key={j} className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: primaryColor }} />
                    <div className="h-3 bg-slate-200 rounded flex-1" style={{ maxWidth: `${60 + j * 10}%` }}>
                      <span className="sr-only">{el}</span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-1">
                {screen.visible_elements.map((el) => (
                  <span key={el} className="text-[10px] bg-white border px-2 py-0.5 rounded text-slate-500">{el}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
