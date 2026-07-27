export const brand = {
  name: 'Preview Brand',
  tagline: 'Your product preview',
};

export const images = {
  hero: 'https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=1600&q=80&fit=crop&auto=format',
  card1: 'https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=800&q=80&fit=crop&auto=format',
  card2: 'https://images.unsplash.com/photo-1616394584738-fc6e612e71b9?w=800&q=80&fit=crop&auto=format',
  card3: 'https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?w=800&q=80&fit=crop&auto=format',
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
    eyebrow: 'Preview Brand',
    headline: '',
    subcopy: 'A clear next step from Preview Brand — warm, specific, and ready when you are.',
    primaryCta: { label: 'Explore now', href: '#details' },
    secondaryCta: { label: 'See how it works', href: '#process' },
  },
  items: [
    { title: 'Preview Brand signature', description: 'A dependable starting point at Preview Brand.' },
    { title: 'Everyday essential', description: 'Built for daily use.' },
  ],
  features: [
    { title: 'What Preview Brand is known for', description: 'Concrete offerings guests can book without guessing.' },
    { title: 'Guided next step', description: 'Every section points toward a clear action.' },
  ],
  process: [
    { title: 'Choose', description: 'Find the right option at Preview Brand.' },
    { title: 'Confirm', description: 'Select a convenient time.' },
    { title: 'Enjoy', description: 'We take care of the details.' },
  ],
  credentials: [
    { title: 'Known locally', detail: 'Neighbors recommend Preview Brand for consistent results.' },
    { title: 'Clear next steps', detail: 'Booking and follow-up stay simple from the start.' },
  ],
  testimonials: [
    {
      quote: 'Clear, warm, and easy — exactly what I wanted from Preview Brand.',
      author: 'A returning client',
      role: 'Verified guest',
    },
  ],
  treatments: [{ id: 'offer-1', name: 'Preview Brand signature', duration: '60 min' }],
  showcaseHeading: 'From Preview Brand',
  featuresHeading: 'What Preview Brand offers',
  processHeading: 'How Preview Brand works',
  credentialsHeading: 'Why Preview Brand',
  testimonialsHeading: 'Guests of Preview Brand',
  cta: {
    heading: 'Ready for Preview Brand?',
    description: 'Tell Preview Brand what you need — clear options, real next steps.',
    primaryLabel: 'Get started',
    primaryHref: '#details',
    secondaryLabel: 'Talk to us',
    secondaryHref: '#contact',
  },
  footer: { description: 'Preview Brand — clear choices and real bookings.' },
  trustLabels: ['Preview Brand quality', 'On schedule', 'Repeat guests', 'Local favorite'],
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
