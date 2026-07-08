/** Apex Legal Group — client portal, intake, matters, partner hub */

export type PracticeArea = {
  id: string;
  name: string;
  category: string;
  fee: string;
  duration: string;
  tag?: string;
  desc: string;
  imageUrl: string;
  partnerId: string;
};

export type Partner = {
  id: string;
  name: string;
  title: string;
  specialties: string[];
  bio: string;
  photoInitial: string;
  imageUrl: string;
};

export type ConsultSlot = {
  id: string;
  label: string;
  day: string;
  time: string;
  practiceId: string;
  partnerId: string;
};

export type Matter = {
  id: string;
  name: string;
  client: string;
  practice: string;
  score: 'ready' | 'intake' | 'docs-pending';
  docsPct: string;
  lastActivity: string;
};

export const FIRM = {
  name: 'Apex Legal Group',
  tagline: 'Corporate · Employment · Litigation',
  address: '200 Park Avenue',
  city: 'New York, NY 10166',
  phone: '(212) 555-0198',
  email: 'intake@apexlegal.app',
  heroImage: 'https://images.unsplash.com/photo-1497366216548-37526070297c?w=1400&h=900&fit=crop&q=85',
  officeImage: 'https://images.unsplash.com/photo-1521791136064-7986c2920216?w=900&h=640&fit=crop&q=85',
  practiceHeroImage: 'https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=1400&h=500&fit=crop&q=85',
  portalImage: 'https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=900&h=1200&fit=crop&q=85',
};

export const PARTNERS: Partner[] = [
  {
    id: 'rachel',
    name: 'Rachel Holt',
    title: 'Managing partner · Corporate',
    specialties: ['M&A', 'Contracts', 'Governance'],
    bio: 'Former Big Law partner — structures deals that close without six months of email.',
    photoInitial: 'R',
    imageUrl: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&h=500&fit=crop&q=80',
  },
  {
    id: 'marcus',
    name: 'Marcus Chen',
    title: 'Partner · Employment',
    specialties: ['HR policy', 'Disputes', 'Compliance'],
    bio: 'Counsels fast-growing teams — intake to counsel letter in days, not quarters.',
    photoInitial: 'M',
    imageUrl: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&h=500&fit=crop&q=80',
  },
  {
    id: 'elena',
    name: 'Elena Vasquez',
    title: 'Partner · Litigation',
    specialties: ['Commercial disputes', 'Arbitration', 'Settlement'],
    bio: 'Trial-ready strategist — clients see matter status without chasing associates.',
    photoInitial: 'E',
    imageUrl: 'https://images.unsplash.com/photo-1580489944761-15a19d654956?w=400&h=500&fit=crop&q=80',
  },
];

export const PRACTICE_AREAS: PracticeArea[] = [
  {
    id: 'corporate',
    name: 'Corporate counsel',
    category: 'Business',
    fee: 'From $450/hr',
    duration: 'Discovery call',
    tag: 'Most requested',
    desc: 'Entity formation, vendor contracts, and investor-ready governance — intake before billable hours.',
    imageUrl: 'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=900&h=680&fit=crop&q=85',
    partnerId: 'rachel',
  },
  {
    id: 'employment',
    name: 'Employment & HR',
    category: 'Workforce',
    fee: 'Flat fee options',
    duration: '45 min consult',
    desc: 'Handbooks, terminations, and dispute prep — AI collects docs before partner review.',
    imageUrl: 'https://images.unsplash.com/photo-1521737711867-e3b97375f902?w=900&h=680&fit=crop&q=85',
    partnerId: 'marcus',
  },
  {
    id: 'litigation',
    name: 'Commercial litigation',
    category: 'Disputes',
    fee: 'Contingency review',
    duration: 'Case assessment',
    desc: 'Demand letters through arbitration — matter portal keeps clients off the phone.',
    imageUrl: 'https://images.unsplash.com/photo-1589391887766-a1fcca3f67d5?w=900&h=680&fit=crop&q=85',
    partnerId: 'elena',
  },
  {
    id: 'estate',
    name: 'Estate planning',
    category: 'Personal',
    fee: 'Package pricing',
    duration: '60 min consult',
    tag: 'Family offices',
    desc: 'Trusts, wills, and succession — secure doc vault with automated reminders.',
    imageUrl: 'https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=900&h=680&fit=crop&q=85',
    partnerId: 'rachel',
  },
];

export const PRACTICE_SECTIONS = [
  { id: 'business', title: 'Business law', items: PRACTICE_AREAS.filter((p) => p.category === 'Business' || p.category === 'Workforce') },
  { id: 'disputes', title: 'Disputes & personal', items: PRACTICE_AREAS.filter((p) => p.category === 'Disputes' || p.category === 'Personal') },
].filter((s) => s.items.length > 0);

export const CONSULT_SLOTS: ConsultSlot[] = [
  { id: 'thu-corp-10', label: 'Thu 10:00 AM · Corporate', day: 'Thursday', time: '10:00 AM', practiceId: 'corporate', partnerId: 'rachel' },
  { id: 'thu-emp-2', label: 'Thu 2:00 PM · Employment', day: 'Thursday', time: '2:00 PM', practiceId: 'employment', partnerId: 'marcus' },
  { id: 'fri-lit-11', label: 'Fri 11:00 AM · Litigation', day: 'Friday', time: '11:00 AM', practiceId: 'litigation', partnerId: 'elena' },
  { id: 'fri-est-3', label: 'Fri 3:00 PM · Estate', day: 'Friday', time: '3:00 PM', practiceId: 'estate', partnerId: 'rachel' },
];

export const HUB_MATTERS: Matter[] = [
  { id: '1', name: 'Chen LLC · Vendor contract', client: 'David Chen', practice: 'Corporate', score: 'ready', docsPct: '100%', lastActivity: 'Consult booked Thu 10am' },
  { id: '2', name: 'Northwind HR dispute', client: 'Priya N.', practice: 'Employment', score: 'docs-pending', docsPct: '60%', lastActivity: 'W-2 requested' },
  { id: '3', name: 'Atlas v. Meridian', client: 'Atlas Corp', practice: 'Litigation', score: 'intake', docsPct: '40%', lastActivity: 'Conflict scan running' },
  { id: '4', name: 'Walsh family trust', client: 'James Walsh', practice: 'Estate', score: 'ready', docsPct: '100%', lastActivity: 'Partner review scheduled' },
];

export const TODAY_MATTERS = [
  { time: '9:00 AM', client: 'Doc review', matter: 'Northwind HR', partner: 'Marcus Chen', status: 'open' as const },
  { time: '10:00 AM', client: 'David Chen', matter: 'Chen LLC · Corporate', partner: 'Rachel Holt', status: 'confirmed' as const },
  { time: '2:00 PM', client: 'Intake queue', matter: 'Employment consults', partner: 'Marcus Chen', status: 'pending' as const },
  { time: '4:00 PM', client: 'Settlement call', matter: 'Atlas v. Meridian', partner: 'Elena Vasquez', status: 'open' as const },
];

export const DOC_CHECKLIST = [
  { name: 'Corporate charter', done: true },
  { name: 'Vendor agreement draft', done: true },
  { name: 'Cap table summary', done: false },
  { name: 'ID verification', done: true },
];

export const WEEKLY_INTAKE = [
  { day: 'Mon', completed: 3, goal: 4, active: false },
  { day: 'Tue', completed: 4, goal: 4, active: false },
  { day: 'Wed', completed: 2, goal: 4, active: false },
  { day: 'Thu', completed: 2, goal: 4, active: true },
  { day: 'Fri', completed: 0, goal: 3, active: false },
];

export function slotsForPractice(practiceId: string): ConsultSlot[] {
  return CONSULT_SLOTS.filter((s) => s.practiceId === practiceId);
}

export function getPractice(id: string): PracticeArea | undefined {
  return PRACTICE_AREAS.find((p) => p.id === id);
}

export function getPartner(id: string): Partner | undefined {
  return PARTNERS.find((p) => p.id === id);
}
