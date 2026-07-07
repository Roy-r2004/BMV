import type { VisualDemo } from '../../../types/request';

import { getIcon } from '../../ProductHeroMockup';

import { hexAlpha } from '../liveSiteTheme';

import { resolvePreviewContent, type DemoContext, type ImageTheme, type ResolvedPreviewContent } from '../demoContent';

import type { AppShellConfig } from '../industryBranding';

import type { DashboardPage } from '../previewTypes';
import MobileScrollNav from '../MobileScrollNav';



export type { DashboardPage } from '../previewTypes';



interface Props extends DemoContext {

  demo: VisualDemo;

  shell: AppShellConfig;

  imageTheme: ImageTheme;

  leadsPanelMode: 'table' | 'adherence';

  bookingsPanelMode: 'appointments' | 'programs';

  fourthMetric: { title: string; value: string; sub: string };

  settingsLabels: string[];

  primary: string;

  secondary: string;

  page: DashboardPage;

  onNavigate: (page: DashboardPage) => void;

}



export default function DashboardView({

  demo,

  businessName,

  industry,

  previewFeatures,

  shell,

  leadsPanelMode,

  bookingsPanelMode,

  fourthMetric,

  settingsLabels,

  primary,

  secondary,

  page,

  onNavigate,

}: Props) {

  const content = resolvePreviewContent(demo, { businessName, industry, previewFeatures });

  const dash = demo.admin_dashboard_preview;

  const cards = [

    { title: dash?.cards?.[0]?.title || 'New leads', value: dash?.cards?.[0]?.value?.trim() || '12', sub: dash?.cards?.[0]?.description || '+4 today' },

    { title: dash?.cards?.[1]?.title || 'Booked', value: dash?.cards?.[1]?.value?.trim() || '8', sub: dash?.cards?.[1]?.description || 'This week' },

    { title: dash?.cards?.[2]?.title || 'Active', value: dash?.cards?.[2]?.value?.trim() || '24', sub: dash?.cards?.[2]?.description || 'Clients' },

    fourthMetric,

  ];



  return (
    <div className="min-h-full flex flex-col md:flex-row bg-slate-50">
      <aside className="hidden md:flex w-52 lg:w-56 border-r border-slate-200 bg-white flex-col shrink-0">

        <div className="p-5 border-b border-slate-100 flex items-center gap-3">

          <div

            className="w-10 h-10 rounded-xl flex items-center justify-center text-white text-sm font-bold shrink-0"

            style={{ backgroundColor: primary }}

          >

            {demo.product_name.charAt(0)}

          </div>

          <div className="min-w-0">

            <p className="font-bold text-slate-900 text-sm truncate">{demo.product_name}</p>

            <p className="text-[10px] text-slate-400 truncate">{businessName}</p>

          </div>

        </div>

        <nav className="p-3 space-y-0.5 flex-1">

          {shell.dashboardNav.map((item) => (

            <button

              key={item.id}

              type="button"

              onClick={() => onNavigate(item.id)}

              className={`w-full text-left px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${

                page === item.id ? 'text-white shadow-sm' : 'text-slate-600 hover:bg-slate-50'

              }`}

              style={page === item.id ? { backgroundColor: primary } : undefined}

            >

              {item.label}

            </button>

          ))}

        </nav>

      </aside>

      <MobileScrollNav
        className="md:hidden"
        items={shell.dashboardNav.map((item) => ({ id: item.id, label: item.label }))}
        activeId={page}
        onSelect={(id) => onNavigate(id as DashboardPage)}
        primary={primary}
      />

      <main className="flex-1 overflow-y-auto overflow-x-hidden p-3 sm:p-6 lg:p-8 min-w-0">

        {page === 'overview' && (

          <OverviewPanel

            cards={cards}

            content={content}

            shell={shell}

            primary={primary}

            secondary={secondary}

          />

        )}

        {page === 'leads' && (

          leadsPanelMode === 'adherence' ? (

            <AdherencePanel content={content} shell={shell} primary={primary} secondary={secondary} />

          ) : (

            <LeadsPanel content={content} shell={shell} primary={primary} />

          )

        )}

        {page === 'bookings' && (

          bookingsPanelMode === 'programs' ? (

            <ProgramsPanel demo={demo} shell={shell} primary={primary} secondary={secondary} />

          ) : (

            <BookingsPanel content={content} shell={shell} primary={primary} />

          )

        )}

        {page === 'clients' && <ClientsPanel content={content} shell={shell} primary={primary} />}

        {page === 'settings' && <SettingsPanel demo={demo} shell={shell} settingsLabels={settingsLabels} />}

      </main>

    </div>

  );

}



function OverviewPanel({

  cards,

  content,

  shell,

  primary,

  secondary,

}: {

  cards: { title: string; value: string; sub: string }[];

  content: ResolvedPreviewContent;

  shell: AppShellConfig;

  primary: string;

  secondary: string;

}) {

  return (

    <>

      <div className="mb-6">

        <h1 className="text-xl sm:text-2xl font-bold text-slate-900">{shell.dashboardGreeting}</h1>

        <p className="text-sm text-slate-500 mt-0.5">{shell.dashboardSubtitle}</p>

      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">

        {cards.map((c, i) => (

          <div key={c.title} className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm">

            <p className="text-xs text-slate-500 font-medium">{c.title}</p>

            <p className="text-2xl sm:text-3xl font-bold mt-1 tabular-nums" style={{ color: i === 0 ? primary : '#0f172a' }}>{c.value}</p>

            <p className="text-[10px] sm:text-xs text-emerald-600 font-medium mt-1">{c.sub}</p>

          </div>

        ))}

      </div>

      <div className="grid lg:grid-cols-5 gap-4">

        <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm overflow-hidden">

          <div className="h-24 -mx-5 -mt-5 mb-4 rounded-t-2xl" style={{ background: `linear-gradient(135deg, ${hexAlpha(primary, 0.15)}, ${hexAlpha(secondary, 0.2)})` }} />

          <p className="font-semibold text-slate-900 text-sm mb-4">Activity · Last 7 days</p>

          <div className="h-36 flex items-end gap-2">

            {[38, 62, 48, 78, 55, 92, 68, 85].map((h, i) => (

              <div key={i} className="flex-1 rounded-t-lg min-h-[6px]" style={{ height: `${h}%`, background: `linear-gradient(180deg, ${primary}, ${hexAlpha(secondary, 0.65)})`, opacity: 0.5 + i * 0.06 }} />

            ))}

          </div>

        </div>

        <div className="lg:col-span-2 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">

          <p className="font-semibold text-slate-900 text-sm mb-4">Recent activity</p>

          <div className="space-y-3">

            {content.activity.slice(0, 5).map((item) => (

              <div key={item.slice(0, 30)} className="flex gap-2.5 items-start">

                <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0 mt-1.5" />

                <p className="text-xs text-slate-600 leading-relaxed">{item}</p>

              </div>

            ))}

          </div>

        </div>

      </div>

      <LeadsTable content={content} shell={shell} primary={primary} />

    </>

  );

}



function LeadsPanel({ content, shell, primary }: { content: ResolvedPreviewContent; shell: AppShellConfig; primary: string }) {

  return (

    <>

      <h1 className="text-xl font-bold text-slate-900 mb-6">{shell.leadsPanelTitle}</h1>

      <LeadsTable content={content} shell={shell} primary={primary} />

    </>

  );

}



function LeadsTable({ content, shell, primary }: { content: ResolvedPreviewContent; shell: AppShellConfig; primary: string }) {

  const headers = shell.tableHeaders;

  return (

    <div className="mt-4 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">

      <div className="preview-table-scroll overflow-x-auto">

        <table className="w-full min-w-[36rem] text-sm">

          <thead>

            <tr className="text-left text-xs text-slate-400 border-b border-slate-50">

              <th className="px-5 py-3 font-medium">{headers.client}</th>

              <th className="px-5 py-3 font-medium">{headers.source}</th>

              <th className="px-5 py-3 font-medium">{headers.service}</th>

              <th className="px-5 py-3 font-medium">{headers.status}</th>

            </tr>

          </thead>

          <tbody>

            {content.leads.map((row) => (

              <tr key={row.name} className="border-b border-slate-50 hover:bg-slate-50/50">

                <td className="px-5 py-3.5">

                  <div className="flex items-center gap-2.5">

                    <div

                      className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold"

                      style={{ backgroundColor: primary }}

                    >

                      {row.name.charAt(0)}

                    </div>

                    <span className="font-medium text-slate-900">{row.name}</span>

                  </div>

                </td>

                <td className="px-5 py-3.5 text-slate-600">{row.source}</td>

                <td className="px-5 py-3.5 text-slate-600">{row.service}</td>

                <td className="px-5 py-3.5">

                  <span className="text-[10px] font-semibold px-2.5 py-1 rounded-full" style={{ backgroundColor: row.status === 'Booked' || row.status === 'Active' ? hexAlpha(primary, 0.1) : '#f1f5f9', color: row.status === 'Booked' || row.status === 'Active' ? primary : '#64748b' }}>

                    {row.status}

                  </span>

                </td>

              </tr>

            ))}

          </tbody>

        </table>

      </div>

    </div>

  );

}



function ProgramsPanel({ demo, shell, primary, secondary }: { demo: VisualDemo; shell: AppShellConfig; primary: string; secondary: string }) {

  const programs = demo.feature_cards?.length ? demo.feature_cards : [];

  return (

    <>

      <h1 className="text-xl font-bold text-slate-900 mb-6">{shell.bookingsPanelTitle}</h1>

      <div className="grid sm:grid-cols-2 gap-4">

        {programs.map((p, i) => (

          <div key={p.title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">

            <div className="flex items-start gap-3">

              <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0" style={{ backgroundColor: `${primary}15` }}>

                {getIcon(p.icon)}

              </div>

              <div>

                <p className="font-bold text-slate-900">{p.title}</p>

                <p className="text-sm text-slate-500 mt-1 leading-relaxed">{p.description}</p>

                <p className="text-xs font-semibold mt-3" style={{ color: secondary }}>

                  {12 + i * 4} active clients

                </p>

              </div>

            </div>

          </div>

        ))}

      </div>

    </>

  );

}



function AdherencePanel({ content, shell, primary, secondary }: { content: ResolvedPreviewContent; shell: AppShellConfig; primary: string; secondary: string }) {

  const scores = [87, 72, 94, 68, 81];

  return (

    <>

      <h1 className="text-xl font-bold text-slate-900 mb-6">{shell.leadsPanelTitle}</h1>

      <div className="space-y-3">

        {content.leads.map((c, i) => (

          <div key={c.name} className="rounded-2xl border border-slate-200 bg-white p-4 flex items-center gap-4 shadow-sm">

            <div className="w-12 h-12 rounded-full flex items-center justify-center text-white font-bold shrink-0" style={{ backgroundColor: primary }}>

              {c.name.charAt(0)}

            </div>

            <div className="flex-1 min-w-0">

              <div className="flex justify-between items-center mb-1.5">

                <p className="font-semibold text-slate-900">{c.name}</p>

                <span className="text-sm font-bold" style={{ color: secondary }}>{scores[i % scores.length]}%</span>

              </div>

              <div className="h-2 rounded-full bg-slate-100 overflow-hidden">

                <div className="h-full rounded-full" style={{ width: `${scores[i % scores.length]}%`, backgroundColor: secondary }} />

              </div>

              <p className="text-xs text-slate-500 mt-1">{c.service} · {c.source}</p>

            </div>

          </div>

        ))}

      </div>

    </>

  );

}



function BookingsPanel({ content, shell, primary }: { content: ResolvedPreviewContent; shell: AppShellConfig; primary: string }) {

  return (

    <>

      <h1 className="text-xl font-bold text-slate-900 mb-6">{shell.bookingsPanelTitle}</h1>

      <div className="grid sm:grid-cols-2 gap-4">

        {content.appointments.filter((a) => a.status !== 'available').map((b) => (

          <div key={b.time} className="rounded-2xl border border-slate-200 bg-white p-4 flex gap-4 shadow-sm">

            <div

              className="w-14 h-14 rounded-xl shrink-0 flex items-center justify-center text-white font-bold"

              style={{ backgroundColor: primary }}

            >

              {b.client.charAt(0)}

            </div>

            <div>

              <p className="font-bold text-slate-900">{b.client}</p>

              <p className="text-sm text-slate-500">{b.service}</p>

              <p className="text-xs font-semibold mt-2" style={{ color: primary }}>{b.time} today</p>

            </div>

          </div>

        ))}

      </div>

    </>

  );

}



function ClientsPanel({ content, shell, primary }: { content: ResolvedPreviewContent; shell: AppShellConfig; primary: string }) {

  return (

    <>

      <h1 className="text-xl font-bold text-slate-900 mb-6">{shell.clientsPanelTitle}</h1>

      <div className="grid sm:grid-cols-3 gap-4">

        {content.leads.map((c) => (

          <div key={c.name} className="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">

            <div

              className="w-16 h-16 rounded-full mx-auto mb-3 flex items-center justify-center text-white text-lg font-bold"

              style={{ backgroundColor: primary }}

            >

              {c.name.charAt(0)}

            </div>

            <p className="font-semibold text-slate-900">{c.name}</p>

            <p className="text-xs text-slate-500 mt-1">{c.service}</p>

            <span className="inline-block mt-2 text-[10px] font-semibold px-2 py-0.5 rounded-full" style={{ backgroundColor: hexAlpha(primary, 0.1), color: primary }}>

              {c.status}

            </span>

          </div>

        ))}

      </div>

    </>

  );

}



function SettingsPanel({ demo, shell, settingsLabels }: { demo: VisualDemo; shell: AppShellConfig; settingsLabels: string[] }) {

  const labels = settingsLabels;



  return (

    <>

      <h1 className="text-xl font-bold text-slate-900 mb-6">Settings</h1>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 max-w-lg shadow-sm space-y-4">

        {labels.map((label) => (

          <div key={label} className="flex justify-between items-center py-2 border-b border-slate-50 last:border-0">

            <span className="text-sm text-slate-700">{label}</span>

            <span className="text-xs font-semibold text-emerald-600">Active</span>

          </div>

        ))}

        <p className="text-xs text-slate-400 pt-2">{demo.product_name} · {shell.inbox.footer}</p>

      </div>

    </>

  );

}


