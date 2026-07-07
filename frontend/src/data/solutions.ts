export interface IndustrySolution {
  id: string;
  name: string;
  icon: string;
  accent: string;
  tagline: string;
  description: string;
  capabilities: string[];
}

/**
 * Industry solution catalog — the plan for verticals we build and integrate.
 * Live demos per industry are rolled out progressively; until then these
 * describe the blueprint we customize and integrate for each business.
 */
export const INDUSTRY_SOLUTIONS: IndustrySolution[] = [
  {
    id: 'healthcare',
    name: 'Healthcare & Clinics',
    icon: 'pulse',
    accent: 'from-blue-500 to-cyan-500',
    tagline: 'Turn DMs and calls into booked appointments with an AI intake assistant.',
    description:
      'A booking and intake system that qualifies patients, answers common questions, and keeps your front desk focused on care instead of scheduling.',
    capabilities: ['AI patient intake chat', 'Appointment booking & reminders', 'Staff dashboard & daily summaries', 'Treatment FAQ automation'],
  },
  {
    id: 'personal-care',
    name: 'Barbershops & Salons',
    icon: 'scissors',
    accent: 'from-violet-500 to-fuchsia-500',
    tagline: 'Fill every chair with automated booking, reminders, and repeat-client loyalty.',
    description:
      'Clients book online in seconds, get automatic reminders, and you get a simple dashboard to manage your day — no more back-and-forth on Instagram.',
    capabilities: ['Online booking & calendar', 'No-show reminders', 'Client history & preferences', 'Loyalty & rebooking prompts'],
  },
  {
    id: 'food',
    name: 'Restaurants & Cafes',
    icon: 'utensils',
    accent: 'from-orange-500 to-amber-500',
    tagline: 'Online ordering and reservations that feel as good as your food tastes.',
    description:
      'A branded ordering and reservation experience for your restaurant, with a live dashboard for staff to manage tables and incoming orders.',
    capabilities: ['Digital menu & ordering', 'Table reservations', 'Order status for staff', 'Repeat-customer offers'],
  },
  {
    id: 'real-estate',
    name: 'Real Estate',
    icon: 'home',
    accent: 'from-indigo-500 to-blue-600',
    tagline: 'Capture and qualify leads the moment they view a listing.',
    description:
      'A listings site with an AI assistant that answers buyer questions, schedules viewings, and hands your agents a qualified lead — not a cold one.',
    capabilities: ['Listings showcase', 'AI buyer Q&A assistant', 'Viewing scheduler', 'Lead scoring dashboard'],
  },
  {
    id: 'fitness',
    name: 'Gyms & Fitness Coaching',
    icon: 'dumbbell',
    accent: 'from-emerald-500 to-teal-500',
    tagline: 'Class bookings, memberships, and progress tracking in one place.',
    description:
      'Members book classes, track progress, and stay engaged — while you get a dashboard for attendance, memberships, and renewals.',
    capabilities: ['Class & session booking', 'Membership management', 'Progress tracking', 'Automated renewal reminders'],
  },
  {
    id: 'professional-services',
    name: 'Legal & Consulting',
    icon: 'briefcase',
    accent: 'from-slate-600 to-slate-800',
    tagline: 'Client intake and document requests without the email back-and-forth.',
    description:
      'A client portal that handles intake forms, document collection, and scheduling — so your team spends time advising, not chasing paperwork.',
    capabilities: ['Client intake forms', 'Secure document requests', 'Consultation scheduling', 'Case/matter status dashboard'],
  },
  {
    id: 'ecommerce',
    name: 'Retail & E-commerce',
    icon: 'cart',
    accent: 'from-purple-500 to-indigo-500',
    tagline: 'A storefront with AI product search that actually understands shoppers.',
    description:
      'An online storefront with natural-language product search, smart recommendations, and a seller dashboard to manage inventory and orders.',
    capabilities: ['Product storefront', 'AI-powered search & recs', 'Inventory dashboard', 'Order & fulfillment tracking'],
  },
  {
    id: 'home-services',
    name: 'Home Services',
    icon: 'wrench',
    accent: 'from-yellow-500 to-orange-500',
    tagline: 'Quote requests, scheduling, and dispatch — for plumbers, electricians, cleaners.',
    description:
      'Customers request quotes and book jobs online; you get a dispatch dashboard to assign and track work without juggling phone calls.',
    capabilities: ['Instant quote requests', 'Job scheduling & dispatch', 'Technician status updates', 'Customer follow-up automation'],
  },
  {
    id: 'education',
    name: 'Education & Tutoring',
    icon: 'graduation',
    accent: 'from-cyan-500 to-blue-500',
    tagline: 'Course booking, student portals, and progress tracking for tutors and schools.',
    description:
      'Students book sessions and track progress, while instructors get a portal to manage schedules, materials, and payments.',
    capabilities: ['Session/course booking', 'Student progress portal', 'Materials & resource sharing', 'Payment & package tracking'],
  },
  {
    id: 'automotive',
    name: 'Automotive Services',
    icon: 'car',
    accent: 'from-red-500 to-rose-600',
    tagline: 'Service booking and real-time repair status for shops and dealers.',
    description:
      'Customers book service appointments and track repair status online, cutting down the "is my car ready?" calls to your front desk.',
    capabilities: ['Service appointment booking', 'Live repair status', 'Estimate approvals', 'Service history records'],
  },
  {
    id: 'hospitality',
    name: 'Hospitality & Hotels',
    icon: 'bed',
    accent: 'from-teal-500 to-emerald-600',
    tagline: 'A booking engine and AI concierge for guest requests.',
    description:
      'Guests book stays and message an AI concierge for requests, while staff manage bookings and requests from one dashboard.',
    capabilities: ['Direct booking engine', 'AI concierge chat', 'Guest request dashboard', 'Automated pre-arrival messaging'],
  },
  {
    id: 'nonprofit',
    name: 'Nonprofits & Community Orgs',
    icon: 'heart',
    accent: 'from-pink-500 to-rose-500',
    tagline: 'Donor management, event signups, and volunteer coordination.',
    description:
      'A donation and event platform with a dashboard to track donors, volunteers, and upcoming events — built for teams without a tech department.',
    capabilities: ['Donation & campaign pages', 'Event signup & RSVPs', 'Volunteer coordination', 'Donor & impact dashboard'],
  },
];
