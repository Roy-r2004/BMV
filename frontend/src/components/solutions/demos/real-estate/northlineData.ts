/** Northline Realty — listings site, inbox, viewings, agent CRM */

export type Listing = {
  id: string;
  address: string;
  neighborhood: string;
  price: string;
  beds: number;
  baths: number;
  sqft: string;
  tag?: string;
  desc: string;
  imageUrl: string;
  agentId: string;
  hoa?: string;
};

export type Agent = {
  id: string;
  name: string;
  title: string;
  specialties: string[];
  bio: string;
  photoInitial: string;
  imageUrl: string;
};

export type ViewingSlot = {
  id: string;
  label: string;
  day: string;
  time: string;
  listingId: string;
  agentId: string;
};

export type Lead = {
  id: string;
  name: string;
  source: string;
  listing: string;
  score: 'hot' | 'warm' | 'cold';
  budget: string;
  lastActivity: string;
};

export const AGENCY = {
  name: 'Northline Realty',
  tagline: 'Brooklyn & Manhattan · Buyer-first',
  address: '88 North 6th Street',
  city: 'Brooklyn, NY 11249',
  phone: '(718) 555-0177',
  email: 'hello@northline.app',
  heroImage: 'https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=1400&h=900&fit=crop&q=85',
  officeImage: 'https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=900&h=640&fit=crop&q=85',
  listingsHeroImage: 'https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1400&h=500&fit=crop&q=85',
  valuationImage: 'https://images.unsplash.com/photo-1568605114967-8130f3a36993?w=900&h=1200&fit=crop&q=85',
};

export const AGENTS: Agent[] = [
  {
    id: 'sarah',
    name: 'Sarah Chen',
    title: 'Lead Agent · Brooklyn',
    specialties: ['First-time buyers', 'Condos', 'Negotiation'],
    bio: 'Twelve years closing deals in Williamsburg and Greenpoint. Known for fast viewings and clear comps.',
    photoInitial: 'S',
    imageUrl: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&h=500&fit=crop&q=80',
  },
  {
    id: 'marcus',
    name: 'Marcus Webb',
    title: 'Senior Agent · Manhattan',
    specialties: ['Luxury', 'Investors', 'Off-market'],
    bio: 'Former analyst turned agent — data-driven pricing and investor-ready packages.',
    photoInitial: 'M',
    imageUrl: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&h=500&fit=crop&q=80',
  },
  {
    id: 'elena',
    name: 'Elena Ruiz',
    title: 'Buyer specialist',
    specialties: ['Families', 'School zones', 'Viewings'],
    bio: 'Books back-to-back Saturday tours and keeps buyers warm with AI follow-up.',
    photoInitial: 'E',
    imageUrl: 'https://images.unsplash.com/photo-1580489944761-15a19d654956?w=400&h=500&fit=crop&q=80',
  },
];

export const LISTINGS: Listing[] = [
  {
    id: 'oak-lane',
    address: '22 Oak Lane',
    neighborhood: 'Williamsburg',
    price: '$1.28M',
    beds: 3,
    baths: 2,
    sqft: '1,840',
    tag: 'Just listed',
    desc: 'Sun-filled row house with private garden and renovated kitchen.',
    imageUrl: 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=900&h=680&fit=crop&q=85',
    agentId: 'sarah',
    hoa: '$240/mo',
  },
  {
    id: 'park-view',
    address: 'Park View #4',
    neighborhood: 'Greenpoint',
    price: '$985K',
    beds: 2,
    baths: 2,
    sqft: '1,120',
    tag: 'Open house Sat',
    desc: 'Corner unit with skyline views and in-unit laundry.',
    imageUrl: 'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=900&h=680&fit=crop&q=85',
    agentId: 'elena',
    hoa: '$310/mo',
  },
  {
    id: 'river-loft',
    address: '15 River Loft',
    neighborhood: 'DUMBO',
    price: '$1.65M',
    beds: 2,
    baths: 2,
    sqft: '1,450',
    desc: 'Exposed brick loft — two blocks from the park.',
    imageUrl: 'https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?w=900&h=680&fit=crop&q=85',
    agentId: 'marcus',
  },
  {
    id: 'cedar-townhouse',
    address: '8 Cedar Row',
    neighborhood: 'Bed-Stuy',
    price: '$1.42M',
    beds: 4,
    baths: 3,
    sqft: '2,100',
    tag: 'Price reduced',
    desc: 'Four-story brownstone with rental income potential.',
    imageUrl: 'https://images.unsplash.com/photo-1605276374104-dee2cfbaecff?w=900&h=680&fit=crop&q=85',
    agentId: 'sarah',
  },
];

export const VIEWING_SLOTS: ViewingSlot[] = [
  { id: 'sat-oak-10', label: 'Sat 10:00 AM · 22 Oak Lane', day: 'Saturday', time: '10:00 AM', listingId: 'oak-lane', agentId: 'sarah' },
  { id: 'sat-park-1130', label: 'Sat 11:30 AM · Park View #4', day: 'Saturday', time: '11:30 AM', listingId: 'park-view', agentId: 'elena' },
  { id: 'sat-river-2', label: 'Sat 2:00 PM · River Loft', day: 'Saturday', time: '2:00 PM', listingId: 'river-loft', agentId: 'marcus' },
  { id: 'sun-oak-1', label: 'Sun 1:00 PM · 22 Oak Lane', day: 'Sunday', time: '1:00 PM', listingId: 'oak-lane', agentId: 'sarah' },
];

export const CRM_LEADS: Lead[] = [
  { id: '1', name: 'Alex P.', source: 'Listing AI', listing: '22 Oak Lane', score: 'hot', budget: '$1.2–1.4M', lastActivity: 'Booked viewing' },
  { id: '2', name: 'Nina S.', source: 'WhatsApp', listing: 'Park View #4', score: 'hot', budget: '$950K–1M', lastActivity: 'Confirmed Sat' },
  { id: '3', name: 'James L.', source: 'Zillow sync', listing: 'River Loft', score: 'warm', budget: '$1.5M+', lastActivity: 'Asked HOA' },
  { id: '4', name: 'Priya K.', source: 'Open house', listing: 'Cedar Row', score: 'warm', budget: '$1.3–1.5M', lastActivity: 'Tour recap sent' },
];

export const TODAY_VIEWINGS = [
  { time: '10:00 AM', buyer: 'Alex P.', listing: '22 Oak Lane', agent: 'Sarah Chen', status: 'confirmed' as const },
  { time: '11:30 AM', buyer: 'Nina S.', listing: 'Park View #4', agent: 'Elena Ruiz', status: 'confirmed' as const },
  { time: '2:00 PM', buyer: 'James L.', listing: 'River Loft', agent: 'Marcus Webb', status: 'pending' as const },
  { time: '4:30 PM', buyer: 'Walk-in', listing: 'Cedar Row', agent: 'Sarah Chen', status: 'open' as const },
];

export function slotsForListing(listingId: string): ViewingSlot[] {
  return VIEWING_SLOTS.filter((s) => s.listingId === listingId);
}

export function getListing(id: string): Listing | undefined {
  return LISTINGS.find((l) => l.id === id);
}

export function getAgent(id: string): Agent | undefined {
  return AGENTS.find((a) => a.id === id);
}
