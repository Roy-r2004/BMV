/** Metro Auto Care — shared demo data */

export type ServiceType = {
  id: string;
  label: string;
  /** Short label for tile glyph (not emoji) */
  glyph: string;
  desc: string;
  price: string;
  duration: string;
  bayPreference: 'quick' | 'align' | 'diag' | 'general';
  imageUrl: string;
};

export type ServiceRequest = {
  id: string;
  customer: string;
  vehicle: string;
  plate: string;
  service: string;
  serviceId: string;
  time: string;
  bayScore: number;
  suggestedBay: number;
  status: 'new' | 'assigned' | 'in-bay' | 'ready';
  preview: string;
  mileage: string;
};

export type Tech = {
  id: string;
  name: string;
  initials: string;
  specialty: string;
  status: 'available' | 'on-bay' | 'parts' | 'off';
  bay?: number;
  jobsToday: number;
  rating: number;
};

export type BayStatus = 'open' | 'active' | 'hold' | 'wash';

export type Bay = {
  id: number;
  label: string;
  lift: string;
  status: BayStatus;
  jobId?: string;
  customer?: string;
  vehicle?: string;
  service?: string;
  techId?: string;
  progress: number;
  stage: string;
  eta?: string;
};

export type BookingSubmission = {
  serviceId: string;
  vehicle: string;
  slot: string;
  notes: string;
};

export type UpsellAlert = {
  id: string;
  customer: string;
  vehicle: string;
  item: string;
  reason: string;
  value: string;
  urgency: 'high' | 'medium' | 'low';
};

export const COMPANY = {
  name: 'Metro Auto Care',
  shortName: 'METRO',
  tagline: 'Book · Track · Drive out',
  address: '880 Service Lane',
  city: 'Denver, CO 80204',
  phone: '(303) 555-0144',
  email: 'service@metroauto.app',
  /** Full-bleed shop floor / vehicle work */
  heroImage: 'https://images.unsplash.com/photo-1619642751034-765dfdf7c58e?w=1600&h=1000&fit=crop&q=85',
  shopImage: 'https://images.unsplash.com/photo-1486262715619-67b23e15e804?w=900&h=640&fit=crop&q=85',
  statusImage: 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=900&h=600&fit=crop&q=85',
  hours: [
    { days: 'Mon – Fri', time: '7:30 AM – 6:00 PM' },
    { days: 'Sat', time: '8:00 AM – 3:00 PM' },
    { days: 'Sun', time: 'Closed' },
  ],
};

export const SERVICES: ServiceType[] = [
  {
    id: 'oil',
    label: 'Oil change',
    glyph: 'OIL',
    desc: 'Synthetic or conventional · filter included',
    price: '$49–$89',
    duration: '35 min',
    bayPreference: 'quick',
    imageUrl: 'https://images.unsplash.com/photo-1632823470760-599a76f4e0ea?w=640&h=480&fit=crop&q=80',
  },
  {
    id: 'rotate',
    label: 'Tire rotation',
    glyph: 'TIRE',
    desc: 'Balance check · tread depth report',
    price: '$35–$55',
    duration: '40 min',
    bayPreference: 'align',
    imageUrl: 'https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=640&h=480&fit=crop&q=80',
  },
  {
    id: 'diag',
    label: 'Diagnostics',
    glyph: 'SCAN',
    desc: 'Check-engine · multi-system scan',
    price: '$119–$165',
    duration: '60 min',
    bayPreference: 'diag',
    imageUrl: 'https://images.unsplash.com/photo-1487754180451-c456f719a1fc?w=640&h=480&fit=crop&q=80',
  },
  {
    id: 'brakes',
    label: 'Brake service',
    glyph: 'BRK',
    desc: 'Pads, rotors, fluid flush',
    price: '$220–$480',
    duration: '90 min',
    bayPreference: 'general',
    imageUrl: 'https://images.unsplash.com/photo-1486262715619-67b23e15e804?w=640&h=480&fit=crop&q=80',
  },
  {
    id: 'inspect',
    label: 'Multi-point inspect',
    glyph: 'MPI',
    desc: '52-point safety + maintenance list',
    price: '$49',
    duration: '45 min',
    bayPreference: 'general',
    imageUrl: 'https://images.unsplash.com/photo-1625047509248-ec889cbff17f?w=640&h=480&fit=crop&q=80',
  },
];

export const BOOKING_SLOTS = [
  'Today · 2:30 PM',
  'Today · 4:00 PM',
  'Tomorrow · 8:00 AM',
  'Tomorrow · 10:30 AM',
  'Fri · 1:00 PM',
];

export const SERVICE_QUEUE: ServiceRequest[] = [
  { id: 'r1', customer: 'Ava Chen', vehicle: '2021 Honda CR-V', plate: 'CO·7X2K9', service: 'Oil change', serviceId: 'oil', time: '3m', bayScore: 96, suggestedBay: 2, status: 'new', preview: 'Due for 5k synthetic — customer waiting in lounge', mileage: '48,210 mi' },
  { id: 'r2', customer: 'Marcus Lee', vehicle: '2018 F-150', plate: 'CO·4M88P', service: 'Diagnostics', serviceId: 'diag', time: '12m', bayScore: 91, suggestedBay: 4, status: 'assigned', preview: 'Check-engine P0302 — misfire cyl 2. Scanner on Bay 4.', mileage: '92,400 mi' },
  { id: 'r3', customer: 'Priya Nair', vehicle: '2020 Tesla Model 3', plate: 'CO·E1V91', service: 'Tire rotation', serviceId: 'rotate', time: '22m', bayScore: 84, suggestedBay: 1, status: 'in-bay', preview: 'Uneven wear front-left — AI recommends alignment upsell', mileage: '31,050 mi' },
  { id: 'r4', customer: 'Jordan Webb', vehicle: '2016 Camry', plate: 'CO·9R3TT', service: 'Brake service', serviceId: 'brakes', time: '41m', bayScore: 78, suggestedBay: 3, status: 'new', preview: 'Front pads at 2mm — parts staged in cage B', mileage: '118,700 mi' },
  { id: 'r5', customer: 'Sam Ortiz', vehicle: '2019 RAV4', plate: 'CO·2H7LQ', service: 'Multi-point inspect', serviceId: 'inspect', time: '1h', bayScore: 72, suggestedBay: 2, status: 'ready', preview: 'Ready for pickup — cabin filter + wiper upsell queued', mileage: '56,880 mi' },
];

export const TECHS: Tech[] = [
  { id: 't1', name: 'Elena V.', initials: 'EV', specialty: 'Quick lube', status: 'on-bay', bay: 2, jobsToday: 6, rating: 4.9 },
  { id: 't2', name: 'Derek M.', initials: 'DM', specialty: 'Alignment', status: 'on-bay', bay: 1, jobsToday: 4, rating: 4.8 },
  { id: 't3', name: 'Nina K.', initials: 'NK', specialty: 'Diagnostics', status: 'on-bay', bay: 4, jobsToday: 3, rating: 4.9 },
  { id: 't4', name: 'Chris P.', initials: 'CP', specialty: 'Brakes / general', status: 'available', jobsToday: 5, rating: 4.7 },
  { id: 't5', name: 'Omar S.', initials: 'OS', specialty: 'EV / hybrid', status: 'parts', bay: 3, jobsToday: 2, rating: 4.8 },
];

export const BAYS: Bay[] = [
  { id: 1, label: 'Bay 1', lift: 'Alignment rack', status: 'active', jobId: 'r3', customer: 'Priya Nair', vehicle: '2020 Tesla Model 3', service: 'Tire rotation', techId: 't2', progress: 55, stage: 'Rotating tires', eta: '18 min' },
  { id: 2, label: 'Bay 2', lift: 'Quick-service lift', status: 'active', jobId: 'r1', customer: 'Ava Chen', vehicle: '2021 Honda CR-V', service: 'Oil change', techId: 't1', progress: 20, stage: 'Draining oil', eta: '28 min' },
  { id: 3, label: 'Bay 3', lift: 'Heavy-duty lift', status: 'hold', jobId: 'r4', customer: 'Jordan Webb', vehicle: '2016 Camry', service: 'Brake service', techId: 't5', progress: 10, stage: 'Waiting on pads', eta: 'Parts 12 min' },
  { id: 4, label: 'Bay 4', lift: 'Diag station', status: 'active', jobId: 'r2', customer: 'Marcus Lee', vehicle: '2018 F-150', service: 'Diagnostics', techId: 't3', progress: 70, stage: 'Live scan · P0302', eta: '22 min' },
];

export const STATUS_TIMELINE = [
  { stage: 'Checked in', done: true, time: '1:42 PM' },
  { stage: 'On lift', done: true, time: '1:55 PM' },
  { stage: 'In progress', done: true, time: '2:08 PM' },
  { stage: 'Quality check', done: false, time: '—' },
  { stage: 'Ready for pickup', done: false, time: '—' },
];

export const UPSELL_ALERTS: UpsellAlert[] = [
  { id: 'u1', customer: 'Priya Nair', vehicle: 'Tesla Model 3', item: '4-wheel alignment', reason: 'Uneven FL wear detected on rotation', value: '+$129', urgency: 'high' },
  { id: 'u2', customer: 'Sam Ortiz', vehicle: 'RAV4', item: 'Cabin air filter', reason: 'Inspect flagged clogged filter', value: '+$48', urgency: 'medium' },
  { id: 'u3', customer: 'Marcus Lee', vehicle: 'F-150', item: 'Ignition coil (cyl 2)', reason: 'Diag confirms misfire — coil weak', value: '+$215', urgency: 'high' },
  { id: 'u4', customer: 'Ava Chen', vehicle: 'CR-V', item: 'Engine air filter', reason: 'Maintenance AI — due at 48k', value: '+$32', urgency: 'low' },
];

export const TODAY_METRICS = [
  { label: 'Revenue today', value: '$6,140', sub: '+12% vs last Wed', accent: true },
  { label: 'Jobs completed', value: '14', sub: '4 in bay now' },
  { label: 'Bay utilization', value: '92%', sub: 'AI-scheduled lifts' },
  { label: 'Upsells accepted', value: '7', sub: '$890 extra' },
];

export function bayScoreLabel(score: number): string {
  if (score >= 90) return 'Best bay';
  if (score >= 80) return 'Good fit';
  if (score >= 70) return 'Flexible';
  return 'Hold';
}

export function preferredBayForService(serviceId: string): number {
  const svc = SERVICES.find((s) => s.id === serviceId);
  if (!svc) return 2;
  if (svc.bayPreference === 'quick') return 2;
  if (svc.bayPreference === 'align') return 1;
  if (svc.bayPreference === 'diag') return 4;
  return 3;
}

export function bayLabelForPreference(pref: ServiceType['bayPreference']): string {
  if (pref === 'quick') return 'Bay 2 · quick lift';
  if (pref === 'align') return 'Bay 1 · alignment';
  if (pref === 'diag') return 'Bay 4 · diag';
  return 'Bay 3 · heavy';
}
