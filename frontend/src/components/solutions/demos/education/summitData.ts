/** Shared Summit Tutoring data — hub configures; other apps consume it. */

export type Subject = {
  id: string;
  name: string;
  icon: string;
  levels: string[];
  desc: string;
  blurb: string;
  artUrl: string;
  accent: string;
};

export type Tutor = {
  id: string;
  name: string;
  title: string;
  subjects: string[];
  levels: string[];
  specialties: string[];
  bio: string;
  photoInitial: string;
  imageUrl: string;
  matchScore?: number;
  sessionsThisWeek: number;
  rating: number;
  visibleOnWebsite: boolean;
};

export type SessionSlot = {
  id: string;
  label: string;
  day: string;
  time: string;
  subjectId: string;
  level: string;
  tutorId: string;
  studentId: string;
  durationMin: number;
  status: 'scheduled' | 'completed' | 'prep-sent';
  materials: PrepMaterial[];
};

export type PrepMaterial = {
  id: string;
  name: string;
  type: 'worksheet' | 'video' | 'quiz' | 'reading';
  sentAt?: string;
};

export type Student = {
  id: string;
  name: string;
  grade: string;
  parentName: string;
  subjects: string[];
  progress: number;
  sessionsCompleted: number;
  packageId: string;
  tutorId: string;
};

export type Package = {
  id: string;
  name: string;
  sessions: number;
  price: string;
  renewsOn?: string;
  status: 'active' | 'renewal-due' | 'expired';
};

export type InboxThread = {
  id: string;
  name: string;
  role: 'parent' | 'student';
  preview: string;
  time: string;
  unread: boolean;
  avatar: string;
  subject: string;
};

export const SUMMIT = {
  name: 'Summit Tutoring',
  brand: 'Summit',
  tagline: 'Results-driven · K–12 & test prep',
  address: '88 Academic Row',
  city: 'Boston, MA 02108',
  phone: '(617) 555-0142',
  email: 'hello@summitlearn.app',
  heroImage: 'https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&w=1200&h=800&fit=crop&q=80',
  studyImage: 'https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&w=800&h=560&fit=crop&q=80',
  hours: [
    { days: 'Mon – Fri', time: '3:00 PM – 8:00 PM' },
    { days: 'Sat', time: '10:00 AM – 4:00 PM' },
    { days: 'Sun', time: 'Closed' },
  ],
};

/** Canonical level names — subjects, tutors, and slots must use these exact strings. */
export const SUBJECTS: Subject[] = [
  {
    id: 'math',
    name: 'Mathematics',
    icon: '∑',
    levels: ['Middle school', 'Algebra I', 'Algebra II', 'Pre-calc', 'AP Calculus'],
    desc: 'Concept mastery through worked examples and adaptive practice.',
    blurb: 'From fractions to AP Calc — matched by level, not waitlist.',
    artUrl: 'https://images.unsplash.com/photo-1635070041078-e363dbe005cb?auto=format&w=800&h=520&fit=crop&q=80',
    accent: '#0891b2',
  },
  {
    id: 'science',
    name: 'Science',
    icon: '⚗',
    levels: ['Middle school', 'Biology', 'Chemistry', 'AP Physics'],
    desc: 'Lab prep, concept maps, and exam-style problem sets.',
    blurb: 'Lab-ready tutoring with materials before every session.',
    artUrl: 'https://images.unsplash.com/photo-1532094349884-543bc11b234d?auto=format&w=800&h=520&fit=crop&q=80',
    accent: '#0e7490',
  },
  {
    id: 'english',
    name: 'English & Writing',
    icon: '✎',
    levels: ['Reading comp', 'Essay writing', 'AP Lang', 'SAT verbal'],
    desc: 'Thesis coaching, grammar drills, and timed essay practice.',
    blurb: 'Essay frameworks and timed drills that stick.',
    artUrl: 'https://images.unsplash.com/photo-1456513080880-7d93aaa2ba70?auto=format&w=800&h=520&fit=crop&q=80',
    accent: '#06b6d4',
  },
  {
    id: 'testprep',
    name: 'Test prep',
    icon: '◈',
    levels: ['SAT', 'ACT', 'SSAT', 'ISEE'],
    desc: 'Strategy sessions, full-length mocks, and score tracking.',
    blurb: 'Diagnostic-to-score roadmaps with weekly mocks.',
    artUrl: 'https://images.unsplash.com/photo-1606326608606-aa0b62935f2b?auto=format&w=800&h=520&fit=crop&q=80',
    accent: '#155e75',
  },
];

export const TUTORS: Tutor[] = [
  {
    id: 'elena',
    name: 'Dr. Elena Ruiz',
    title: 'Lead Math · AP specialist',
    subjects: ['math', 'testprep'],
    levels: ['Algebra I', 'Algebra II', 'Pre-calc', 'AP Calculus', 'SAT'],
    specialties: ['Systems of equations', 'SAT math', 'AP Calc AB/BC'],
    bio: 'MIT PhD. 12 years tutoring — students average +180 SAT math points.',
    photoInitial: 'E',
    imageUrl: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&w=400&h=500&fit=crop&q=80',
    sessionsThisWeek: 14,
    rating: 4.9,
    visibleOnWebsite: true,
  },
  {
    id: 'marcus',
    name: 'Marcus Chen',
    title: 'Science · Chemistry focus',
    subjects: ['science', 'math'],
    levels: ['Middle school', 'Biology', 'Chemistry', 'AP Physics', 'Algebra I'],
    specialties: ['Stoichiometry', 'Lab prep', 'Visual models'],
    bio: 'Former lab TA. Makes stoichiometry click with visual models.',
    photoInitial: 'M',
    imageUrl: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&w=400&h=500&fit=crop&q=80',
    sessionsThisWeek: 11,
    rating: 4.8,
    visibleOnWebsite: true,
  },
  {
    id: 'priya',
    name: 'Priya Nair',
    title: 'English · Essay coach',
    subjects: ['english', 'testprep'],
    levels: ['Essay writing', 'AP Lang', 'SAT verbal', 'ACT', 'Reading comp'],
    specialties: ['Thesis frameworks', 'Timed essays', 'AP Lang rhetoric'],
    bio: 'Published editor. Students leave with reusable essay frameworks.',
    photoInitial: 'P',
    imageUrl: 'https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&w=400&h=500&fit=crop&q=80',
    sessionsThisWeek: 9,
    rating: 5.0,
    visibleOnWebsite: true,
  },
  {
    id: 'james',
    name: 'James Okonkwo',
    title: 'Test prep · Strategy lead',
    subjects: ['testprep', 'math'],
    levels: ['SAT', 'ACT', 'SSAT', 'ISEE', 'Algebra II'],
    specialties: ['Full-length mocks', 'Timing strategy', 'Score roadmaps'],
    bio: 'Full-time prep coach. Diagnostic-to-score roadmap in 8 weeks.',
    photoInitial: 'J',
    imageUrl: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&w=400&h=500&fit=crop&q=80',
    sessionsThisWeek: 16,
    rating: 4.9,
    visibleOnWebsite: true,
  },
];

export const STUDENTS: Student[] = [
  { id: 's1', name: 'Ava M.', grade: '10th', parentName: 'Sarah M.', subjects: ['math'], progress: 78, sessionsCompleted: 12, packageId: 'pkg-12', tutorId: 'elena' },
  { id: 's2', name: 'Noah K.', grade: '8th', parentName: 'David K.', subjects: ['science'], progress: 62, sessionsCompleted: 6, packageId: 'pkg-8', tutorId: 'marcus' },
  { id: 's3', name: 'Mia T.', grade: '11th', parentName: 'Lisa T.', subjects: ['english', 'testprep'], progress: 91, sessionsCompleted: 18, packageId: 'pkg-20', tutorId: 'priya' },
  { id: 's4', name: 'Ethan R.', grade: '12th', parentName: 'Karen R.', subjects: ['testprep'], progress: 55, sessionsCompleted: 4, packageId: 'pkg-8', tutorId: 'james' },
];

export const PACKAGES: Package[] = [
  { id: 'pkg-8', name: '8-session pack', sessions: 8, price: '$720', renewsOn: 'Mar 14', status: 'renewal-due' },
  { id: 'pkg-12', name: '12-session pack', sessions: 12, price: '$1,020', status: 'active' },
  { id: 'pkg-20', name: '20-session pack', sessions: 20, price: '$1,600', status: 'active' },
];

export const BOOKING_SLOTS: SessionSlot[] = [
  {
    id: 'slot-1',
    label: 'Thu 4:30 PM · Elena · Algebra II',
    day: 'Thursday',
    time: '4:30 PM',
    subjectId: 'math',
    level: 'Algebra II',
    tutorId: 'elena',
    studentId: '',
    durationMin: 60,
    status: 'scheduled',
    materials: [],
  },
  {
    id: 'slot-2',
    label: 'Thu 5:45 PM · Elena · Pre-calc',
    day: 'Thursday',
    time: '5:45 PM',
    subjectId: 'math',
    level: 'Pre-calc',
    tutorId: 'elena',
    studentId: '',
    durationMin: 60,
    status: 'scheduled',
    materials: [],
  },
  {
    id: 'slot-3',
    label: 'Fri 3:15 PM · Marcus · Chemistry',
    day: 'Friday',
    time: '3:15 PM',
    subjectId: 'science',
    level: 'Chemistry',
    tutorId: 'marcus',
    studentId: '',
    durationMin: 60,
    status: 'scheduled',
    materials: [],
  },
  {
    id: 'slot-4',
    label: 'Fri 4:30 PM · Elena · Algebra II',
    day: 'Friday',
    time: '4:30 PM',
    subjectId: 'math',
    level: 'Algebra II',
    tutorId: 'elena',
    studentId: '',
    durationMin: 60,
    status: 'scheduled',
    materials: [],
  },
  {
    id: 'slot-5',
    label: 'Sat 10:30 AM · James · SAT',
    day: 'Saturday',
    time: '10:30 AM',
    subjectId: 'testprep',
    level: 'SAT',
    tutorId: 'james',
    studentId: '',
    durationMin: 90,
    status: 'scheduled',
    materials: [],
  },
  {
    id: 'slot-6',
    label: 'Wed 5:00 PM · Priya · Essay writing',
    day: 'Wednesday',
    time: '5:00 PM',
    subjectId: 'english',
    level: 'Essay writing',
    tutorId: 'priya',
    studentId: '',
    durationMin: 60,
    status: 'scheduled',
    materials: [],
  },
];

export const WEEK_SESSIONS: SessionSlot[] = [
  {
    id: 'ws-mon-1',
    label: 'Mon 4:00 PM · Ava · Algebra II',
    day: 'Monday',
    time: '4:00 PM',
    subjectId: 'math',
    level: 'Algebra II',
    tutorId: 'elena',
    studentId: 's1',
    durationMin: 60,
    status: 'completed',
    materials: [
      { id: 'm1', name: 'Quadratic review sheet', type: 'worksheet', sentAt: 'Sun 6:00 PM' },
      { id: 'm2', name: 'Factoring walkthrough', type: 'video', sentAt: 'Sun 6:00 PM' },
    ],
  },
  {
    id: 'ws-tue-1',
    label: 'Tue 5:30 PM · Noah · Chemistry',
    day: 'Tuesday',
    time: '5:30 PM',
    subjectId: 'science',
    level: 'Chemistry',
    tutorId: 'marcus',
    studentId: 's2',
    durationMin: 60,
    status: 'completed',
    materials: [
      { id: 'm3', name: 'Mole ratio practice', type: 'worksheet', sentAt: 'Mon 7:00 PM' },
      { id: 'm4', name: 'Lab prep: titration', type: 'reading', sentAt: 'Mon 7:00 PM' },
    ],
  },
  {
    id: 'ws-wed-1',
    label: 'Wed 4:15 PM · Mia · SAT verbal',
    day: 'Wednesday',
    time: '4:15 PM',
    subjectId: 'testprep',
    level: 'SAT verbal',
    tutorId: 'priya',
    studentId: 's3',
    durationMin: 90,
    status: 'prep-sent',
    materials: [
      { id: 'm5', name: 'Passage strategy deck', type: 'reading', sentAt: 'Tue 6:30 PM' },
      { id: 'm6', name: 'Timed vocab quiz', type: 'quiz', sentAt: 'Tue 6:30 PM' },
    ],
  },
  {
    id: 'ws-thu-1',
    label: 'Thu 4:30 PM · Ava · Algebra II',
    day: 'Thursday',
    time: '4:30 PM',
    subjectId: 'math',
    level: 'Algebra II',
    tutorId: 'elena',
    studentId: 's1',
    durationMin: 60,
    status: 'prep-sent',
    materials: [
      { id: 'm7', name: 'Systems of equations set', type: 'worksheet', sentAt: 'Wed 7:15 PM' },
      { id: 'm8', name: 'Graphing shortcuts', type: 'video', sentAt: 'Wed 7:15 PM' },
    ],
  },
  {
    id: 'ws-thu-2',
    label: 'Thu 6:00 PM · Ethan · SAT',
    day: 'Thursday',
    time: '6:00 PM',
    subjectId: 'testprep',
    level: 'SAT',
    tutorId: 'james',
    studentId: 's4',
    durationMin: 90,
    status: 'scheduled',
    materials: [
      { id: 'm9', name: 'Calculator strategies', type: 'worksheet', sentAt: 'Wed 8:00 PM' },
    ],
  },
  {
    id: 'ws-fri-1',
    label: 'Fri 3:15 PM · Noah · Chemistry',
    day: 'Friday',
    time: '3:15 PM',
    subjectId: 'science',
    level: 'Chemistry',
    tutorId: 'marcus',
    studentId: 's2',
    durationMin: 60,
    status: 'scheduled',
    materials: [],
  },
];

export const INBOX_THREADS: InboxThread[] = [
  { id: '0', name: 'Sarah M.', role: 'parent', preview: 'Weekly report received — thanks!', time: '12m', unread: true, avatar: 'S', subject: 'Ava · Math' },
  { id: '1', name: 'Ava M.', role: 'student', preview: 'Prep pack for Thursday ready?', time: '28m', unread: false, avatar: 'A', subject: 'Algebra II' },
  { id: '2', name: 'David K.', role: 'parent', preview: 'Can we renew the 8-pack?', time: '1h', unread: false, avatar: 'D', subject: 'Noah · Science' },
  { id: '3', name: 'Mia T.', role: 'student', preview: 'Finished the vocab quiz — 18/20', time: '2h', unread: false, avatar: 'M', subject: 'SAT verbal' },
];

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

export function getTutor(id: string) {
  return TUTORS.find((t) => t.id === id);
}

export function getSubject(id: string) {
  return SUBJECTS.find((s) => s.id === id);
}

export function getStudent(id: string) {
  return STUDENTS.find((s) => s.id === id);
}

export function getPackage(id: string) {
  return PACKAGES.find((p) => p.id === id);
}

/** Day-before evening copy for prep delivery (e.g. Thursday slot → "Wednesday evening"). */
export function prepDeliveryLabel(slot: SessionSlot): string {
  const idx = WEEKDAYS.indexOf(slot.day);
  if (idx < 0) return 'the evening before';
  const prev = WEEKDAYS[(idx + 6) % 7];
  return `${prev} evening`;
}

export function slotsForSubject(subjectId: string, level?: string, tutorId?: string) {
  return BOOKING_SLOTS.filter((s) => {
    if (s.subjectId !== subjectId) return false;
    if (level && s.level !== level) return false;
    if (tutorId && s.tutorId !== tutorId) return false;
    return true;
  });
}

export function matchTutors(subjectId: string, level: string): Tutor[] {
  return TUTORS.filter(
    (t) => t.visibleOnWebsite && t.subjects.includes(subjectId) && t.levels.includes(level),
  )
    .map((t) => ({
      ...t,
      matchScore: Math.min(99, 82 + Math.floor(t.rating * 3) + (t.sessionsThisWeek > 10 ? 5 : 0)),
    }))
    .sort((a, b) => (b.matchScore ?? 0) - (a.matchScore ?? 0));
}

export function tutorMatchReasons(tutor: Tutor, level: string): string[] {
  const reasons: string[] = [];
  if (tutor.levels.includes(level)) {
    reasons.push(`Deep expertise in ${level}`);
  }
  if (tutor.specialties[0]) {
    reasons.push(`Known for ${tutor.specialties[0].toLowerCase()}`);
  }
  if (tutor.rating >= 4.9) {
    reasons.push(`${tutor.rating}★ family rating`);
  } else {
    reasons.push(`${tutor.rating}★ average from parents`);
  }
  if (tutor.sessionsThisWeek >= 12) {
    reasons.push('High weekly cadence · spots move fast');
  } else if (reasons.length < 3) {
    reasons.push('Prep pack auto-queued with every booking');
  }
  return reasons.slice(0, 3);
}

export function matchScoreBreakdown(tutor: Tutor): { label: string; value: number }[] {
  const expert = Math.min(40, 28 + Math.floor(tutor.rating * 2));
  const load = Math.min(30, 18 + Math.min(12, tutor.sessionsThisWeek));
  const fit = Math.min(30, (tutor.matchScore ?? 90) - expert - load + 10);
  return [
    { label: 'Subject expertise', value: expert },
    { label: 'Scheduling fit', value: Math.max(12, fit) },
    { label: 'Outcomes & load', value: load },
  ];
}

export const PREP_PREVIEW = [
  { type: 'worksheet' as const, name: 'Level-aligned practice set' },
  { type: 'video' as const, name: 'Concept walkthrough (8–12 min)' },
  { type: 'quiz' as const, name: 'Warm-up quiz before session' },
];

export const WEBSITE_TUTORS = TUTORS.filter((t) => t.visibleOnWebsite);
