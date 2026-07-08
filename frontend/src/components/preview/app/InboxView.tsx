import { useState } from 'react';

import type { VisualDemo } from '../../../types/request';

import { resolvePreviewContent, type DemoContext } from '../demoContent';

import type { AppShellConfig } from '../industryBranding';
import MobileScrollNav from '../MobileScrollNav';



interface Props extends DemoContext {

  demo: VisualDemo;

  shell: AppShellConfig;

  primary: string;

  secondary: string;

}



export default function InboxView({ demo, businessName, industry, previewFeatures, shell, primary }: Props) {

  const content = resolvePreviewContent(demo, { businessName, industry, previewFeatures });

  const [active, setActive] = useState('0');

  const conversations = content.conversations;

  const activeConvo = conversations[Number(active)] || conversations[0];



  return (
    <div className="min-h-full flex flex-col sm:flex-row bg-white">
      <MobileScrollNav
        className="sm:hidden"
        items={conversations.map((c, i) => ({ id: String(i), label: c.name }))}
        activeId={active}
        onSelect={setActive}
        primary={primary}
      />

      <div className="hidden sm:flex w-72 lg:w-80 border-r border-slate-200 flex-col bg-slate-50/50 shrink-0">

        <div className="p-4 border-b border-slate-200 bg-white">

          <h2 className="font-bold text-slate-900">{shell.inbox.title}</h2>

          <p className="text-xs text-slate-500 mt-0.5">{shell.inbox.subtitle}</p>

        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">

          {conversations.map((c, i) => (

            <button

              key={`${c.name}-${i}`}

              type="button"

              onClick={() => setActive(String(i))}

              className={`w-full text-left rounded-xl p-3 transition-colors ${

                active === String(i) ? 'bg-white shadow-sm border border-slate-200' : 'hover:bg-white/80'

              }`}

            >

              <div className="flex items-center gap-3">

                <div

                  className="w-10 h-10 rounded-full shrink-0 flex items-center justify-center text-white text-sm font-bold"

                  style={{ backgroundColor: primary }}

                >

                  {c.name.charAt(0)}

                </div>

                <div className="flex-1 min-w-0">

                  <div className="flex justify-between items-center">

                    <p className="text-sm font-semibold text-slate-900 truncate">{c.name}</p>

                    <span className="text-[10px] text-slate-400">{c.time}</span>

                  </div>

                  <p className="text-xs text-slate-500 truncate">{c.preview}</p>

                </div>

                {c.unread && <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: primary }} />}

              </div>

              <span

                className="inline-block mt-2 text-[9px] font-semibold px-2 py-0.5 rounded-full"

                style={{ backgroundColor: `${primary}18`, color: primary }}

              >

                {c.channel}

              </span>

            </button>

          ))}

        </div>

      </div>



      <div className="flex-1 flex flex-col min-w-0">

        <div className="px-4 sm:px-6 py-4 border-b border-slate-200 flex items-center gap-3 bg-white">

          <div

            className="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-bold"

            style={{ backgroundColor: primary }}

          >

            {activeConvo?.name.charAt(0) || '?'}

          </div>

          <div className="flex-1">

            <p className="font-semibold text-slate-900 text-sm">{activeConvo?.name}</p>

            <p className="text-xs text-emerald-600 flex items-center gap-1">

              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> {shell.inbox.statusLabel} · {activeConvo?.channel}

            </p>

          </div>

        </div>



        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 bg-slate-50/30 min-h-[280px]">

          {content.messages.map((msg, i) => (

            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>

              <div

                className={`max-w-[85%] sm:max-w-[70%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${

                  msg.role === 'user'

                    ? 'text-white rounded-br-md'

                    : 'bg-white border border-slate-200 text-slate-700 rounded-bl-md shadow-sm'

                }`}

                style={msg.role === 'user' ? { backgroundColor: primary } : undefined}

              >

                {msg.role === 'team' && msg.ai_assisted && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-violet-600 mb-1.5">
                    <svg viewBox="0 0 24 24" className="w-3 h-3" fill="currentColor" aria-hidden><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>
                    AI sent
                  </span>
                )}
                {msg.text}

              </div>

            </div>

          ))}

          <div className="flex justify-center">

            <span className="text-[10px] text-slate-400 bg-white px-3 py-1 rounded-full border border-slate-100">

              {content.bookedBanner}

            </span>

          </div>

        </div>



        <div className="px-4 pt-3 pb-1 flex gap-2 overflow-x-auto scrollbar-none">

          {shell.inbox.quickReplies.map((q) => (

            <button

              key={q}

              type="button"

              className="shrink-0 text-xs px-3 py-1.5 rounded-full border font-medium"

              style={{ borderColor: `${primary}40`, color: primary, backgroundColor: `${primary}08` }}

            >

              {q}

            </button>

          ))}

        </div>



        <div className="p-4 border-t border-slate-200 bg-white">

          <div className="flex gap-2 max-w-3xl mx-auto">

            <input

              placeholder="Type a reply…"

              className="flex-1 px-4 py-3 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20"

            />

            <button type="button" className="px-5 py-3 rounded-xl text-white text-sm font-semibold shrink-0" style={{ backgroundColor: primary }}>

              Send

            </button>

          </div>

          <p className="text-[10px] text-slate-400 text-center mt-2">{demo.product_name} · {shell.inbox.footer}</p>

        </div>

      </div>

    </div>

  );

}


