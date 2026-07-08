/** Peak Form Studio — gym site, member chat, progress, coach hub */

export type Program = {
  id: string;
  name: string;
  category: string;
  price: string;
  duration: string;
  tag?: string;
  desc: string;
  imageUrl: string;
  coachId: string;
};

export type Coach = {
  id: string;
  name: string;
  title: string;
  specialties: string[];
  bio: string;
  photoInitial: string;
  imageUrl: string;
};

export type ClassSlot = {
  id: string;
  label: string;
  day: string;
  time: string;
  programId: string;
  coachId: string;
};

export type Member = {
  id: string;
  name: string;
  source: string;
  program: string;
  score: 'active' | 'trial' | 'at-risk';
  streak: string;
  lastActivity: string;
};

export const STUDIO = {
  name: 'Peak Form Studio',
  tagline: 'Strength · HIIT · Recovery',
  address: '142 Mercer Street',
  city: 'New York, NY 10012',
  phone: '(212) 555-0142',
  email: 'hello@peakform.app',
  heroImage: 'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=1400&h=900&fit=crop&q=85',
  floorImage: 'https://images.unsplash.com/photo-1571902943202-507ec2618e8f?w=900&h=640&fit=crop&q=85',
  programsHeroImage: 'https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=1400&h=500&fit=crop&q=85',
  trialImage: 'https://images.unsplash.com/photo-1540497077202-7a8b3d6fbaa1?w=900&h=1200&fit=crop&q=85',
};

export const COACHES: Coach[] = [
  {
    id: 'maya',
    name: 'Maya Ortiz',
    title: 'Head coach · HIIT',
    specialties: ['HIIT', 'Metabolic', 'Group energy'],
    bio: 'Former D1 athlete — builds sessions that push limits without burning people out.',
    photoInitial: 'M',
    imageUrl: 'https://images.unsplash.com/photo-1594381898411-8465977db7b3?w=400&h=500&fit=crop&q=80',
  },
  {
    id: 'derek',
    name: 'Derek Shaw',
    title: 'Strength director',
    specialties: ['Powerlifting', 'Hypertrophy', 'Form'],
    bio: 'Twelve years coaching compound lifts — progressive overload with injury prevention.',
    photoInitial: 'D',
    imageUrl: 'https://images.unsplash.com/photo-1567013127542-490d757e51fc?w=400&h=500&fit=crop&q=80',
  },
  {
    id: 'lina',
    name: 'Lina Park',
    title: 'Recovery & mobility',
    specialties: ['Yoga', 'Mobility', 'Breathwork'],
    bio: 'Keeps members moving long-term — flow classes that complement heavy training days.',
    photoInitial: 'L',
    imageUrl: 'https://images.unsplash.com/photo-1518611012118-696072aa579a?w=400&h=500&fit=crop&q=80',
  },
];

export const PROGRAMS: Program[] = [
  {
    id: 'hiit',
    name: 'HIIT Burn',
    category: 'Cardio',
    price: '$28/class',
    duration: '45 min',
    tag: 'Most popular',
    desc: 'Intervals on assault bikes, kettlebells, and sleds — max output, coached rest.',
    imageUrl: 'https://images.unsplash.com/photo-1517838277536-f5f99be501cd?w=900&h=680&fit=crop&q=85',
    coachId: 'maya',
  },
  {
    id: 'strength',
    name: 'Strength Lab',
    category: 'Strength',
    price: '$32/class',
    duration: '60 min',
    desc: 'Squat, bench, deadlift progressions with personalized load prescriptions.',
    imageUrl: 'https://images.unsplash.com/photo-1581009146145-b5ef050c149a?w=900&h=680&fit=crop&q=85',
    coachId: 'derek',
  },
  {
    id: 'yoga',
    name: 'Flow & Recover',
    category: 'Recovery',
    price: '$22/class',
    duration: '50 min',
    desc: 'Active recovery flow — hips, shoulders, and breath for heavy training weeks.',
    imageUrl: 'https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=900&h=680&fit=crop&q=85',
    coachId: 'lina',
  },
  {
    id: 'bootcamp',
    name: 'Saturday Bootcamp',
    category: 'Community',
    price: '$35/class',
    duration: '75 min',
    tag: 'Weekend crew',
    desc: 'Partner workouts, outdoor finishers when weather allows — bring a friend.',
    imageUrl: 'https://images.unsplash.com/photo-1576678927484-cc907957088c?w=900&h=680&fit=crop&q=85',
    coachId: 'maya',
  },
];

export const PROGRAM_SECTIONS = [
  { id: 'cardio', title: 'Cardio & conditioning', items: PROGRAMS.filter((p) => p.category === 'Cardio' || p.category === 'Community') },
  { id: 'strength', title: 'Strength & power', items: PROGRAMS.filter((p) => p.category === 'Strength') },
  { id: 'recovery', title: 'Recovery', items: PROGRAMS.filter((p) => p.category === 'Recovery') },
].filter((s) => s.items.length > 0);

export const CLASS_SLOTS: ClassSlot[] = [
  { id: 'thu-hiit-630', label: 'Thu 6:30 PM · HIIT Burn', day: 'Thursday', time: '6:30 PM', programId: 'hiit', coachId: 'maya' },
  { id: 'thu-strength-730', label: 'Thu 7:30 PM · Strength Lab', day: 'Thursday', time: '7:30 PM', programId: 'strength', coachId: 'derek' },
  { id: 'fri-yoga-630', label: 'Fri 6:30 AM · Flow & Recover', day: 'Friday', time: '6:30 AM', programId: 'yoga', coachId: 'lina' },
  { id: 'sat-boot-9', label: 'Sat 9:00 AM · Bootcamp', day: 'Saturday', time: '9:00 AM', programId: 'bootcamp', coachId: 'maya' },
];

export const HUB_MEMBERS: Member[] = [
  { id: '1', name: 'Jordan K.', source: 'App', program: 'HIIT pass', score: 'active', streak: '12 days', lastActivity: 'Rescheduled Thu HIIT' },
  { id: '2', name: 'Sam L.', source: 'Referral', program: '12-week program', score: 'trial', streak: '3 days', lastActivity: 'Trial check-in' },
  { id: '3', name: 'Priya M.', source: 'Instagram', program: 'Strength Lab', score: 'active', streak: '28 days', lastActivity: 'PR logged' },
  { id: '4', name: 'Chris W.', source: 'Walk-in', program: 'Unlimited', score: 'at-risk', streak: '0 days', lastActivity: 'Missed 2 classes' },
];

export const TODAY_CLASSES = [
  { time: '6:30 AM', member: 'Team flow', program: 'Flow & Recover', coach: 'Lina Park', status: 'open' as const },
  { time: '12:00 PM', member: 'Open gym', program: 'Strength Lab', coach: 'Derek Shaw', status: 'open' as const },
  { time: '6:30 PM', member: 'Jordan K.', program: 'HIIT Burn', coach: 'Maya Ortiz', status: 'confirmed' as const },
  { time: '7:30 PM', member: '4 spots left', program: 'Strength Lab', coach: 'Derek Shaw', status: 'pending' as const },
];

export const WEEKLY_PROGRESS = [
  { day: 'Mon', workouts: 1, goal: 1, active: false },
  { day: 'Tue', workouts: 1, goal: 1, active: false },
  { day: 'Wed', workouts: 0, goal: 1, active: false },
  { day: 'Thu', workouts: 1, goal: 1, active: true },
  { day: 'Fri', workouts: 0, goal: 1, active: false },
  { day: 'Sat', workouts: 0, goal: 1, active: false },
  { day: 'Sun', workouts: 0, goal: 1, active: false },
];

export function slotsForProgram(programId: string): ClassSlot[] {
  return CLASS_SLOTS.filter((s) => s.programId === programId);
}

export function getProgram(id: string): Program | undefined {
  return PROGRAMS.find((p) => p.id === id);
}

export function getCoach(id: string): Coach | undefined {
  return COACHES.find((c) => c.id === id);
}
