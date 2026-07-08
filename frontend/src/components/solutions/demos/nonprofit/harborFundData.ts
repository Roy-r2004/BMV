/** Shared Harbor Community Fund data — campaigns, donors, volunteers, impact. */

export type ImpactStory = {
  id: string;
  title: string;
  amount: number;
  story: string;
  imageUrl: string;
  metric: string;
};

export type DonateTier = {
  amount: number;
  label: string;
  impact: string;
  suggested?: boolean;
};

export type VolunteerOpp = {
  id: string;
  title: string;
  when: string;
  where: string;
  hours: number;
  spots: number;
  filled: number;
  skills: string[];
  desc: string;
  imageUrl: string;
  matchScore?: number;
};

export type VolunteerSkill = {
  id: string;
  label: string;
};

export type Campaign = {
  id: string;
  name: string;
  goal: number;
  raised: number;
  donors: number;
  daysLeft: number;
  status: 'active' | 'closing' | 'completed';
};

export type DonorSegment = {
  id: string;
  label: string;
  count: number;
  pct: number;
  avgGift: string;
  color: string;
};

export type InboxThread = {
  id: string;
  name: string;
  role: 'donor' | 'volunteer';
  preview: string;
  time: string;
  unread: boolean;
  avatar: string;
  topic: string;
  channel: 'email' | 'sms' | 'app';
};

export type Donation = {
  id: string;
  amount: number;
  tier: string;
  donorName: string;
  recurring: boolean;
  campaignId: string;
};

export const HARBOR_FUND = {
  name: 'Harbor Community Fund',
  product: 'Harbor Give',
  tagline: 'Neighbors helping neighbors · Bay Area',
  address: '214 Pier Street',
  city: 'Oakland, CA 94607',
  phone: '(510) 555-0188',
  email: 'give@harborgive.app',
  heroImage: 'https://images.unsplash.com/photo-1559027615-cd4628902d4a?auto=format&w=1200&h=800&fit=crop&q=80',
  communityImage: 'https://images.unsplash.com/photo-1469571486292-0ba58a3f068b?auto=format&w=800&h=560&fit=crop&q=80',
  hours: [
    { days: 'Mon – Fri', time: '9:00 AM – 6:00 PM' },
    { days: 'Sat', time: '10:00 AM – 2:00 PM' },
    { days: 'Sun', time: 'Closed' },
  ],
};

export const IMPACT_METER = {
  raised: 186420,
  goal: 250000,
  donors: 1842,
  meals: 31200,
  families: 890,
};

export const DONATE_TIERS: DonateTier[] = [
  { amount: 25, label: 'Seed', impact: '5 after-school meals' },
  { amount: 50, label: 'Neighbor', impact: '1 week of tutoring supplies', suggested: true },
  { amount: 100, label: 'Anchor', impact: 'A family grocery box for a month' },
  { amount: 250, label: 'Beacon', impact: 'Weekend workshop for 12 youth' },
];

export const IMPACT_STORIES: ImpactStory[] = [
  {
    id: 'meals',
    title: 'Meals @ the pier kitchen',
    amount: 50,
    story: 'Weekend line stayed open — 3,200 hot plates served while Campaign AI routed gifts to the kitchen queue in real time.',
    imageUrl: 'https://images.unsplash.com/photo-1593113646773-028c64a8f1b8?auto=format&fit=crop&w=800&h=500&q=80',
    metric: '3,200 meals served',
  },
  {
    id: 'youth',
    title: 'Youth mentorship hours',
    amount: 100,
    story: 'Forty-eight literacy & STEM mentors met learners after school — 612 hours this quarter, matched by skill not signup order.',
    imageUrl: 'https://images.unsplash.com/photo-1509062522246-3755977927d7?auto=format&fit=crop&w=800&h=500&q=80',
    metric: '612 mentor hours',
  },
  {
    id: 'housing',
    title: 'Emergency rent buffer',
    amount: 250,
    story: 'Bridge gifts reached 14 households facing eviction within 48 hours — Campaign AI flagged urgency before caseworkers dialed.',
    imageUrl: 'https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=800&h=500&q=80',
    metric: '14 homes kept',
  },
];

export const VOLUNTEER_SKILLS: VolunteerSkill[] = [
  { id: 'kitchen', label: 'Kitchen & food' },
  { id: 'tutoring', label: 'Tutoring' },
  { id: 'logistics', label: 'Logistics' },
  { id: 'outreach', label: 'Outreach' },
  { id: 'admin', label: 'Admin' },
  { id: 'tech', label: 'Tech support' },
];

export const VOLUNTEER_OPPS: VolunteerOpp[] = [
  {
    id: 'opp-kitchen',
    title: 'Pier kitchen shift',
    when: 'Sat 9:00 AM – 1:00 PM',
    where: 'Waterfront Hub',
    hours: 4,
    spots: 12,
    filled: 8,
    skills: ['kitchen', 'logistics'],
    desc: 'Prep and serve weekend meals. Knife skills welcome — training available.',
    imageUrl: 'https://images.unsplash.com/photo-1593113598332-cd288d649433?auto=format&w=500&h=360&fit=crop&q=80',
  },
  {
    id: 'opp-tutor',
    title: 'After-school tutoring',
    when: 'Tue & Thu 3:30 – 5:30 PM',
    where: 'Harbor Learning Room',
    hours: 2,
    spots: 8,
    filled: 5,
    skills: ['tutoring', 'admin'],
    desc: 'One-on-one literacy and math with grades 3–8. Curriculum packs provided.',
    imageUrl: 'https://images.unsplash.com/photo-1509062522246-3755977927d7?auto=format&w=500&h=360&fit=crop&q=80',
  },
  {
    id: 'opp-drive',
    title: 'Grocery distribution',
    when: 'Fri 4:00 – 7:00 PM',
    where: 'Community lot B',
    hours: 3,
    spots: 15,
    filled: 11,
    skills: ['logistics', 'outreach'],
    desc: 'Sort boxes, greet families, load cars. High-energy, high-impact Friday evenings.',
    imageUrl: 'https://images.unsplash.com/photo-1532629345422-751a97cea58d?auto=format&w=500&h=360&fit=crop&q=80',
  },
  {
    id: 'opp-event',
    title: 'Spring gala check-in',
    when: 'Apr 12 · 5:00 – 9:00 PM',
    where: 'Civic Hall',
    hours: 4,
    spots: 10,
    filled: 4,
    skills: ['admin', 'tech', 'outreach'],
    desc: 'Badge guests, run QR check-in, support the thank-you wall. Event ops with AI roster.',
    imageUrl: 'https://images.unsplash.com/photo-1511632765481-a0e7e8f7e1d8?auto=format&w=500&h=360&fit=crop&q=80',
  },
];

export const CAMPAIGNS: Campaign[] = [
  { id: 'bridge', name: 'Bridge the Gap 2026', goal: 250000, raised: 186420, donors: 1842, daysLeft: 42, status: 'active' },
  { id: 'summer', name: 'Summer Youth Lab', goal: 75000, raised: 61200, donors: 420, daysLeft: 18, status: 'closing' },
  { id: 'meals', name: 'Pier Kitchen Sustain', goal: 40000, raised: 40000, donors: 610, daysLeft: 0, status: 'completed' },
];

export const DONOR_SEGMENTS: DonorSegment[] = [
  { id: 'first', label: 'First-time', count: 612, pct: 33, avgGift: '$42', color: '#86efac' },
  { id: 'recurring', label: 'Monthly', count: 480, pct: 26, avgGift: '$38/mo', color: '#22c55e' },
  { id: 'major', label: 'Major ($500+)', count: 94, pct: 5, avgGift: '$1,240', color: '#166534' },
  { id: 'lapsed', label: 'Re-engaged', count: 218, pct: 12, avgGift: '$65', color: '#fbbf24' },
  { id: 'events', label: 'Event donors', count: 438, pct: 24, avgGift: '$120', color: '#d97706' },
];

export const VOLUNTEER_HOURS = [
  { label: 'Kitchen', hours: 1240, pct: 34 },
  { label: 'Tutoring', hours: 980, pct: 27 },
  { label: 'Logistics', hours: 720, pct: 20 },
  { label: 'Events', hours: 460, pct: 12 },
  { label: 'Admin', hours: 260, pct: 7 },
];

export const INBOX_THREADS: InboxThread[] = [
  { id: '0', name: 'Maya Chen', role: 'donor', preview: 'Thank you — receipt arrived!', time: '8m', unread: true, avatar: 'M', topic: '$50 · Bridge', channel: 'email' },
  { id: '1', name: 'Jordan Lee', role: 'volunteer', preview: 'Matched to pier kitchen Sat', time: '22m', unread: true, avatar: 'J', topic: 'Kitchen shift', channel: 'app' },
  { id: '2', name: 'Elena Soto', role: 'donor', preview: 'Can I make this monthly?', time: '1h', unread: false, avatar: 'E', topic: '$100 · Youth', channel: 'sms' },
  { id: '3', name: 'Chris Park', role: 'volunteer', preview: 'Tutoring confirmation received', time: '3h', unread: false, avatar: 'C', topic: 'After-school', channel: 'email' },
];

export function matchVolunteerOpps(skillIds: string[]): VolunteerOpp[] {
  const set = new Set(skillIds);
  return VOLUNTEER_OPPS.map((opp) => {
    const overlap = opp.skills.filter((s) => set.has(s)).length;
    const base = set.size === 0 ? 70 : 68 + overlap * 12 + (opp.spots - opp.filled);
    return { ...opp, matchScore: Math.min(99, base) };
  }).sort((a, b) => (b.matchScore ?? 0) - (a.matchScore ?? 0));
}

export function storyForAmount(amount: number): ImpactStory {
  const sorted = [...IMPACT_STORIES].sort((a, b) => a.amount - b.amount);
  let best = sorted[0];
  for (const s of sorted) {
    if (amount >= s.amount) best = s;
  }
  return best;
}

export function suggestAmount(preference: 'meals' | 'youth' | 'housing' | 'default' = 'default'): number {
  if (preference === 'meals') return 50;
  if (preference === 'youth') return 100;
  if (preference === 'housing') return 250;
  return 50;
}

export function getCampaign(id: string) {
  return CAMPAIGNS.find((c) => c.id === id);
}

export function campaignPct(c: Campaign) {
  return Math.min(100, Math.round((c.raised / c.goal) * 100));
}
