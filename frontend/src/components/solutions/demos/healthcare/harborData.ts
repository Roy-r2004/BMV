/** Shared clinic data — admin configures this; other apps consume it. */

export type Room = {
  id: string;
  name: string;
  purpose: string;
  equipment: string[];
  createdBy: string;
  createdAt: string;
  status: 'active' | 'maintenance';
};

export type Practitioner = {
  id: string;
  name: string;
  title: string;
  specialties: string[];
  bio: string;
  photoInitial: string;
  imageUrl: string;
  visibleOnWebsite: boolean;
};

export type Treatment = {
  id: string;
  icon: string;
  name: string;
  price: string;
  duration: string;
  tag: string;
  desc: string;
  longDesc: string;
  practitionerIds: string[];
  roomIds: string[];
  published: boolean;
};

export type TimeSlot = {
  id: string;
  label: string;
  day: string;
  time: string;
  treatmentId: string;
  practitionerId: string;
  roomId: string;
};

export type Appointment = {
  time: string;
  patient: string;
  service: string;
  practitionerId: string;
  roomId: string;
  durationMin: number;
  status: 'checked-in' | 'confirmed' | 'new' | 'open' | 'pending';
};

export const CLINIC = {
  name: 'Harbor Wellness',
  tagline: 'Clinical aesthetics & wellness',
  address: '284 Harbor View Dr, Suite 200',
  city: 'San Diego, CA 92101',
  phone: '(619) 555-0142',
  email: 'hello@harborwellness.com',
  heroImage: 'https://images.unsplash.com/photo-1629909613654-28e377c01b09?w=800&h=600&fit=crop&q=80',
  clinicImage: 'https://images.unsplash.com/photo-1586773860418-d37222d8fce3?w=400&h=280&fit=crop&q=75',
  hours: [
    { days: 'Mon – Fri', time: '8:00 AM – 6:00 PM' },
    { days: 'Sat', time: '9:00 AM – 2:00 PM' },
    { days: 'Sun', time: 'Closed' },
  ],
};

export const ROOMS: Room[] = [
  {
    id: 'room-1',
    name: 'Consult Suite A',
    purpose: 'Injectables & consults',
    equipment: ['Exam chair', 'Digital mapping camera', 'Cold storage'],
    createdBy: 'Maya R. (Office Manager)',
    createdAt: 'Mar 12, 2025',
    status: 'active',
  },
  {
    id: 'room-2',
    name: 'Treatment Room 2',
    purpose: 'Hydrafacial & skin treatments',
    equipment: ['Hydrafacial MD', 'LED panel', 'Sterilization station'],
    createdBy: 'Maya R. (Office Manager)',
    createdAt: 'Mar 12, 2025',
    status: 'active',
  },
  {
    id: 'room-3',
    name: 'IV Lounge',
    purpose: 'Wellness drips & recovery',
    equipment: ['Recliners (×3)', 'Vital monitors', 'Pharmacy fridge'],
    createdBy: 'Dr. Chen (Medical Director)',
    createdAt: 'Apr 3, 2025',
    status: 'active',
  },
];

export const PRACTITIONERS: Practitioner[] = [
  {
    id: 'chen',
    name: 'Dr. Elena Chen',
    title: 'Medical Director',
    specialties: ['Botox', 'Fillers', 'Laser consults'],
    bio: 'Board-certified dermatologist with 12 years in medical aesthetics. Patients know her for precise, natural results.',
    photoInitial: 'E',
    imageUrl: 'https://images.unsplash.com/photo-1594824476967-48c8b964273f?w=320&h=400&fit=crop&q=75',
    visibleOnWebsite: true,
  },
  {
    id: 'patel',
    name: 'Dr. Arjun Patel',
    title: 'Aesthetic Physician',
    specialties: ['Laser resurfacing', 'Skin rejuvenation'],
    bio: 'Specializes in fractional laser and combination protocols for texture and tone.',
    photoInitial: 'A',
    imageUrl: 'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?w=320&h=400&fit=crop&q=75',
    visibleOnWebsite: true,
  },
  {
    id: 'nurse-kim',
    name: 'Jess Kim, RN',
    title: 'Lead Nurse Injector',
    specialties: ['IV therapy', 'Hydrafacial', 'Patient education'],
    bio: 'Runs treatment Room 2 and the IV lounge. Known for calm, thorough pre-visit prep.',
    photoInitial: 'J',
    imageUrl: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=320&h=400&fit=crop&q=75',
    visibleOnWebsite: true,
  },
];

export const TREATMENTS: Treatment[] = [
  {
    id: 'hydra',
    icon: '✦',
    name: 'Hydrafacial',
    price: '$189',
    duration: '45 min',
    tag: 'Most booked',
    desc: 'Deep cleanse, extract, hydrate — zero downtime glow.',
    longDesc: 'Our signature Hydrafacial uses vortex technology to cleanse, extract, and infuse serums tailored to your skin. Ideal before events or as monthly maintenance. Performed in Treatment Room 2.',
    practitionerIds: ['nurse-kim'],
    roomIds: ['room-2'],
    published: true,
  },
  {
    id: 'botox',
    icon: '◆',
    name: 'Botox consult',
    price: 'From $420',
    duration: '30 min',
    tag: 'AI pre-screen',
    desc: 'Virtual consult + in-clinic mapping with Dr. Chen.',
    longDesc: 'Initial consult includes facial mapping, medical history review, and a personalized treatment plan. AI intake collects history before you arrive so your visit focuses on care.',
    practitionerIds: ['chen'],
    roomIds: ['room-1'],
    published: true,
  },
  {
    id: 'iv',
    icon: '◇',
    name: 'IV wellness drip',
    price: '$240',
    duration: '60 min',
    tag: 'Same-day',
    desc: 'Energy, immunity, or recovery — nurse-administered.',
    longDesc: 'Choose from immunity, hydration, or recovery blends. Administered in our IV Lounge with continuous monitoring. Same-day slots often available.',
    practitionerIds: ['nurse-kim'],
    roomIds: ['room-3'],
    published: true,
  },
  {
    id: 'laser',
    icon: '◎',
    name: 'Laser resurfacing',
    price: 'From $680',
    duration: '90 min',
    tag: 'Consult first',
    desc: 'Fractional treatment for texture, scars, and tone.',
    longDesc: 'Requires an initial consult with Dr. Patel to assess fit and downtime. Treatment sessions use Consult Suite A equipment.',
    practitionerIds: ['patel', 'chen'],
    roomIds: ['room-1'],
    published: true,
  },
];

export const BOOKING_SLOTS: TimeSlot[] = [
  {
    id: 'slot-1',
    label: 'Thu 2:30 PM · Dr. Chen · Consult Suite A',
    day: 'Thursday',
    time: '2:30 PM',
    treatmentId: 'botox',
    practitionerId: 'chen',
    roomId: 'room-1',
  },
  {
    id: 'slot-2',
    label: 'Thu 4:00 PM · Dr. Chen · Consult Suite A',
    day: 'Thursday',
    time: '4:00 PM',
    treatmentId: 'botox',
    practitionerId: 'chen',
    roomId: 'room-1',
  },
  {
    id: 'slot-3',
    label: 'Fri 11:00 AM · Jess Kim · Treatment Room 2',
    day: 'Friday',
    time: '11:00 AM',
    treatmentId: 'hydra',
    practitionerId: 'nurse-kim',
    roomId: 'room-2',
  },
];

export const TODAY_APPOINTMENTS: Appointment[] = [
  { time: '9:00', patient: 'Maria K.', service: 'Hydrafacial', practitionerId: 'nurse-kim', roomId: 'room-2', durationMin: 75, status: 'checked-in' },
  { time: '10:30', patient: 'David P.', service: 'Consult', practitionerId: 'chen', roomId: 'room-1', durationMin: 30, status: 'confirmed' },
  { time: '14:00', patient: 'Sarah M.', service: 'Botox consult', practitionerId: 'chen', roomId: 'room-1', durationMin: 45, status: 'new' },
  { time: '15:30', patient: '—', service: 'Open slot', practitionerId: 'patel', roomId: 'room-3', durationMin: 45, status: 'open' },
  { time: '11:00', patient: 'Emma R.', service: 'IV therapy', practitionerId: 'nurse-kim', roomId: 'room-3', durationMin: 60, status: 'confirmed' },
  { time: '16:00', patient: 'Lisa T.', service: 'Follow-up', practitionerId: 'chen', roomId: 'room-1', durationMin: 30, status: 'confirmed' },
  { time: '17:30', patient: 'James L.', service: 'Hydrafacial', practitionerId: 'nurse-kim', roomId: 'room-2', durationMin: 75, status: 'pending' },
];

export function getPractitioner(id: string) {
  return PRACTITIONERS.find((p) => p.id === id);
}

export function getRoom(id: string) {
  return ROOMS.find((r) => r.id === id);
}

export function getTreatment(id: string) {
  return TREATMENTS.find((t) => t.id === id);
}

export function practitionerLabel(id: string) {
  const p = getPractitioner(id);
  return p?.name.replace('Dr. ', 'Dr. ').replace(', RN', '') ?? id;
}

export function roomLabel(id: string) {
  return getRoom(id)?.name ?? id;
}

export function slotsForTreatment(treatmentId: string) {
  return BOOKING_SLOTS.filter((s) => s.treatmentId === treatmentId);
}

export const PUBLISHED_TREATMENTS = TREATMENTS.filter((t) => t.published);
export const WEBSITE_TEAM = PRACTITIONERS.filter((p) => p.visibleOnWebsite);
