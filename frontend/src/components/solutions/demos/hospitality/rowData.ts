/** Shared The Row Hotel data — guest site, inbox, housekeeping, ops */

export type RoomType = {
  id: string;
  name: string;
  size: string;
  rate: string;
  nightsFrom: string;
  desc: string;
  tag?: string;
  amenities: string[];
  imageUrl: string;
};

export type BookingHold = {
  id: string;
  label: string;
  checkIn: string;
  checkOut: string;
  nights: number;
  roomId: string;
  roomName: string;
  guests: number;
  rate: string;
};

export type RoomStatus = 'dirty' | 'cleaning' | 'clean' | 'inspected' | 'occupied';

export type HousekeepingRoom = {
  id: string;
  number: string;
  floor: number;
  type: string;
  status: RoomStatus;
  guest?: string;
  checkout?: string;
  note?: string;
  attendant?: string;
};

export type Arrival = {
  id: string;
  guest: string;
  room: string;
  time: string;
  nights: number;
  vip?: boolean;
  prefs?: string;
  returning?: boolean;
  status?: 'due' | 'ready' | 'checked-in' | 'out';
  roomReady?: boolean;
  type?: string;
};

export type GuestMemory = {
  name: string;
  stays: number;
  prefs: string[];
  lastStay: string;
  room?: string;
  nights?: number;
  history?: string[];
  aiNote?: string;
  loyalty?: string;
};

export const HOTEL = {
  name: 'The Row Hotel',
  product: 'Row Guest',
  tagline: 'Boutique stay · Downtown corridor',
  address: '214 Row Street',
  city: 'Chicago, IL 60654',
  phone: '(312) 555-0190',
  email: 'stay@therowhotel.app',
  heroImage: 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=1400&h=900&fit=crop&q=85',
  lobbyImage: 'https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?w=900&h=640&fit=crop&q=85',
  suiteImage: 'https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=1400&h=500&fit=crop&q=85',
  loungeImage: 'https://images.unsplash.com/photo-1611892440504-42a792e24d32?w=900&h=1200&fit=crop&q=85',
  gallery: [
    'https://images.unsplash.com/photo-1618773928121-c32242e63f39?w=800&h=600&fit=crop&q=85',
    'https://images.unsplash.com/photo-1590490360182-c33d57733427?w=800&h=600&fit=crop&q=85',
    'https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=800&h=600&fit=crop&q=85',
    'https://images.unsplash.com/photo-1578683010236-d716f9a3f461?w=800&h=600&fit=crop&q=85',
  ],
};

export const ROOM_TYPES: RoomType[] = [
  {
    id: 'classic',
    name: 'Classic King',
    size: '280 sq ft',
    rate: '$248',
    nightsFrom: 'from / night',
    desc: 'Quiet courtyard view · rain shower · desk nook',
    amenities: ['King bed', 'Courtyard', 'Nespresso'],
    imageUrl: 'https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=900&h=680&fit=crop&q=85',
  },
  {
    id: 'corner',
    name: 'Corner Suite',
    size: '420 sq ft',
    rate: '$389',
    nightsFrom: 'from / night',
    desc: 'Floor-to-ceiling glass · soaking tub · evening turndown',
    tag: 'Most booked',
    amenities: ['City view', 'Sofa', 'Tub'],
    imageUrl: 'https://images.unsplash.com/photo-1618773928121-c32242e63f39?w=900&h=680&fit=crop&q=85',
  },
  {
    id: 'row-pent',
    name: 'Row Penthouse',
    size: '680 sq ft',
    rate: '$620',
    nightsFrom: 'from / night',
    desc: 'Private terrace · butler pantry · skyline plunge',
    tag: 'Direct only',
    amenities: ['Terrace', 'Butler', 'Plunge'],
    imageUrl: 'https://images.unsplash.com/photo-1590490360182-c33d57733427?w=900&h=680&fit=crop&q=85',
  },
];

export const BOOKING_OPTIONS: BookingHold[] = [
  {
    id: 'fri-corner-2n',
    label: 'Fri–Sun · Corner Suite',
    checkIn: 'Fri Jul 10',
    checkOut: 'Sun Jul 12',
    nights: 2,
    roomId: 'corner',
    roomName: 'Corner Suite',
    guests: 2,
    rate: '$778 total',
  },
  {
    id: 'sat-classic-1n',
    label: 'Sat · Classic King',
    checkIn: 'Sat Jul 11',
    checkOut: 'Sun Jul 12',
    nights: 1,
    roomId: 'classic',
    roomName: 'Classic King',
    guests: 2,
    rate: '$248 total',
  },
  {
    id: 'fri-pent-3n',
    label: 'Fri–Mon · Penthouse',
    checkIn: 'Fri Jul 10',
    checkOut: 'Mon Jul 13',
    nights: 3,
    roomId: 'row-pent',
    roomName: 'Row Penthouse',
    guests: 2,
    rate: '$1,860 total',
  },
];

export const HOUSEKEEPING_ROOMS: HousekeepingRoom[] = [
  { id: '401', number: '401', floor: 4, type: 'Classic', status: 'dirty', guest: 'Leaving 11 AM', checkout: '11:00', attendant: 'M. Reyes' },
  { id: '402', number: '402', floor: 4, type: 'Classic', status: 'cleaning', guest: 'Vacant', attendant: 'M. Reyes', note: 'Deep clean linens' },
  { id: '403', number: '403', floor: 4, type: 'Corner', status: 'clean', attendant: 'M. Reyes' },
  { id: '404', number: '404', floor: 4, type: 'Classic', status: 'inspected', attendant: 'Lead · J. Park' },
  { id: '405', number: '405', floor: 4, type: 'Classic', status: 'occupied', guest: 'Dubois · late checkout', note: 'Remember hypoallergenic' },
  { id: '501', number: '501', floor: 5, type: 'Corner', status: 'dirty', guest: 'Leaving noon', checkout: '12:00', attendant: 'A. Chen' },
  { id: '502', number: '502', floor: 5, type: 'Classic', status: 'cleaning', attendant: 'A. Chen' },
  { id: '503', number: '503', floor: 5, type: 'Classic', status: 'clean', attendant: 'A. Chen' },
  { id: '504', number: '504', floor: 5, type: 'Penthouse', status: 'inspected', attendant: 'Lead · J. Park', note: 'VIP arrival 3 PM' },
  { id: '505', number: '505', floor: 5, type: 'Corner', status: 'occupied', guest: 'Walsh · in-house', note: 'Extra pillows · firm' },
  { id: '601', number: '601', floor: 6, type: 'Classic', status: 'clean', attendant: 'L. Ortiz' },
  { id: '602', number: '602', floor: 6, type: 'Corner', status: 'dirty', guest: 'Leaving 10 AM', checkout: '10:00', attendant: 'L. Ortiz' },
  { id: '603', number: '603', floor: 6, type: 'Classic', status: 'inspected', attendant: 'Lead · J. Park' },
  { id: '604', number: '604', floor: 6, type: 'Classic', status: 'cleaning', attendant: 'L. Ortiz', note: 'Minibar restock' },
  { id: '605', number: '605', floor: 6, type: 'Penthouse', status: 'occupied', guest: 'Returning · Kim', note: 'High floor · quiet wing' },
];

export const TODAY_ARRIVALS: Arrival[] = [
  { id: 'a1', guest: 'Claire Dubois', room: '504', time: '3:00 PM', nights: 2, vip: true, prefs: 'Hypoallergenic · late checkout', returning: true, status: 'ready', roomReady: true, type: 'Penthouse' },
  { id: 'a2', guest: 'James Walsh', room: '403', time: '4:15 PM', nights: 1, prefs: 'Firm pillows', status: 'ready', roomReady: true, type: 'Corner' },
  { id: 'a3', guest: 'Sofia Kim', room: '605', time: '5:00 PM', nights: 3, returning: true, prefs: 'Quiet wing · sparkling water', status: 'due', roomReady: false, type: 'Classic' },
  { id: 'a4', guest: 'Marcus Lee', room: '502', time: '6:30 PM', nights: 2, status: 'due', roomReady: false, type: 'Classic' },
];

export const TODAY_DEPARTURES: Arrival[] = [
  { id: 'd1', guest: 'Nina Okonkwo', room: '401', time: '11:00 AM', nights: 2, status: 'out', type: 'Classic' },
  { id: 'd2', guest: 'Tom Hart', room: '501', time: '12:00 PM', nights: 1, prefs: 'Express checkout', status: 'out', type: 'Corner' },
  { id: 'd3', guest: 'Elena Cruz', room: '602', time: '10:00 AM', nights: 3, returning: true, status: 'out', type: 'Classic' },
];

export const OCCUPANCY_BARS = [
  { day: 'Mon', pct: 72 },
  { day: 'Tue', pct: 68 },
  { day: 'Wed', pct: 81 },
  { day: 'Thu', pct: 88 },
  { day: 'Fri', pct: 94 },
  { day: 'Sat', pct: 97 },
  { day: 'Sun', pct: 79 },
];

export const REVENUE_METRICS = [
  { label: 'RevPAR', value: '$284', sub: '+12% vs LW', accent: true },
  { label: 'ADR', value: '$312', sub: 'Direct +$41 vs OTA' },
  { label: 'Occupancy', value: '91%', sub: 'Tonight · 42/46' },
  { label: 'OTA fees saved', value: '$1.8k', sub: 'This week direct' },
];

export const TONIGHT_STATS = {
  occupancyPct: 91,
  roomsOccupied: 42,
  roomsTotal: 46,
  roomsToSell: 4,
  vipArrivals: 1,
  conciergeOpen: 5,
  arrivals: 4,
  departures: 3,
  lateCheckouts: 6,
  walkInPace: 'On pace',
};

export const VIP_TICKER = [
  { guest: 'Claire Dubois', room: '504', eta: '3:00 PM', note: 'VIP · hypoallergenic · late C/O' },
  { guest: 'Sofia Kim', room: '605', eta: '5:00 PM', note: 'Returning · quiet wing held' },
  { guest: 'Marcus Lee', room: '502', eta: '6:30 PM', note: 'First stay · upgrade offer ready' },
];

export const CONCIERGE_QUEUE = [
  { id: 'cq1', guest: 'James Walsh', request: 'Firm pillows + extra towels', status: 'open' as const, eta: '12m', channel: 'Chat' },
  { id: 'cq2', guest: 'Elena Cruz', request: 'Express checkout receipt', status: 'done' as const, eta: 'Done', channel: 'SMS' },
  { id: 'cq3', guest: 'In-house 405', request: 'Late checkout to 1 PM', status: 'synced' as const, eta: 'HK synced', channel: 'AI' },
  { id: 'cq4', guest: 'Claire Dubois', request: 'Still water only · dining hold', status: 'open' as const, eta: 'Pre-arrival', channel: 'Memory' },
  { id: 'cq5', guest: 'Walk-up lobby', request: 'Luggage hold until 4 PM', status: 'open' as const, eta: '8m', channel: 'Desk' },
];

export const HOUSEKEEPING_SUMMARY = {
  dirty: 3,
  cleaning: 3,
  clean: 3,
  inspected: 3,
  occupied: 3,
  vipReady: 1,
  syncNote: 'VIP prep 504 · late C/O on 405 · departure 401 still dirty',
};

export const FLOOR_HEAT = [
  { floor: 4, occ: 80, dirty: 1, cleaning: 1, ready: 2, occupied: 1 },
  { floor: 5, occ: 100, dirty: 1, cleaning: 1, ready: 2, occupied: 1 },
  { floor: 6, occ: 80, dirty: 1, cleaning: 1, ready: 2, occupied: 1 },
];

export const ROOM_TYPE_MIX = [
  { type: 'Classic King', sold: 18, total: 22, pct: 82, adr: '$248' },
  { type: 'Corner Suite', sold: 14, total: 14, pct: 100, adr: '$389' },
  { type: 'Row Penthouse', sold: 10, total: 10, pct: 100, adr: '$620' },
];

export const CHANNEL_MIX = [
  { channel: 'Direct', pct: 58, nights: 24, revenue: '$8.4k', color: 'gold' as const },
  { channel: 'OTA', pct: 28, nights: 12, revenue: '$3.1k', color: 'wine' as const },
  { channel: 'Corporate', pct: 10, nights: 4, revenue: '$1.2k', color: 'cream' as const },
  { channel: 'Walk-in', pct: 4, nights: 2, revenue: '$0.5k', color: 'warm' as const },
];

export const REVENUE_PACE = {
  tonight: { sold: 42, target: 44, pace: '92% of pace' },
  week: { rev: '$48.2k', vsPrior: '+9%' },
  upsellAttach: { rate: '34%', tonight: 'Spa · late C/O · breakfast' },
  pickup: [
    { day: 'Mon', direct: 6, ota: 3 },
    { day: 'Tue', direct: 5, ota: 4 },
    { day: 'Wed', direct: 8, ota: 3 },
    { day: 'Thu', direct: 9, ota: 4 },
    { day: 'Fri', direct: 11, ota: 5 },
    { day: 'Sat', direct: 12, ota: 4 },
    { day: 'Sun', direct: 7, ota: 3 },
  ],
};

export const GUEST_MEMORIES: GuestMemory[] = [
  {
    name: 'Claire Dubois',
    stays: 7,
    prefs: ['Hypoallergenic bedding', 'Late checkout 1 PM', 'Still water only'],
    lastStay: 'Mar 2026',
    room: '504',
    nights: 2,
    loyalty: 'Row Circle · Gold',
    history: ['Mar 2026 · Penthouse', 'Nov 2025 · Corner', 'Jun 2025 · Corner'],
    aiNote: 'Auto-apply prefs on check-in · VIP amenity tray staged · dining hold Untitled 8:15.',
  },
  {
    name: 'Sofia Kim',
    stays: 4,
    prefs: ['High floor quiet', 'Sparkling water', 'Gym 6 AM'],
    lastStay: 'Jan 2026',
    room: '605',
    nights: 3,
    loyalty: 'Row Circle · Silver',
    history: ['Jan 2026 · Classic', 'Sep 2025 · Corner', 'Apr 2025 · Classic'],
    aiNote: 'Quiet wing already held · spa add-on pitched at 28% attach for her segment.',
  },
  {
    name: 'Elena Cruz',
    stays: 3,
    prefs: ['Express checkout', 'Corner city view'],
    lastStay: 'Dec 2025',
    room: '602',
    nights: 3,
    loyalty: 'Returning',
    history: ['Dec 2025 · Corner', 'Aug 2025 · Classic'],
    aiNote: 'Departing today · express C/O ready · invite for autumn early-bird direct rate.',
  },
];

export function bookingForGuests(guests: number): BookingHold[] {
  return BOOKING_OPTIONS.filter((b) => b.guests >= guests || guests <= 2);
}

export function getRoomType(id: string): RoomType | undefined {
  return ROOM_TYPES.find((r) => r.id === id);
}

export function roomsByFloor(floor: number): HousekeepingRoom[] {
  return HOUSEKEEPING_ROOMS.filter((r) => r.floor === floor);
}

export const HOUSEKEEPING_FLOORS = [4, 5, 6] as const;
