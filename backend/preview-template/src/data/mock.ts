export const brand = {
  name: 'Preview Brand',
  tagline: 'Your product preview',
};

export const images = {
  hero: 'https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=1600&q=80&fit=crop&auto=format',
  card1: 'https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=800&q=80&fit=crop&auto=format',
  card2: 'https://images.unsplash.com/photo-1616394584738-fc6e612e71b9?w=800&q=80&fit=crop&auto=format',
  card3: 'https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?w=800&q=80&fit=crop&auto=format',
  // Per-item photography. A generated workspace has these filled from the item
  // pool, but the deterministic scaffolds read `images.item1…item8` directly —
  // so without them declared here the template does not typecheck against the
  // code the generator writes, and `test_catalogue_fallback_typechecks_with_
  // template` is the only place that ever notices.
  item1: 'https://images.unsplash.com/photo-1578321272176-b7bbc0679853?w=800&q=80&fit=crop&auto=format',
  item2: 'https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5?w=800&q=80&fit=crop&auto=format',
  item3: 'https://images.unsplash.com/photo-1549289524-06cf8837ace5?w=800&q=80&fit=crop&auto=format',
  item4: 'https://images.unsplash.com/photo-1552083375-1447ce886485?w=800&q=80&fit=crop&auto=format',
  item5: 'https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=800&q=80&fit=crop&auto=format',
  item6: 'https://images.unsplash.com/photo-1513519245088-0e12902e5a38?w=800&q=80&fit=crop&auto=format',
  item7: 'https://images.unsplash.com/photo-1519681393784-d120267933ba?w=800&q=80&fit=crop&auto=format',
  item8: 'https://images.unsplash.com/photo-1470770841072-f978cf4d019e?w=800&q=80&fit=crop&auto=format',
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
    // Both of these used to be `/gallery` and `/contact#inquire` — neither of
    // which `navigation` above declares, so the template shipped two dead CTAs
    // by construction, and "the collection" named an artifact type no generic
    // preview has. A default may only point where the default routes go.
    primaryCta: { label: 'Services', href: '/services' },
    secondaryCta: { label: 'See what we offer', href: '/' },
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
    primaryHref: '/contact#inquire',
    secondaryLabel: 'Talk to us',
    secondaryHref: '/contact#inquire',
  },
  footer: { description: 'Preview Brand — clear choices and a real next step.' },
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
