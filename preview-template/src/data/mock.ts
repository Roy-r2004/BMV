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
