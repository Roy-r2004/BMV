interface Card {
  title: string;
  value: string;
  description: string;
}

interface Props {
  cards: Card[];
  recentActivity: string[];
  primaryColor?: string;
}

export default function AdminDashboardMockup({ cards, recentActivity, primaryColor = '#2563eb' }: Props) {
  return (
    <div className="card overflow-hidden">
      <div className="bg-slate-800 px-4 py-2 flex items-center gap-2">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-400" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-400" />
        </div>
        <span className="text-slate-400 text-xs ml-2">Admin Dashboard</span>
      </div>
      <div className="p-5">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
          {cards.map((card, i) => (
            <div key={i} className="bg-slate-50 rounded-xl p-4 border border-slate-100">
              <p className="text-xs text-slate-500 mb-1">{card.title}</p>
              <p className="text-2xl font-bold" style={{ color: primaryColor }}>{card.value}</p>
              <p className="text-[10px] text-slate-400">{card.description}</p>
            </div>
          ))}
        </div>
        <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
          <p className="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wide">Recent Activity</p>
          <div className="space-y-2">
            {recentActivity.map((item, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
                <span className="text-slate-600">{item}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
