/** Shared Ember & Oak Kitchen data — guest site, inbox, floor, kitchen ops */

export type MenuItem = {
  id: string;
  name: string;
  price: string;
  desc: string;
  tag?: string;
  imageUrl: string;
};

export type MenuSection = {
  id: string;
  title: string;
  items: MenuItem[];
};

export type Table = {
  id: string;
  label: string;
  seats: number;
  zone: 'main' | 'patio' | 'bar';
  status: 'open' | 'seated' | 'reserved' | 'closing';
  guest?: string;
  time?: string;
};

export type ReservationSlot = {
  id: string;
  label: string;
  day: string;
  time: string;
  zone: 'main' | 'patio' | 'bar';
  seats: number;
};

export type KitchenOrder = {
  id: string;
  table: string;
  items: string[];
  status: 'new' | 'cooking' | 'ready' | 'served';
  time: string;
  type: 'dine-in' | 'pickup' | 'delivery';
};

export const RESTAURANT = {
  name: 'Ember & Oak',
  tagline: 'Wood-fired · Seasonal · Downtown',
  address: '88 Mercer Street',
  city: 'Brooklyn, NY 11211',
  phone: '(718) 555-0144',
  email: 'hello@emberorder.app',
  heroImage: 'https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1400&h=900&fit=crop&q=85',
  kitchenImage: 'https://images.unsplash.com/photo-1556910103-1c02745aae4d?w=900&h=640&fit=crop&q=85',
  menuHeroImage: 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1400&h=500&fit=crop&q=85',
  reserveImage: 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=900&h=1200&fit=crop&q=85',
  hours: [
    { days: 'Tue – Thu', time: '5:00 PM – 10:00 PM' },
    { days: 'Fri – Sat', time: '5:00 PM – 11:00 PM' },
    { days: 'Sun', time: 'Brunch 10 AM – 3 PM' },
    { days: 'Mon', time: 'Closed' },
  ],
};

export const MENU_SECTIONS: MenuSection[] = [
  {
    id: 'starters',
    title: 'To start',
    items: [
      { id: 'oysters', name: 'Grilled oysters', price: '$16', desc: 'Chili butter, charred lemon', tag: 'Chef pick', imageUrl: 'https://images.unsplash.com/photo-1559339352-11d035aa65de?w=900&h=680&fit=crop&q=85' },
      { id: 'burrata', name: 'Burrata & figs', price: '$14', desc: 'Honey, sourdough crisps', imageUrl: 'https://images.unsplash.com/photo-1606755962773-d324e0a13086?w=900&h=680&fit=crop&q=85' },
    ],
  },
  {
    id: 'mains',
    title: 'From the hearth',
    items: [
      { id: 'truffle-pasta', name: 'Truffle tagliatelle', price: '$28', desc: 'Parmesan, black truffle', tag: 'Most ordered', imageUrl: 'https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=900&h=680&fit=crop&q=85' },
      { id: 'ribeye', name: 'Oak ribeye', price: '$42', desc: 'Bone marrow butter, fries', imageUrl: 'https://images.unsplash.com/photo-1600891964092-4316c288032e?w=900&h=680&fit=crop&q=85' },
      { id: 'salmon', name: 'Cedar salmon', price: '$32', desc: 'Roasted fennel, citrus glaze', imageUrl: 'https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?w=900&h=680&fit=crop&q=85' },
    ],
  },
  {
    id: 'desserts',
    title: 'Sweet',
    items: [
      { id: 'tart', name: 'Burnt honey tart', price: '$12', desc: 'Vanilla bean cream', imageUrl: 'https://images.unsplash.com/photo-1485921325833-c519f76c4927?w=900&h=680&fit=crop&q=85' },
    ],
  },
];

export const PUBLISHED_MENU = MENU_SECTIONS.flatMap((s) => s.items);

export const RESERVATION_SLOTS: ReservationSlot[] = [
  { id: 'sat-patio-745', label: 'Sat 7:45 PM · Patio (8)', day: 'Saturday', time: '7:45 PM', zone: 'patio', seats: 8 },
  { id: 'sat-main-700', label: 'Sat 7:00 PM · Main (4)', day: 'Saturday', time: '7:00 PM', zone: 'main', seats: 4 },
  { id: 'sat-bar-630', label: 'Sat 6:30 PM · Bar (2)', day: 'Saturday', time: '6:30 PM', zone: 'bar', seats: 2 },
  { id: 'fri-patio-800', label: 'Fri 8:00 PM · Patio (6)', day: 'Friday', time: '8:00 PM', zone: 'patio', seats: 6 },
];

export const TONIGHT_TABLES: Table[] = [
  { id: 't1', label: 'Table 4', seats: 4, zone: 'main', status: 'seated', guest: 'Miller party', time: '6:00 PM' },
  { id: 't2', label: 'Table 8', seats: 2, zone: 'main', status: 'seated', guest: 'Chen', time: '6:30 PM' },
  { id: 't3', label: 'Table 12', seats: 6, zone: 'main', status: 'reserved', guest: 'Anderson', time: '7:30 PM' },
  { id: 't4', label: 'Patio A', seats: 8, zone: 'patio', status: 'reserved', guest: 'Birthday party', time: '7:45 PM' },
  { id: 't5', label: 'Patio B', seats: 4, zone: 'patio', status: 'open' },
  { id: 't6', label: 'Bar 1', seats: 2, zone: 'bar', status: 'seated', guest: 'Solo diner', time: '6:15 PM' },
  { id: 't7', label: 'Bar 2', seats: 2, zone: 'bar', status: 'open' },
  { id: 't8', label: 'Bar 3', seats: 2, zone: 'bar', status: 'closing', guest: 'Finishing', time: '6:45 PM' },
];

export const KITCHEN_QUEUE: KitchenOrder[] = [
  { id: '1842', table: 'Pickup #1842', items: ['Truffle tagliatelle', 'Burnt honey tart'], status: 'cooking', time: '6:52 PM', type: 'pickup' },
  { id: '1843', table: 'Table 4', items: ['Oak ribeye ×2', 'Grilled oysters'], status: 'new', time: '6:54 PM', type: 'dine-in' },
  { id: '1841', table: 'Delivery', items: ['Cedar salmon', 'Burrata & figs'], status: 'ready', time: '6:48 PM', type: 'delivery' },
  { id: '1840', table: 'Table 8', items: ['Truffle tagliatelle'], status: 'served', time: '6:35 PM', type: 'dine-in' },
];

export function slotsForParty(size: number): ReservationSlot[] {
  return RESERVATION_SLOTS.filter((s) => s.seats >= size);
}

export function getMenuItem(id: string): MenuItem | undefined {
  return PUBLISHED_MENU.find((m) => m.id === id);
}
