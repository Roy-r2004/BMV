import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import type { VisualDemo } from '../../../types/request';

import { getIcon } from '../../ProductHeroMockup';

import { hexAlpha } from '../liveSiteTheme';

import { resolvePreviewContent, type DemoContext, type ResolvedPreviewContent } from '../demoContent';

import type { ResolvedShell } from '../resolveAppShell';

import IndustryVisual, { ServiceVisual } from '../IndustryVisual';

import { PREVIEW_IMAGES } from '../previewImages';

import PreviewImage from '../PreviewImage';



export type WebsitePage = 'home' | 'services' | 'about' | 'contact';



interface Props extends DemoContext {

  demo: VisualDemo;

  branding: ResolvedShell;

  content: ResolvedPreviewContent;

  primary: string;

  secondary: string;

  page: WebsitePage;

  onNavigate: (page: WebsitePage) => void;

  websiteTone?: boolean;

  cinematic?: boolean;

}



export default function PublicWebsiteView({

  demo,

  businessName,

  branding,

  content,

  primary,

  secondary,

  page,

  onNavigate,

  websiteTone = false,

  cinematic = false,

}: Props) {

  const name = businessName || 'Your Business';

  const useClinicPhotos = content.imageTheme === 'wellness';

  const darkHeader = branding.headerVariant === 'dark';



  return (

    <div className="min-h-full" style={{ backgroundColor: branding.background }}>

      <header className={`sticky top-0 z-20 border-b backdrop-blur-md ${darkHeader ? 'border-slate-800 bg-slate-900/95' : 'border-slate-100 bg-white/95'}`}>

        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">

          <button type="button" onClick={() => onNavigate('home')} className="flex items-center gap-2.5">

            <div

              className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold shadow-sm"

              style={{ backgroundColor: primary }}

            >

              {name.charAt(0)}

            </div>

            <span className={`font-semibold text-sm sm:text-base truncate max-w-[9rem] sm:max-w-none ${darkHeader ? 'text-white' : 'text-slate-900'}`}>{name}</span>

          </button>

          <nav className="hidden md:flex items-center gap-1">

            {branding.nav.map((item) => (

              <button

                key={item.id}

                type="button"

                onClick={() => onNavigate(item.id)}

                className={`px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${

                  page === item.id

                    ? 'text-white'

                    : darkHeader

                      ? 'text-slate-300 hover:bg-slate-800'

                      : 'text-slate-600 hover:bg-slate-100'

                }`}

                style={page === item.id ? { backgroundColor: primary } : undefined}

              >

                {item.label}

              </button>

            ))}

          </nav>

          <button

            type="button"

            onClick={() => onNavigate('contact')}

            className="px-3 sm:px-4 py-2 rounded-full text-white text-xs sm:text-sm font-semibold shadow-lg shrink-0"

            style={{ backgroundColor: primary }}

          >

            {content.primaryCta}

          </button>

        </div>

        <div className="md:hidden flex gap-1 px-4 pb-3 overflow-x-auto scrollbar-none">

          {branding.nav.map((item) => (

            <button

              key={item.id}

              type="button"

              onClick={() => onNavigate(item.id)}

              className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-medium ${

                page === item.id

                  ? 'text-white'

                  : darkHeader

                    ? 'text-slate-300 bg-slate-800'

                    : 'text-slate-600 bg-slate-100'

              }`}

              style={page === item.id ? { backgroundColor: primary } : undefined}

            >

              {item.label}

            </button>

          ))}

        </div>

      </header>



      {page === 'home' && (

        <HomePage
          demo={demo}
          branding={branding}
          content={content}
          primary={primary}
          secondary={secondary}
          useClinicPhotos={useClinicPhotos}
          onNavigate={onNavigate}
          websiteTone={websiteTone}
          cinematic={cinematic}
        />

      )}

      {page === 'services' && (

        <ServicesPage content={content} primary={primary} secondary={secondary} useClinicPhotos={useClinicPhotos} onNavigate={onNavigate} />

      )}

      {page === 'about' && <AboutPage name={name} primary={primary} demo={demo} content={content} useClinicPhotos={useClinicPhotos} />}

      {page === 'contact' && (

        <ContactPage name={name} primary={primary} secondary={secondary} content={content} useClinicPhotos={useClinicPhotos} />

      )}



      <footer className="border-t border-slate-100 py-8 text-center text-xs text-slate-400">
        © {new Date().getFullYear()} {name}
        {!websiteTone && <> · Powered by {demo.product_name}</>}
      </footer>

    </div>

  );

}



function HomePage({
  demo,
  branding,
  content,
  primary,
  secondary,
  useClinicPhotos,
  onNavigate,
  websiteTone = false,
  cinematic = false,
}: {
  demo: VisualDemo;
  branding: ResolvedShell;
  content: ResolvedPreviewContent;
  primary: string;
  secondary: string;
  useClinicPhotos: boolean;
  onNavigate: (p: WebsitePage) => void;
  websiteTone?: boolean;
  cinematic?: boolean;
}) {

  const features = demo.feature_cards?.length ? demo.feature_cards : content.services.map((s) => ({
    title: s.name,
    description: s.description,
    icon: 'sparkles',
  }));

  const sections = websiteTone || cinematic
    ? ['hero', 'features', 'ai', 'programs', 'journey', 'testimonial', 'cta']
    : branding.homeSections?.length ? branding.homeSections : ['hero', 'features', 'programs'];
  const centeredHero = branding.heroLayout === 'centered' && !cinematic;
  const aiSteps = demo.ai_workflow?.length ? demo.ai_workflow : [];

  const sectionBlocks: Record<string, ReactNode> = {
    hero: (
      <section key="hero" className={`relative overflow-hidden ${cinematic ? 'showcase-hero' : ''}`}>
        {cinematic && (
          <>
            <div className="showcase-hero__mesh pointer-events-none" style={{ background: `radial-gradient(ellipse 80% 60% at 20% 0%, ${hexAlpha(primary, 0.22)}, transparent), radial-gradient(ellipse 60% 50% at 90% 20%, ${hexAlpha(secondary, 0.18)}, transparent)` }} />
            <div className="showcase-hero__orb showcase-hero__orb--1 pointer-events-none" style={{ background: hexAlpha(primary, 0.35) }} />
            <div className="showcase-hero__orb showcase-hero__orb--2 pointer-events-none" style={{ background: hexAlpha(secondary, 0.28) }} />
          </>
        )}
        <div className={`max-w-5xl mx-auto px-4 sm:px-6 py-12 sm:py-20 grid gap-10 items-center relative z-10 ${centeredHero ? 'text-center max-w-3xl' : 'lg:grid-cols-2'}`}>
          <div className={centeredHero ? 'mx-auto' : ''}>
            {cinematic && (
              <motion.span
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="showcase-ai-badge inline-flex items-center gap-1.5 mb-4"
              >
                <span className="showcase-ai-badge__dot" />
                AI-powered · Automates your busywork
              </motion.span>
            )}
            <p className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: primary }}>{content.eyebrow}</p>
            <h1 className={`font-bold text-slate-900 leading-[1.06] tracking-tight mb-5 ${cinematic ? 'text-3xl sm:text-4xl lg:text-[2.75rem]' : 'text-3xl sm:text-4xl lg:text-5xl'}`}>{content.headline}</h1>
            <p className={`text-slate-600 text-base sm:text-lg leading-relaxed mb-6 ${centeredHero ? 'mx-auto' : 'max-w-md'}`}>{content.subheadline}</p>
            {cinematic && content.aiChips.length > 0 && (
              <div className={`flex flex-wrap gap-2 mb-7 ${centeredHero ? 'justify-center' : ''}`}>
                {content.aiChips.map((chip) => (
                  <span key={chip} className="showcase-ai-chip">{chip}</span>
                ))}
              </div>
            )}
            <div className={`flex flex-wrap gap-3 ${centeredHero ? 'justify-center' : ''}`}>
              <button type="button" onClick={() => onNavigate('contact')} className={`px-6 py-3 rounded-full text-white font-semibold text-sm ${cinematic ? 'showcase-cta-primary' : 'shadow-xl'}`} style={{ backgroundColor: primary, boxShadow: cinematic ? undefined : `0 12px 32px ${hexAlpha(primary, 0.35)}` }}>{content.primaryCta}</button>
              <button type="button" onClick={() => onNavigate('services')} className="px-6 py-3 rounded-full border border-slate-200/80 text-slate-700 font-semibold text-sm bg-white/80 backdrop-blur-sm">{content.secondaryCta}</button>
            </div>
            <p className="mt-8 text-sm text-slate-600"><span className="font-semibold text-slate-900">★</span> {content.socialProof}</p>
          </div>
          {!centeredHero && (
            <motion.div
              initial={cinematic ? { opacity: 0, scale: 0.96, y: 16 } : undefined}
              animate={cinematic ? { opacity: 1, scale: 1, y: 0 } : undefined}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              className="relative"
            >
              {useClinicPhotos ? (
                <PreviewImage src={PREVIEW_IMAGES.hero} alt="" className="aspect-[4/5] w-full rounded-3xl object-cover shadow-2xl shadow-slate-300/50" />
              ) : (
                <IndustryVisual theme={content.imageTheme} primary={primary} secondary={secondary} />
              )}
              <div className={`absolute bottom-6 left-6 right-6 rounded-2xl p-4 shadow-xl ${cinematic ? 'showcase-hero-card bg-white/90 backdrop-blur-md border border-white/60' : 'bg-white/95 backdrop-blur'}`}>
                <p className="text-xs text-slate-500">{content.heroHighlight.label}</p>
                <p className="text-lg font-bold text-slate-900">{content.heroHighlight.title}</p>
                <p className="text-xs font-medium mt-1" style={{ color: primary }}>{content.heroHighlight.subtitle}</p>
                {cinematic && (
                  <p className="text-[10px] text-emerald-600 font-semibold mt-2 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    AI confirmed · reminder scheduled
                  </p>
                )}
              </div>
            </motion.div>
          )}
        </div>
      </section>
    ),
    features: (
      <section key="features" className={`py-12 sm:py-16 px-4 sm:px-6 ${cinematic ? 'showcase-section-dark' : ''}`}>
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-8">
            <p className="text-xs font-bold uppercase tracking-widest mb-2" style={{ color: primary }}>
              {cinematic ? 'What runs automatically' : websiteTone ? 'What we offer' : 'Platform features'}
            </p>
            <h2 className={`text-2xl sm:text-3xl font-bold ${cinematic ? 'text-white' : 'text-slate-900'}`}>
              {websiteTone || cinematic ? 'Built to automate your day' : branding.featuresTitle}
            </h2>
            <p className={`mt-2 max-w-lg mx-auto text-sm sm:text-base ${cinematic ? 'text-slate-400' : 'text-slate-600'}`}>
              {cinematic ? 'AI handles the repetitive work — your team handles the human moments.' : websiteTone ? 'Everything your customers need — presented the way a real business site would.' : branding.featuresSubtitle}
            </p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {features.slice(0, 4).map((card, i) => (
              <motion.div
                key={card.title}
                initial={cinematic ? { opacity: 0, y: 20 } : undefined}
                whileInView={cinematic ? { opacity: 1, y: 0 } : undefined}
                viewport={{ once: true }}
                transition={{ delay: i * 0.08, duration: 0.5 }}
                className={`rounded-2xl p-5 transition-shadow ${cinematic ? 'showcase-feature-card' : 'border border-slate-200/80 bg-white shadow-sm hover:shadow-md'}`}
              >
                <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl mb-3" style={{ backgroundColor: `${primary}${cinematic ? '30' : '18'}` }}>{getIcon(card.icon)}</div>
                <h3 className={`font-bold text-sm leading-snug ${cinematic ? 'text-white' : 'text-slate-900'}`}>{card.title}</h3>
                <p className={`text-xs mt-2 leading-relaxed line-clamp-3 ${cinematic ? 'text-slate-400' : 'text-slate-500'}`}>{card.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>
    ),
    ai: aiSteps.length ? (
      <section key="ai" className="py-12 sm:py-16 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-10">
            <span className="showcase-ai-badge inline-flex items-center gap-1.5 mb-3">
              <span className="showcase-ai-badge__dot" />
              AI workflow
            </span>
            <h2 className="text-2xl sm:text-3xl font-bold text-slate-900">{content.automationTitle}</h2>
            <p className="text-slate-600 mt-2 max-w-xl mx-auto text-sm">{content.automationSubtitle}</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {aiSteps.slice(0, 4).map((step, i) => (
              <motion.div
                key={step.step}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.55 }}
                className="showcase-ai-step relative rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm"
              >
                <div className="flex items-center gap-2 mb-3">
                  <span className="showcase-ai-step__num" style={{ backgroundColor: primary }}>{step.step}</span>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-violet-600 bg-violet-50 px-2 py-0.5 rounded-full">Auto</span>
                </div>
                <h3 className="font-bold text-slate-900 text-sm">{step.title}</h3>
                <p className="text-xs text-slate-500 mt-2 leading-relaxed">{step.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>
    ) : null,
    programs: (
      <section key="programs" className="py-12 bg-slate-50/80">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 grid sm:grid-cols-3 gap-4">
          {content.services.slice(0, 3).map((s, i) => (
            <button key={s.name} type="button" onClick={() => onNavigate('services')} className="text-left rounded-2xl overflow-hidden bg-white border border-slate-200 shadow-sm hover:shadow-lg transition-all group">
              {useClinicPhotos ? (
                <PreviewImage src={[PREVIEW_IMAGES.treatment1, PREVIEW_IMAGES.treatment2, PREVIEW_IMAGES.treatment3][i]} alt={s.name} className="w-full h-32 object-cover group-hover:scale-105 transition-transform duration-500" />
              ) : (
                <ServiceVisual theme={content.imageTheme} primary={primary} secondary={secondary} />
              )}
              <div className="p-4">
                <h3 className="font-bold text-slate-900 text-sm">{s.name}</h3>
                <p className="text-xs mt-1 line-clamp-2 text-slate-500">{s.description}</p>
              </div>
            </button>
          ))}
        </div>
      </section>
    ),
    journey: demo.user_journey?.length ? (
      <section key="journey" className="py-12 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-xl font-bold text-slate-900 mb-6 text-center">How it works</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {demo.user_journey.slice(0, 4).map((step) => (
              <div key={step.step} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <span className="text-xs font-bold px-2 py-1 rounded-full" style={{ backgroundColor: `${primary}15`, color: primary }}>Step {step.step}</span>
                <h3 className="font-semibold text-slate-900 mt-3 text-sm">{step.title}</h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    ) : null,
    testimonial: content.testimonial ? (
      <section key="testimonial" className="py-12 px-4 sm:px-6">
        <div className="max-w-3xl mx-auto text-center showcase-testimonial rounded-3xl p-8 sm:p-10">
          <div className="flex justify-center gap-0.5 mb-4" aria-hidden>
            {Array.from({ length: content.testimonial.rating }).map((_, i) => (
              <span key={i} className="text-amber-400 text-lg">★</span>
            ))}
          </div>
          <blockquote className="text-lg sm:text-xl font-medium text-slate-800 leading-relaxed">&ldquo;{content.testimonial.quote}&rdquo;</blockquote>
          <p className="mt-5 text-sm font-semibold text-slate-900">{content.testimonial.name}</p>
          <p className="text-xs text-slate-500">{content.testimonial.role}</p>
        </div>
      </section>
    ) : null,
    cta: (
      <section key="cta" className="py-10 px-4 sm:px-6">
        <div className="max-w-3xl mx-auto text-center rounded-3xl p-8 text-white" style={{ background: `linear-gradient(135deg, ${primary}, ${secondary})` }}>
          <h2 className="text-xl font-bold">{demo.final_cta?.headline || content.primaryCta}</h2>
          <p className="text-sm opacity-90 mt-2">{demo.final_cta?.description || content.subheadline}</p>
          <button type="button" onClick={() => onNavigate('contact')} className="mt-5 px-6 py-2.5 rounded-full bg-white text-sm font-semibold" style={{ color: primary }}>{demo.final_cta?.button_text || content.primaryCta}</button>
        </div>
      </section>
    ),
  };

  return <>{sections.map((id) => sectionBlocks[id] ?? null).filter(Boolean)}</>;
}



function ServicesPage({

  content,

  primary,

  secondary,

  useClinicPhotos,

  onNavigate,

}: {

  content: ReturnType<typeof resolvePreviewContent>;

  primary: string;

  secondary: string;

  useClinicPhotos: boolean;

  onNavigate: (p: WebsitePage) => void;

}) {

  return (

    <section className="py-10 sm:py-14 lg:py-20 px-4 sm:px-6">

      <div className="max-w-5xl mx-auto px-4 sm:px-6">

        <div className="text-center mb-10">

          <h2 className="text-2xl sm:text-3xl font-bold text-slate-900">{content.servicesLabel}</h2>

          <p className="text-slate-600 mt-2">{content.subheadline}</p>

        </div>

        <div className="grid sm:grid-cols-2 gap-5">

          {content.services.map((s, i) => (

            <div key={s.name} className="rounded-2xl overflow-hidden border border-slate-200 bg-white shadow-sm hover:shadow-xl transition-shadow">

              {useClinicPhotos ? (

                <PreviewImage

                  src={[PREVIEW_IMAGES.treatment1, PREVIEW_IMAGES.treatment2, PREVIEW_IMAGES.treatment3, PREVIEW_IMAGES.treatment4][i % 4]}

                  alt={s.name}

                  className="w-full h-44 object-cover"

                />

              ) : (

                <ServiceVisual theme={content.imageTheme} primary={primary} secondary={secondary} className="h-44" />

              )}

              <div className="p-5 sm:p-6">

                <h3 className="font-bold text-slate-900">{s.name}</h3>

                {s.duration && <p className="text-sm text-slate-500 mt-1">{s.duration}</p>}

                <p className="text-sm text-slate-600 mt-3 leading-relaxed">{s.description}</p>

                <button

                  type="button"

                  onClick={() => onNavigate('contact')}

                  className="mt-4 text-sm font-semibold"

                  style={{ color: primary }}

                >

                  {s.cta || 'Get started'} →

                </button>

              </div>

            </div>

          ))}

        </div>

      </div>

    </section>

  );

}



function AboutPage({

  name,

  primary,

  demo,

  content,

  useClinicPhotos,

}: {

  name: string;

  primary: string;

  demo: VisualDemo;

  content: ReturnType<typeof resolvePreviewContent>;

  useClinicPhotos: boolean;

}) {

  return (

    <section className="py-10 sm:py-14 lg:py-20 px-4 sm:px-6">

      <div className="max-w-5xl mx-auto px-4 sm:px-6 grid lg:grid-cols-2 gap-10 items-center">

        {useClinicPhotos ? (

          <PreviewImage src={PREVIEW_IMAGES.about} alt="" className="rounded-3xl w-full h-72 lg:h-96 object-cover shadow-xl" />

        ) : (

          <IndustryVisual theme={content.imageTheme} primary={primary} secondary={demo.visual_theme.secondary_color} aspect="aspect-[4/3] lg:h-96" />

        )}

        <div>

          <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 mb-4">About {name}</h2>

          {content.aboutParagraphs.map((p) => (

            <p key={p.slice(0, 40)} className="text-slate-600 leading-relaxed mb-4">

              {p}

            </p>

          ))}

        </div>

      </div>

    </section>

  );

}



function ContactPage({

  name,

  primary,

  secondary,

  content,

  useClinicPhotos,

}: {

  name: string;

  primary: string;

  secondary: string;

  content: ReturnType<typeof resolvePreviewContent>;

  useClinicPhotos: boolean;

}) {

  return (

    <section className="py-10 sm:py-14 lg:py-20 px-4 sm:px-6">

      <div className="max-w-5xl mx-auto px-4 sm:px-6 grid lg:grid-cols-2 gap-10">

        <div>

          <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 mb-2">{content.primaryCta}</h2>

          <p className="text-slate-600 mb-6">{content.contactIntro}</p>

          <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>

            {content.formFields.map((label) => (

              <div key={label}>

                <label className="text-xs font-medium text-slate-500">{label}</label>

                <input className="mt-1 w-full px-4 py-3 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20" />

              </div>

            ))}

            <button

              type="submit"

              className="w-full py-3.5 rounded-xl text-white font-semibold text-sm shadow-lg"

              style={{ background: `linear-gradient(135deg, ${primary}, ${secondary})` }}

            >

              Submit

            </button>

          </form>

        </div>

        <div className="space-y-4">

          {useClinicPhotos ? (

            <PreviewImage src={PREVIEW_IMAGES.contact} alt="" className="rounded-2xl w-full h-48 object-cover shadow-md" />

          ) : (

            <IndustryVisual theme={content.imageTheme} primary={primary} secondary={secondary} aspect="aspect-video" />

          )}

          <div className="rounded-2xl border border-slate-200 p-5 bg-slate-50">

            <p className="font-semibold text-slate-900 text-sm">{name}</p>

            <p className="text-sm text-slate-600 mt-2">{content.contactIntro}</p>

          </div>

        </div>

      </div>

    </section>

  );

}


