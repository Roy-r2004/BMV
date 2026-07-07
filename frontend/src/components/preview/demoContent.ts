import type {
  PreviewAppointment,
  PreviewContent,
  PreviewConversation,
  PreviewLead,
  PreviewMessage,
  PreviewService,
  VisualDemo,
} from '../../types/request';
import { getHeroCopy } from './heroCopy';

export type ImageTheme = 'wellness' | 'fitness' | 'saas' | 'generic';

export interface DemoContext {
  businessName?: string;
  industry?: string | null;
  previewFeatures?: string[];
}

export interface ResolvedPreviewContent {
  imageTheme: ImageTheme;
  eyebrow: string;
  headline: string;
  subheadline: string;
  primaryCta: string;
  secondaryCta: string;
  servicesLabel: string;
  services: PreviewService[];
  aboutParagraphs: string[];
  contactIntro: string;
  formFields: string[];
  socialProof: string;
  heroHighlight: { label: string; title: string; subtitle: string };
  conversations: PreviewConversation[];
  messages: PreviewMessage[];
  bookedBanner: string;
  appointments: PreviewAppointment[];
  weekStat: string;
  weekDetail: string;
  leads: PreviewLead[];
  activity: string[];
}

function inferImageTheme(industry?: string | null, explicit?: string): ImageTheme {
  if (explicit === 'wellness' || explicit === 'fitness' || explicit === 'saas' || explicit === 'generic') {
    return explicit;
  }
  const i = (industry || '').toLowerCase();
  if (/fitness|nutrition|diet|coach|gym|workout|meal|trainer/.test(i)) return 'fitness';
  if (/wellness|clinic|aesthetic|medical|spa|beauty|dental|botox/.test(i)) return 'wellness';
  if (/saas|software|tech|marketing|sales|hr|fintech|e-?commerce/.test(i)) return 'saas';
  return 'generic';
}

function parseActivityName(activity: string): string {
  const m = activity.match(/^([A-Z][a-z]+(?:\s[A-Z]\.)?)/);
  return m ? m[1] : 'Alex M.';
}

function defaultServices(demo: VisualDemo, ctx: DemoContext): PreviewService[] {
  if (demo.feature_cards?.length) {
    return demo.feature_cards.slice(0, 4).map((f) => ({
      name: f.title,
      description: f.description,
      duration: '45 min',
      cta: demo.hero.primary_cta || 'Get started',
    }));
  }
  if (ctx.previewFeatures?.length) {
    return ctx.previewFeatures.slice(0, 4).map((f) => {
      const [name, ...rest] = f.split('—').map((s) => s.trim());
      return {
        name: name || f,
        description: rest.join(' — ') || `Part of your ${ctx.businessName || 'business'} offering.`,
        duration: '45 min',
        cta: 'Learn more',
      };
    });
  }
  return [
    { name: 'Core offering', description: 'Your flagship service, tailored to client goals.', duration: '45 min', cta: 'Book now' },
    { name: 'Consultation', description: 'A focused session to understand needs and next steps.', duration: '30 min', cta: 'Book now' },
  ];
}

function defaultConversations(demo: VisualDemo, services: PreviewService[]): PreviewConversation[] {
  const activity = demo.admin_dashboard_preview?.recent_activity || [];
  if (activity.length >= 3) {
    return activity.slice(0, 4).map((line, i) => ({
      name: parseActivityName(line),
      channel: /whatsapp/i.test(line) ? 'WhatsApp' : /instagram|dm/i.test(line) ? 'Instagram' : 'Email',
      preview: line.length > 60 ? `${line.slice(0, 57)}…` : line,
      time: ['2m', '14m', '1h', '3h'][i] || '1h',
      unread: i < 2,
    }));
  }
  const svc = services[0]?.name || 'your service';
  return [
    { name: 'Jamie R.', channel: 'Instagram', preview: `Interested in ${svc} — any availability?`, time: '2m', unread: true },
    { name: 'Taylor S.', channel: 'WhatsApp', preview: 'Can we move my session to Friday?', time: '18m', unread: true },
    { name: 'Jordan P.', channel: 'Email', preview: 'Thanks — confirmed for Thursday!', time: '1h', unread: false },
  ];
}

function defaultMessages(services: PreviewService[], businessName?: string): PreviewMessage[] {
  const svc = services[0]?.name || 'a session';
  const biz = businessName || 'our team';
  return [
    { role: 'user', text: `Hi! I'm interested in ${svc} — do you have openings this week?` },
    { role: 'team', text: `Hello! Yes — ${biz} has Thursday 2pm or Friday 11am. Which works better for you?` },
    { role: 'user', text: 'Thursday 2pm works perfectly.' },
    { role: 'team', text: `You're booked for Thursday 2pm. Confirmation sent — see you then! ✓` },
  ];
}

function defaultAppointments(services: PreviewService[]): PreviewAppointment[] {
  const a = services[0]?.name || 'Session';
  const b = services[1]?.name || 'Consultation';
  return [
    { time: '10:30', client: 'Jamie R.', service: b, status: 'confirmed' },
    { time: '2:00', client: 'Taylor S.', service: a, status: 'confirmed' },
    { time: '3:30', client: 'Open slot', service: '—', status: 'available' },
  ];
}

function defaultLeads(demo: VisualDemo, services: PreviewService[]): PreviewLead[] {
  const activity = demo.admin_dashboard_preview?.recent_activity || [];
  if (activity.length >= 2) {
    return activity.slice(0, 3).map((line, i) => ({
      name: parseActivityName(line),
      source: /whatsapp/i.test(line) ? 'WhatsApp' : /instagram/i.test(line) ? 'Instagram' : 'Website',
      service: services[i % services.length]?.name || 'Inquiry',
      status: /book|confirm/i.test(line) ? 'Booked' : i === 1 ? 'Pending' : 'New',
    }));
  }
  return [
    { name: 'Jamie R.', source: 'Instagram', service: services[0]?.name || 'Inquiry', status: 'Booked' },
    { name: 'Taylor S.', source: 'WhatsApp', service: services[1]?.name || 'Follow-up', status: 'Pending' },
    { name: 'Jordan P.', source: 'Website', service: services[0]?.name || 'Consultation', status: 'Completed' },
  ];
}

function defaultEyebrow(industry: string | null | undefined, theme: ImageTheme): string {
  if (theme === 'fitness') return 'Personalized plans · Weekly check-ins';
  if (theme === 'wellness') return 'Premium care · Same-week appointments';
  if (theme === 'saas') return 'Built for growth · Ready to scale';
  return industry ? `${industry} · Tailored for you` : 'Your business · Elevated experience';
}

function defaultAbout(demo: VisualDemo, ctx: DemoContext): string[] {
  const pc = demo.preview_content?.website?.about_paragraphs;
  if (pc?.length) return pc;
  const journey = demo.user_journey?.map((j) => j.description).filter(Boolean);
  if (journey.length >= 2) return journey.slice(0, 2);
  const name = ctx.businessName || 'your business';
  return [
    `${name} delivers ${demo.product_name} — designed around real client needs, not generic templates.`,
    demo.hero.subheadline || `From first inquiry to ongoing support, every step feels personal and professional.`,
  ];
}

export function resolvePreviewContent(demo: VisualDemo, ctx: DemoContext): ResolvedPreviewContent {
  const pc: PreviewContent = demo.preview_content || {};
  const { headline, subheadline } = getHeroCopy(demo, ctx.businessName, ctx.industry);
  const imageTheme = inferImageTheme(ctx.industry, pc.image_theme);
  const services = pc.website?.services?.length ? pc.website.services : defaultServices(demo, ctx);
  const firstSvc = services[0]?.name || 'session';

  return {
    imageTheme,
    eyebrow: pc.website?.eyebrow || defaultEyebrow(ctx.industry, imageTheme),
    headline,
    subheadline,
    primaryCta: demo.hero.primary_cta || 'Get started',
    secondaryCta: demo.hero.secondary_cta || 'Learn more',
    servicesLabel: pc.website?.services_label || (imageTheme === 'fitness' ? 'Programs & plans' : imageTheme === 'saas' ? 'Features' : 'Services'),
    services,
    aboutParagraphs: defaultAbout(demo, ctx),
    contactIntro: pc.website?.contact_intro || `Reach ${ctx.businessName || 'us'} — we typically reply within minutes.`,
    formFields: pc.website?.form_fields || ['Full name', 'Email', 'Phone', `Interested in`],
    socialProof: pc.website?.social_proof || 'Trusted by happy clients',
    heroHighlight: pc.website?.hero_highlight || {
      label: 'Next available',
      title: 'Thursday · 2:00 PM',
      subtitle: `${firstSvc} — 1 slot left`,
    },
    conversations: pc.inbox?.conversations?.length
      ? pc.inbox.conversations
      : defaultConversations(demo, services),
    messages: pc.inbox?.messages?.length ? pc.inbox.messages : defaultMessages(services, ctx.businessName),
    bookedBanner: pc.inbox?.booked_banner || `Booked · Thu 2:00 PM · ${firstSvc}`,
    appointments: pc.schedule?.appointments?.length ? pc.schedule.appointments : defaultAppointments(services),
    weekStat: pc.schedule?.week_stat || demo.admin_dashboard_preview?.cards?.[1]?.value?.trim() || '8',
    weekDetail:
      pc.schedule?.week_detail
      || (imageTheme === 'fitness'
        ? 'check-ins this week'
        : imageTheme === 'wellness'
          ? 'appointments this week'
          : imageTheme === 'saas'
            ? 'demos booked'
            : 'bookings this week'),
    leads: pc.dashboard?.leads?.length ? pc.dashboard.leads : defaultLeads(demo, services),
    activity: demo.admin_dashboard_preview?.recent_activity?.length
      ? demo.admin_dashboard_preview.recent_activity
      : [`New inquiry for ${firstSvc}`, 'Follow-up reminder sent', 'Client completed onboarding'],
  };
}
