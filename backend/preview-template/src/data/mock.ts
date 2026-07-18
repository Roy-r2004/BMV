export const brand = {
  name: 'Preview Brand',
  tagline: 'Your product preview',
};

export const images = {
  hero: 'https://images.unsplash.com/photo-1570172619644-dfd955edfc01?w=1600&q=80',
  card1: 'https://images.unsplash.com/photo-1512290923902-8a9f81dc2369?w=800&q=80',
  card2: 'https://images.unsplash.com/photo-1616394584738-fc6e612e71b9?w=800&q=80',
  card3: 'https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=800&q=80',
};

/** Role switcher metadata — AI rewrites ids, labels, and default landing paths */
export const roles = [
  { id: 'customer', label: 'Customer', defaultPath: '/', icon: 'users' as const },
  { id: 'owner', label: 'Admin', defaultPath: '/admin', icon: 'chart' as const },
];

/** Nav links per shell — MUST stay in sync with App.tsx routes */
export const navigation = {
  public: [
    { path: '/', label: 'Home' },
    { path: '/services', label: 'Services' },
  ],
  admin: [
    { path: '/admin', label: 'Overview' },
    { path: '/admin/appointments', label: 'Appointments' },
  ],
};

/** Industry template seed — generation overwrites this from the pack mock_seed. */
export const seed = {
  tone: 'branded',
  hero: {
    headline: '',
    subcopy: 'Cinematic first impression — brand-forward, vivid, and ready for the next step.',
    primaryCta: { label: 'Explore now', href: '#details' },
    secondaryCta: { label: 'See how it works', href: '#process' },
  },
  items: [
    { title: 'Signature offering', description: 'A dependable starting point.' },
    { title: 'Everyday essential', description: 'Built for daily use.' },
  ],
  features: [
    { title: 'Immersive first view', description: 'Atmosphere and brand color from the first scroll.' },
    { title: 'Guided next step', description: 'Every section pushes toward a clear action.' },
  ],
  process: [
    { title: 'Choose', description: 'Find the right option.' },
    { title: 'Confirm', description: 'Select a convenient time.' },
    { title: 'Enjoy', description: 'We take care of the details.' },
  ],
  credentials: [
    { title: 'Brand-first chrome', detail: 'Every surface carries your color and type.' },
    { title: 'Motion with purpose', detail: 'Kenburns, reveals, and lifts — never static.' },
  ],
  testimonials: [
    { quote: 'Clear, warm, and easy from start to finish.', author: 'A returning client', role: 'Verified guest' },
  ],
  treatments: [{ id: 'offer-1', name: 'Signature offering', duration: '60 min' }],
  showcaseHeading: 'Featured experiences',
  featuresHeading: 'Designed to feel alive',
  processHeading: 'How it works',
  credentialsHeading: 'Why it stands out',
  testimonialsHeading: 'What clients say',
  cta: {
    heading: 'Make it unforgettable',
    description: 'Book the next chapter — polished, branded, never bland.',
    primaryLabel: 'Get started',
    primaryHref: '#details',
    secondaryLabel: 'Talk to us',
    secondaryHref: '#contact',
  },
  footer: { description: 'Premium presence from first glance to booked revenue.' },
  trustLabels: ['Signature craft', 'On-time delivery', 'Repeat guests', 'Local favorite'],
};

export const services = [
  { id: '1', name: 'Service One', description: 'Description', duration: '60 min' },
  { id: '2', name: 'Service Two', description: 'Description', duration: '45 min' },
];

export const appointments = [
  { id: '1', client: 'Alex M.', service: 'Consultation', time: 'Today 2:00 PM', status: 'confirmed' as const },
  { id: '2', client: 'Jordan K.', service: 'Follow-up', time: 'Tomorrow 10:30 AM', status: 'pending' as const },
];

export const stats = [
  { label: 'Bookings', value: '128', change: '+12%' },
  { label: 'Clients', value: '84', change: '+8%' },
  { label: 'Revenue', value: '42k', change: '+15%' },
  { label: 'Satisfaction', value: '98%', change: '+2%' },
];
