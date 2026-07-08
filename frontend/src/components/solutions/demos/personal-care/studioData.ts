/** Shared Studio Nine data — owner hub configures; other apps consume it. */

export type Chair = {
  id: string;
  name: string;
  barberId: string;
  equipment: string[];
  status: 'active' | 'maintenance';
};

export type Barber = {
  id: string;
  name: string;
  title: string;
  specialties: string[];
  bio: string;
  photoInitial: string;
  imageUrl: string;
  visibleOnWebsite: boolean;
};

export type Service = {
  id: string;
  icon: string;
  name: string;
  price: string;
  duration: string;
  tag: string;
  desc: string;
  longDesc: string;
  barberIds: string[];
  published: boolean;
};

export type TimeSlot = {
  id: string;
  label: string;
  day: string;
  time: string;
  serviceId: string;
  barberId: string;
  chairId: string;
};

export type Booking = {
  time: string;
  client: string;
  service: string;
  barberId: string;
  chairId: string;
  durationMin: number;
  status: 'checked-in' | 'confirmed' | 'new' | 'open' | 'pending';
};

export const SALON = {
  name: 'Studio Nine',
  tagline: 'Premium cuts · Downtown',
  address: '142 Mercer Street',
  city: 'Brooklyn, NY 11211',
  phone: '(718) 555-0192',
  email: 'book@studionine.app',
  heroImage: 'https://images.unsplash.com/photo-1622286342621-4bd786c2447c?auto=format&w=1200&h=800&fit=crop&q=80',
  shopImage: 'https://images.unsplash.com/photo-1585747860715-2ba37e788b70?auto=format&w=800&h=560&fit=crop&q=80',
  hours: [
    { days: 'Tue – Fri', time: '10:00 AM – 8:00 PM' },
    { days: 'Sat', time: '9:00 AM – 6:00 PM' },
    { days: 'Sun – Mon', time: 'Closed' },
  ],
};

export const CHAIRS: Chair[] = [
  { id: 'chair-1', name: 'Chair 1', barberId: 'marcus', equipment: ['Premium clippers', 'Hot towel station'], status: 'active' },
  { id: 'chair-2', name: 'Chair 2', barberId: 'jay', equipment: ['Straight razor kit', 'Beard sculpt tools'], status: 'active' },
  { id: 'chair-3', name: 'Chair 3', barberId: 'alex', equipment: ['Skin fade station', 'Line-up mirror'], status: 'active' },
];

export const BARBERS: Barber[] = [
  {
    id: 'marcus',
    name: 'Marcus Reid',
    title: 'Owner · Master Barber',
    specialties: ['Skin fades', 'Classic cuts', 'VIP clients'],
    bio: 'Founded Studio Nine in 2018. Known for sharp fades and knowing every regular by name.',
    photoInitial: 'M',
    imageUrl: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&w=400&h=500&fit=crop&q=80',
    visibleOnWebsite: true,
  },
  {
    id: 'jay',
    name: 'Jay Ortiz',
    title: 'Senior Barber',
    specialties: ['Beard sculpt', 'Cut + beard', 'Hot towel'],
    bio: 'Ten years in the chair. Clients book Jay for the full groom experience.',
    photoInitial: 'J',
    imageUrl: 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400&h=500&fit=crop&q=80',
    visibleOnWebsite: true,
  },
  {
    id: 'alex',
    name: 'Alex Kim',
    title: 'Barber · Style specialist',
    specialties: ['Textured crops', 'Design lines', 'Walk-ins'],
    bio: 'Fast, precise, and great with first-timers. Handles most afternoon walk-ins.',
    photoInitial: 'A',
    imageUrl: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&w=400&h=500&fit=crop&q=80',
    visibleOnWebsite: true,
  },
];

export const SERVICES: Service[] = [
  {
    id: 'fade',
    icon: '✂',
    name: 'Skin fade',
    price: '$38',
    duration: '45 min',
    tag: 'Most booked',
    desc: 'Tapered fade with line-up — your barber remembers your usual.',
    longDesc: 'Our signature skin fade includes consult, wash optional, precision fade, and line-up. AI booking remembers your preferred barber and guard length.',
    barberIds: ['marcus', 'alex'],
    published: true,
  },
  {
    id: 'combo',
    icon: '◆',
    name: 'Cut + beard',
    price: '$55',
    duration: '60 min',
    tag: 'Full groom',
    desc: 'Haircut and beard sculpt — hot towel finish.',
    longDesc: 'Full service with Jay or Marcus. Includes beard outline, hot towel, and styling product. Most popular on weekends.',
    barberIds: ['jay', 'marcus'],
    published: true,
  },
  {
    id: 'vip',
    icon: '★',
    name: 'VIP slot',
    price: '$65',
    duration: '45 min',
    tag: 'Priority',
    desc: 'Skip the wait — loyalty tracked automatically.',
    longDesc: 'Reserved chair time for regulars. Includes priority rebooking and style notes saved to your profile.',
    barberIds: ['marcus'],
    published: true,
  },
  {
    id: 'kids',
    icon: '◇',
    name: 'Kids cut',
    price: '$28',
    duration: '30 min',
    tag: 'Under 12',
    desc: 'Patient cuts for the little ones.',
    longDesc: 'Before-school and weekend slots. Alex specializes in first haircuts.',
    barberIds: ['alex'],
    published: true,
  },
];

export const BOOKING_SLOTS: TimeSlot[] = [
  { id: 'slot-1', label: 'Thu 5:15 PM · Jay · Chair 2', day: 'Thursday', time: '5:15 PM', serviceId: 'fade', barberId: 'jay', chairId: 'chair-2' },
  { id: 'slot-2', label: 'Thu 6:00 PM · Jay · Chair 2', day: 'Thursday', time: '6:00 PM', serviceId: 'fade', barberId: 'jay', chairId: 'chair-2' },
  { id: 'slot-3', label: 'Fri 11:30 AM · Marcus · Chair 1', day: 'Friday', time: '11:30 AM', serviceId: 'combo', barberId: 'marcus', chairId: 'chair-1' },
];

export const TODAY_BOOKINGS: Booking[] = [
  { time: '11:00', client: 'Alex R.', service: 'Skin fade', barberId: 'marcus', chairId: 'chair-1', durationMin: 45, status: 'checked-in' },
  { time: '12:30', client: 'Jordan P.', service: 'Cut + beard', barberId: 'jay', chairId: 'chair-2', durationMin: 60, status: 'confirmed' },
  { time: '14:00', client: 'Mike T.', service: 'Skin fade', barberId: 'jay', chairId: 'chair-2', durationMin: 45, status: 'new' },
  { time: '15:00', client: '—', service: 'Open slot', barberId: 'alex', chairId: 'chair-3', durationMin: 45, status: 'open' },
  { time: '16:30', client: 'Chris D.', service: 'VIP slot', barberId: 'marcus', chairId: 'chair-1', durationMin: 45, status: 'confirmed' },
  { time: '17:15', client: 'Mike T.', service: 'Skin fade', barberId: 'jay', chairId: 'chair-2', durationMin: 45, status: 'pending' },
  { time: '18:00', client: 'Devon S.', service: 'Kids cut', barberId: 'alex', chairId: 'chair-3', durationMin: 30, status: 'confirmed' },
];

export function getBarber(id: string) {
  return BARBERS.find((b) => b.id === id);
}

export function getChair(id: string) {
  return CHAIRS.find((c) => c.id === id);
}

export function getService(id: string) {
  return SERVICES.find((s) => s.id === id);
}

export function slotsForService(serviceId: string) {
  return BOOKING_SLOTS.filter((s) => s.serviceId === serviceId);
}

export const PUBLISHED_SERVICES = SERVICES.filter((s) => s.published);
export const WEBSITE_BARBERS = BARBERS.filter((b) => b.visibleOnWebsite);
