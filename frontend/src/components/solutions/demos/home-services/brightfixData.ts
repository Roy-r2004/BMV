/** BrightFix Plumbing — shared demo data */

export type JobType = {
  id: string;
  label: string;
  icon: string;
  desc: string;
  avgPrice: string;
  skill: string;
};

export type ServiceZone = {
  id: string;
  label: string;
  eta: string;
  techs: number;
  urgent: boolean;
};

export type Urgency = 'emergency' | 'today' | 'this-week';

export type JobRequest = {
  id: string;
  customer: string;
  address: string;
  zone: string;
  jobType: string;
  urgency: Urgency;
  photos: number;
  time: string;
  dispatchScore: number;
  skillMatch: number;
  status: 'new' | 'quoted' | 'dispatched';
  preview: string;
};

export type Tech = {
  id: string;
  name: string;
  initials: string;
  skill: string;
  status: 'available' | 'en-route' | 'on-site' | 'off';
  zone: string;
  jobsToday: number;
  rating: number;
};

export type ActiveJob = {
  id: string;
  customer: string;
  address: string;
  jobType: string;
  techId: string;
  status: 'en-route' | 'in-progress' | 'done';
  eta?: string;
  value: string;
  zone: string;
  pinX: number;
  pinY: number;
};

export type QuoteSubmission = {
  jobTypeId: string;
  urgency: Urgency;
  zoneId: string;
  photos: number;
  description: string;
};

export const COMPANY = {
  name: 'BrightFix Plumbing',
  tagline: 'Same-day service · Licensed & insured',
  address: '1420 Industrial Blvd',
  city: 'Austin, TX 78745',
  phone: '(512) 555-0192',
  email: 'hello@brightfix.app',
  emergencyPhone: '(512) 555-0911',
  heroImage: 'https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?w=1600&h=1000&fit=crop&q=85',
  techImage: 'https://images.unsplash.com/photo-1621905252507-b35492cc74b4?w=900&h=640&fit=crop&q=85',
  hours: [
    { days: 'Mon – Fri', time: '7:00 AM – 7:00 PM' },
    { days: 'Sat', time: '8:00 AM – 5:00 PM' },
    { days: 'Emergency', time: '24/7 dispatch' },
  ],
};

export const JOB_TYPES: JobType[] = [
  { id: 'leak', label: 'Leak / burst pipe', icon: '💧', desc: 'Active water leak or burst line', avgPrice: '$185–$420', skill: 'Emergency' },
  { id: 'drain', label: 'Clogged drain', icon: '🚿', desc: 'Slow or blocked sink, tub, or toilet', avgPrice: '$120–$280', skill: 'Drain' },
  { id: 'water-heater', label: 'Water heater', icon: '🔥', desc: 'No hot water, leaks, or replacement', avgPrice: '$350–$1,800', skill: 'HVAC-plumb' },
  { id: 'install', label: 'Fixture install', icon: '🔧', desc: 'Faucet, toilet, disposal, or appliance', avgPrice: '$95–$350', skill: 'General' },
  { id: 'sewer', label: 'Sewer / main line', icon: '⚠️', desc: 'Backups, tree roots, or camera inspect', avgPrice: '$250–$2,400', skill: 'Sewer' },
];

export const SERVICE_ZONES: ServiceZone[] = [
  { id: 'north', label: 'North Austin', eta: '18 min', techs: 3, urgent: false },
  { id: 'central', label: 'Central / Downtown', eta: '12 min', techs: 2, urgent: true },
  { id: 'south', label: 'South Austin', eta: '22 min', techs: 2, urgent: false },
  { id: 'east', label: 'East / Manor', eta: '28 min', techs: 1, urgent: false },
];

export const URGENCY_OPTIONS: { id: Urgency; label: string; desc: string; badge?: string }[] = [
  { id: 'emergency', label: 'Emergency', desc: 'Water actively flooding — dispatch now', badge: 'ASAP' },
  { id: 'today', label: 'Today', desc: 'Same-day window, non-emergency', badge: '4 hr' },
  { id: 'this-week', label: 'This week', desc: 'Schedule at your convenience' },
];

export const JOB_QUEUE: JobRequest[] = [
  { id: 'j1', customer: 'Maria G.', address: '1842 Oak Hill Dr', zone: 'South', jobType: 'Burst pipe', urgency: 'emergency', photos: 3, time: '2m', dispatchScore: 98, skillMatch: 95, status: 'new', preview: 'Water spraying from under sink — shutoff failed' },
  { id: 'j2', customer: 'James T.', address: '901 Congress Ave', zone: 'Central', jobType: 'Clogged drain', urgency: 'today', photos: 1, time: '14m', dispatchScore: 82, skillMatch: 88, status: 'quoted', preview: 'Kitchen sink backing up — tried plunger' },
  { id: 'j3', customer: 'Linda W.', address: '4400 Burnet Rd', zone: 'North', jobType: 'Water heater', urgency: 'today', photos: 2, time: '28m', dispatchScore: 76, skillMatch: 72, status: 'new', preview: 'No hot water since morning — unit is 12 yrs old' },
  { id: 'j4', customer: 'Dev P.', address: '2100 E 6th St', zone: 'East', jobType: 'Fixture install', urgency: 'this-week', photos: 0, time: '1h', dispatchScore: 54, skillMatch: 90, status: 'new', preview: 'New faucet delivery Thu — need install Fri' },
  { id: 'j5', customer: 'Karen S.', address: '3300 S Lamar', zone: 'South', jobType: 'Sewer line', urgency: 'emergency', photos: 2, time: '35m', dispatchScore: 91, skillMatch: 68, status: 'quoted', preview: 'Multiple drains backing up — possible main line' },
];

export const TECHS: Tech[] = [
  { id: 't1', name: 'Mike R.', initials: 'MR', skill: 'Emergency', status: 'available', zone: 'Central', jobsToday: 4, rating: 4.9 },
  { id: 't2', name: 'Sara L.', initials: 'SL', skill: 'Drain', status: 'en-route', zone: 'North', jobsToday: 3, rating: 4.8 },
  { id: 't3', name: 'Carlos D.', initials: 'CD', skill: 'Sewer', status: 'on-site', zone: 'East', jobsToday: 2, rating: 4.9 },
  { id: 't4', name: 'Amy K.', initials: 'AK', skill: 'General', status: 'available', zone: 'South', jobsToday: 5, rating: 4.7 },
  { id: 't5', name: 'Tom B.', initials: 'TB', skill: 'HVAC-plumb', status: 'off', zone: '—', jobsToday: 0, rating: 4.8 },
];

export const ACTIVE_JOBS: ActiveJob[] = [
  { id: 'a1', customer: 'Maria G.', address: '1842 Oak Hill Dr', jobType: 'Burst pipe', techId: 't1', status: 'en-route', eta: '8 min', value: '$385', zone: 'south', pinX: 62, pinY: 72 },
  { id: 'a2', customer: 'James T.', address: '901 Congress Ave', jobType: 'Clogged drain', techId: 't2', status: 'in-progress', value: '$165', zone: 'central', pinX: 48, pinY: 42 },
  { id: 'a3', customer: 'Linda W.', address: '4400 Burnet Rd', jobType: 'Water heater', techId: 't4', status: 'done', value: '$1,240', zone: 'north', pinX: 38, pinY: 28 },
  { id: 'a4', customer: 'Karen S.', address: '3300 S Lamar', jobType: 'Sewer line', techId: 't3', status: 'in-progress', value: '$890', zone: 'south', pinX: 55, pinY: 68 },
];

export const TODAY_METRICS = [
  { label: 'Revenue today', value: '$4,820', sub: '+18% vs last Tue', accent: true },
  { label: 'Jobs completed', value: '11', sub: '3 in progress' },
  { label: 'Avg response', value: '4 min', sub: 'Quote to dispatch' },
  { label: '5★ reviews', value: '7', sub: 'Auto-sent post-job' },
];

export const REVIEW_QUEUE = [
  { customer: 'Linda W.', job: 'Water heater', sent: '12m ago', status: 'opened' },
  { customer: 'Dev P.', job: 'Fixture install', sent: '2h ago', status: 'reviewed' },
];

export function scoreLabel(score: number): string {
  if (score >= 90) return 'Priority';
  if (score >= 75) return 'High';
  if (score >= 60) return 'Normal';
  return 'Low';
}

export function urgencyColor(u: Urgency): string {
  if (u === 'emergency') return 'emergency';
  if (u === 'today') return 'today';
  return 'week';
}
