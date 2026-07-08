/** Shared Lumen Home Goods data — storefront, support, fulfillment, seller hub */

export type ProductCategory = 'lighting' | 'textiles' | 'decor' | 'furniture';

export type Product = {
  id: string;
  name: string;
  price: string;
  priceNum: number;
  desc: string;
  category: ProductCategory;
  subcategory: string;
  tags: string[];
  visualTags?: string[];
  imageUrl: string;
  stock: number;
  lowStock?: boolean;
};

export type StyleBundle = {
  id: string;
  title: string;
  subtitle: string;
  productIds: string[];
  savings: string;
  imageUrl: string;
};

export type SupportTicket = {
  id: string;
  orderNum: string;
  customer: string;
  email: string;
  status: 'open' | 'ai-resolved' | 'escalated' | 'closed';
  topic: 'tracking' | 'return' | 'exchange' | 'damage' | 'other';
  preview: string;
  time: string;
  aiResolution?: string;
  urgent?: boolean;
};

export type Shipment = {
  id: string;
  orderNum: string;
  customer: string;
  items: string[];
  stage: 'packed' | 'shipped' | 'out-for-delivery' | 'delivered';
  carrier: string;
  tracking: string;
  eta: string;
  city: string;
};

export type SellerOrder = {
  id: string;
  orderNum: string;
  customer: string;
  items: string[];
  total: string;
  status: 'to-ship' | 'packed' | 'shipped';
  priority?: boolean;
};

export type CategoryDef = {
  id: ProductCategory;
  label: string;
  subcategories: { id: string; label: string }[];
};

export type ImageSearchPreset = {
  id: string;
  label: string;
  description: string;
  thumbnailUrl: string;
  productIds: string[];
  visualTags: string[];
};

export const STORE = {
  name: 'Lumen Home Goods',
  tagline: 'Curated home · AI-guided shopping',
  address: '412 Market Street',
  city: 'Portland, OR 97204',
  phone: '(503) 555-0198',
  email: 'hello@lumenstore.app',
  heroImage: 'https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=1400&h=900&fit=crop&q=85',
};

export const CATEGORIES: CategoryDef[] = [
  {
    id: 'lighting',
    label: 'Lighting',
    subcategories: [
      { id: 'floor', label: 'Floor lamps' },
      { id: 'table', label: 'Table lamps' },
      { id: 'pendant', label: 'Pendants' },
    ],
  },
  {
    id: 'textiles',
    label: 'Textiles',
    subcategories: [
      { id: 'throws', label: 'Throws' },
      { id: 'pillows', label: 'Pillows' },
      { id: 'rugs', label: 'Rugs' },
    ],
  },
  {
    id: 'decor',
    label: 'Decor',
    subcategories: [
      { id: 'vases', label: 'Vases' },
      { id: 'mirrors', label: 'Mirrors' },
      { id: 'objects', label: 'Objects' },
    ],
  },
  {
    id: 'furniture',
    label: 'Furniture',
    subcategories: [
      { id: 'seating', label: 'Seating' },
      { id: 'tables', label: 'Tables' },
      { id: 'storage', label: 'Storage' },
    ],
  },
];

export const PRODUCTS: Product[] = [
  {
    id: 'arc-lamp',
    name: 'Arc floor lamp',
    price: '$189',
    priceNum: 189,
    desc: 'Warm brass arc · linen shade · dimmable',
    category: 'lighting',
    subcategory: 'floor',
    tags: ['minimalist', 'bedroom', 'warm', 'lighting'],
    visualTags: ['brass', 'warm-glow', 'arc', 'linen-shade', 'bedroom'],
    imageUrl: 'https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=800&h=1000&fit=crop&q=85',
    stock: 24,
  },
  {
    id: 'cloud-throw',
    name: 'Cloud weave throw',
    price: '$78',
    priceNum: 78,
    desc: 'Oatmeal cotton · oversized · machine wash',
    category: 'textiles',
    subcategory: 'throws',
    tags: ['cozy', 'bedroom', 'neutral', 'textiles'],
    visualTags: ['oatmeal', 'soft', 'neutral', 'layered', 'cozy'],
    imageUrl: 'https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?w=800&h=900&fit=crop&q=85',
    stock: 41,
  },
  {
    id: 'ceramic-vase',
    name: 'Matte ceramic vase',
    price: '$42',
    priceNum: 42,
    desc: 'Soft ivory · sculptural silhouette',
    category: 'decor',
    subcategory: 'vases',
    tags: ['minimalist', 'decor', 'neutral'],
    visualTags: ['ivory', 'matte', 'sculptural', 'ceramic', 'neutral'],
    imageUrl: 'https://images.unsplash.com/photo-1578500494198-246f612d3b3d?w=800&h=1000&fit=crop&q=85',
    stock: 8,
    lowStock: true,
  },
  {
    id: 'walnut-stool',
    name: 'Walnut bedside stool',
    price: '$124',
    priceNum: 124,
    desc: 'Solid walnut · rounded edge · 16" height',
    category: 'furniture',
    subcategory: 'seating',
    tags: ['bedroom', 'warm', 'furniture', 'minimalist'],
    visualTags: ['walnut', 'warm-wood', 'bedside', 'rounded'],
    imageUrl: 'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=800&h=900&fit=crop&q=85',
    stock: 12,
  },
  {
    id: 'table-lamp',
    name: 'Halo table lamp',
    price: '$96',
    priceNum: 96,
    desc: 'Frosted globe · walnut base · 2700K glow',
    category: 'lighting',
    subcategory: 'table',
    tags: ['warm', 'bedroom', 'lighting', 'minimalist'],
    visualTags: ['frosted-glass', 'warm-glow', 'walnut', 'bedside', '2700k'],
    imageUrl: 'https://images.unsplash.com/photo-1513506003901-1e6a229e2d15?w=800&h=1000&fit=crop&q=85',
    stock: 19,
  },
  {
    id: 'linen-pillow',
    name: 'Linen pillow set',
    price: '$58',
    priceNum: 58,
    desc: 'Pair · sand & fog · envelope closure',
    category: 'textiles',
    subcategory: 'pillows',
    tags: ['bedroom', 'neutral', 'textiles', 'cozy'],
    visualTags: ['linen', 'sand', 'fog', 'soft', 'layered'],
    imageUrl: 'https://images.unsplash.com/photo-1584100936595-c0654b4a2ccf?w=800&h=900&fit=crop&q=85',
    stock: 33,
  },
  {
    id: 'mirror-round',
    name: 'Round brass mirror',
    price: '$145',
    priceNum: 145,
    desc: '24" diameter · thin brass frame',
    category: 'decor',
    subcategory: 'mirrors',
    tags: ['minimalist', 'decor', 'warm'],
    visualTags: ['brass', 'round', 'reflective', 'warm-metal'],
    imageUrl: 'https://images.unsplash.com/photo-1618220179428-22790b461013?w=800&h=1000&fit=crop&q=85',
    stock: 6,
    lowStock: true,
  },
  {
    id: 'shelf-float',
    name: 'Floating shelf pair',
    price: '$68',
    priceNum: 68,
    desc: 'White oak · hidden bracket · 24"',
    category: 'furniture',
    subcategory: 'storage',
    tags: ['minimalist', 'decor', 'furniture'],
    visualTags: ['white-oak', 'floating', 'minimal', 'display'],
    imageUrl: 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=800&h=900&fit=crop&q=85',
    stock: 27,
  },
  {
    id: 'pendant-orb',
    name: 'Orb pendant light',
    price: '$156',
    priceNum: 156,
    desc: 'Milk glass globe · black canopy · adjustable',
    category: 'lighting',
    subcategory: 'pendant',
    tags: ['dining', 'minimalist', 'lighting'],
    visualTags: ['milk-glass', 'pendant', 'globe', 'black-metal'],
    imageUrl: 'https://images.unsplash.com/photo-1524484483545-86c8e687b5a4?w=800&h=1000&fit=crop&q=85',
    stock: 14,
  },
  {
    id: 'wool-rug',
    name: 'Soft wool runner',
    price: '$210',
    priceNum: 210,
    desc: 'Hand-loomed wool · fog stripe · 2.5×8',
    category: 'textiles',
    subcategory: 'rugs',
    tags: ['hallway', 'neutral', 'textiles', 'cozy'],
    visualTags: ['wool', 'fog', 'stripe', 'soft', 'neutral'],
    imageUrl: 'https://images.unsplash.com/photo-1600166898405-da9535204843?w=800&h=900&fit=crop&q=85',
    stock: 9,
    lowStock: true,
  },
  {
    id: 'stone-bowl',
    name: 'Travertine catchall',
    price: '$54',
    priceNum: 54,
    desc: 'Natural stone · shallow bowl · coffee table',
    category: 'decor',
    subcategory: 'objects',
    tags: ['decor', 'minimalist', 'warm'],
    visualTags: ['stone', 'travertine', 'organic', 'taupe'],
    imageUrl: 'https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=800&h=1000&fit=crop&q=85',
    stock: 22,
  },
  {
    id: 'oak-side-table',
    name: 'Oak nesting table',
    price: '$168',
    priceNum: 168,
    desc: 'Solid white oak · tapered legs · nestable pair',
    category: 'furniture',
    subcategory: 'tables',
    tags: ['living', 'furniture', 'warm', 'minimalist'],
    visualTags: ['white-oak', 'nesting', 'tapered', 'warm-wood'],
    imageUrl: 'https://images.unsplash.com/photo-1533090161767-e6ffed986c88?w=800&h=900&fit=crop&q=85',
    stock: 11,
  },
  {
    id: 'sconce-pair',
    name: 'Fluted wall sconce pair',
    price: '$132',
    priceNum: 132,
    desc: 'Ceramic fluted · plug-in · linen shade',
    category: 'lighting',
    subcategory: 'table',
    tags: ['bedroom', 'warm', 'lighting'],
    visualTags: ['ceramic', 'fluted', 'linen-shade', 'warm-glow', 'wall'],
    imageUrl: 'https://images.unsplash.com/photo-1540932239986-30128078f3c5?w=800&h=1000&fit=crop&q=85',
    stock: 16,
  },
  {
    id: 'boucle-pillow',
    name: 'Bouclé accent pillow',
    price: '$48',
    priceNum: 48,
    desc: 'Cream bouclé · down fill · knife edge',
    category: 'textiles',
    subcategory: 'pillows',
    tags: ['cozy', 'neutral', 'living', 'textiles'],
    visualTags: ['boucle', 'cream', 'texture', 'soft', 'cozy'],
    imageUrl: 'https://images.unsplash.com/photo-1615529162924-f8605388461d?w=800&h=900&fit=crop&q=85',
    stock: 38,
  },
];

export const STYLE_BUNDLES: StyleBundle[] = [
  {
    id: 'warm-bedroom',
    title: 'Warm minimalist bedroom',
    subtitle: 'Soft light, neutral layers, calm surfaces',
    productIds: ['table-lamp', 'cloud-throw', 'ceramic-vase', 'linen-pillow'],
    savings: 'Save $32',
    imageUrl: 'https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=1200&h=600&fit=crop&q=85',
  },
  {
    id: 'reading-nook',
    title: 'Reading nook edit',
    subtitle: 'Arc light + walnut stool + throw',
    productIds: ['arc-lamp', 'walnut-stool', 'cloud-throw'],
    savings: 'Save $18',
    imageUrl: 'https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?w=1200&h=600&fit=crop&q=85',
  },
  {
    id: 'living-calm',
    title: 'Living room calm',
    subtitle: 'Nesting oak, wool runner, soft textures',
    productIds: ['oak-side-table', 'wool-rug', 'boucle-pillow', 'stone-bowl'],
    savings: 'Save $44',
    imageUrl: 'https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?w=1200&h=600&fit=crop&q=85',
  },
];

export const IMAGE_SEARCH_PRESETS: ImageSearchPreset[] = [
  {
    id: 'warm-bedroom',
    label: 'Warm bedroom mood',
    description: 'Soft neutrals · linen layers · 2700K glow',
    thumbnailUrl: 'https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=200&h=200&fit=crop&q=80',
    productIds: ['table-lamp', 'cloud-throw', 'linen-pillow', 'ceramic-vase', 'walnut-stool'],
    visualTags: ['warm-glow', 'linen', 'oatmeal', 'neutral', 'bedside', 'soft'],
  },
  {
    id: 'brass-minimal',
    label: 'Brass & glass',
    description: 'Warm metal · reflective surfaces · arc lines',
    thumbnailUrl: 'https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=200&h=200&fit=crop&q=80',
    productIds: ['arc-lamp', 'mirror-round', 'pendant-orb', 'table-lamp'],
    visualTags: ['brass', 'warm-metal', 'round', 'arc', 'reflective'],
  },
  {
    id: 'organic-living',
    label: 'Organic living room',
    description: 'Stone · oak · wool · cream texture',
    thumbnailUrl: 'https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?w=200&h=200&fit=crop&q=80',
    productIds: ['oak-side-table', 'wool-rug', 'stone-bowl', 'boucle-pillow', 'shelf-float'],
    visualTags: ['white-oak', 'wool', 'stone', 'boucle', 'organic', 'taupe'],
  },
];

export const SUPPORT_QUEUE: SupportTicket[] = [
  {
    id: '0',
    orderNum: '#LM-48291',
    customer: 'Maya Chen',
    email: 'maya.c@email.com',
    status: 'ai-resolved',
    topic: 'tracking',
    preview: 'Where is my order? Shipped Tuesday.',
    time: '4m',
    aiResolution: 'Tracking sent · out for delivery today',
    urgent: true,
  },
  {
    id: '1',
    orderNum: '#LM-48102',
    customer: 'James Ortiz',
    email: 'j.ortiz@email.com',
    status: 'open',
    topic: 'return',
    preview: 'Return label for Halo lamp — wrong shade tone',
    time: '18m',
    aiResolution: 'Return label generated · pickup scheduled',
  },
  {
    id: '2',
    orderNum: '#LM-47988',
    customer: 'Priya Shah',
    email: 'priya.s@email.com',
    status: 'ai-resolved',
    topic: 'exchange',
    preview: 'Exchange throw for fog color?',
    time: '42m',
    aiResolution: 'Exchange approved · fog shipped free',
  },
  {
    id: '3',
    orderNum: '#LM-47844',
    customer: 'Alex Kim',
    email: 'alex.k@email.com',
    status: 'closed',
    topic: 'damage',
    preview: 'Vase arrived chipped — replacement?',
    time: '2h',
    aiResolution: 'Replacement shipped · no return needed',
  },
];

export const SHIPMENTS: Shipment[] = [
  {
    id: 's1',
    orderNum: '#LM-48291',
    customer: 'Maya Chen',
    items: ['Halo table lamp', 'Linen pillow set'],
    stage: 'out-for-delivery',
    carrier: 'UPS',
    tracking: '1Z999AA10123456784',
    eta: 'Today by 6 PM',
    city: 'Portland, OR',
  },
  {
    id: 's2',
    orderNum: '#LM-48204',
    customer: 'Daniel Wu',
    items: ['Arc floor lamp'],
    stage: 'shipped',
    carrier: 'FedEx',
    tracking: '7946 1234 5678',
    eta: 'Thu, Jul 10',
    city: 'Seattle, WA',
  },
  {
    id: 's3',
    orderNum: '#LM-48156',
    customer: 'Elena Rossi',
    items: ['Warm bedroom bundle'],
    stage: 'packed',
    carrier: 'UPS',
    tracking: 'Pending label',
    eta: 'Ships today',
    city: 'San Francisco, CA',
  },
  {
    id: 's4',
    orderNum: '#LM-48012',
    customer: 'Tom Bradley',
    items: ['Walnut bedside stool', 'Cloud weave throw'],
    stage: 'delivered',
    carrier: 'UPS',
    tracking: '1Z999AA10987654321',
    eta: 'Delivered Jul 6',
    city: 'Denver, CO',
  },
  {
    id: 's5',
    orderNum: '#LM-47901',
    customer: 'Nina Patel',
    items: ['Round brass mirror'],
    stage: 'shipped',
    carrier: 'USPS',
    tracking: '9400 1234 5678 9012',
    eta: 'Fri, Jul 11',
    city: 'Austin, TX',
  },
];

export const ORDERS_TO_SHIP: SellerOrder[] = [
  {
    id: 'o1',
    orderNum: '#LM-48156',
    customer: 'Elena Rossi',
    items: ['Warm bedroom bundle ×1'],
    total: '$264',
    status: 'to-ship',
    priority: true,
  },
  {
    id: 'o2',
    orderNum: '#LM-48215',
    customer: 'Chris Lee',
    items: ['Floating shelf pair ×2'],
    total: '$136',
    status: 'to-ship',
  },
  {
    id: 'o3',
    orderNum: '#LM-48204',
    customer: 'Daniel Wu',
    items: ['Arc floor lamp ×1'],
    total: '$189',
    status: 'packed',
  },
  {
    id: 'o4',
    orderNum: '#LM-48288',
    customer: 'Sofia Grant',
    items: ['Orb pendant ×1', 'Wool runner ×1'],
    total: '$366',
    status: 'to-ship',
    priority: true,
  },
  {
    id: 'o5',
    orderNum: '#LM-48271',
    customer: 'Marcus Bell',
    items: ['Bouclé pillow ×2', 'Travertine catchall ×1'],
    total: '$150',
    status: 'packed',
  },
];

export const SELLER_ACTIVITY = [
  { text: 'Image search converted — Warm bedroom mood', detail: 'Halo lamp + linen pillows · $154', time: '3m', type: 'vision' as const },
  { text: 'NL search: “warm minimalist lamp”', detail: '4 matches · 68% find-to-cart', time: '12m', type: 'search' as const },
  { text: 'Bundle sold — Warm bedroom', detail: 'Elena Rossi · #LM-48156', time: '28m', type: 'order' as const },
  { text: 'Low stock alert — Round brass mirror', detail: '6 left · reorder suggested', time: '1h', type: 'alert' as const },
  { text: 'Flash sale live — Textiles 15% off', detail: 'Ends tonight · 42 views', time: '2h', type: 'promo' as const },
  { text: 'IG shop synced 3 new SKUs', detail: 'Pendant, runner, nesting table', time: '3h', type: 'channel' as const },
];

export const TOP_QUERIES = [
  { query: 'warm minimalist lamp for bedroom', count: 148, conversion: '72%' },
  { query: 'cozy neutral throw', count: 96, conversion: '64%' },
  { query: 'sculptural decor under $50', count: 71, conversion: '58%' },
  { query: 'brass mirror round', count: 54, conversion: '61%' },
  { query: 'reading nook furniture', count: 41, conversion: '55%' },
];

export const PROMO_RULES = [
  { id: 'flash-textiles', name: 'Flash sale · Textiles', detail: '15% off throws & pillows', status: 'live' as const, ends: 'Tonight 11:59 PM' },
  { id: 'free-ship', name: 'Free shipping', detail: 'Orders $75+ · US contiguous', status: 'always' as const, ends: 'Always on' },
  { id: 'bundle-save', name: 'Bundle discount', detail: 'Style bundles · save $18–$44', status: 'live' as const, ends: 'Ongoing' },
  { id: 'first-order', name: 'Welcome 10%', detail: 'First purchase · code LUMEN10', status: 'paused' as const, ends: 'Paused' },
];

export const CHANNELS = [
  { id: 'site', name: 'Storefront', detail: 'lumenstore.app · Shopper AI on', enabled: true },
  { id: 'ig', name: 'Instagram Shop', detail: 'Tagged catalog · 12 SKUs live', enabled: true },
  { id: 'email', name: 'Email & SMS', detail: 'Abandoned cart + restock alerts', enabled: false },
];

export const TOP_CUSTOMERS = [
  { name: 'Elena Rossi', orders: 7, ltv: '$1,840', tag: 'VIP' },
  { name: 'Maya Chen', orders: 5, ltv: '$960', tag: 'Repeat' },
  { name: 'Daniel Wu', orders: 4, ltv: '$720', tag: 'Repeat' },
  { name: 'Sofia Grant', orders: 3, ltv: '$540', tag: 'New' },
  { name: 'Marcus Bell', orders: 3, ltv: '$410', tag: 'New' },
];

export const REV_SPARK = [58, 64, 71, 68, 82, 76, 91];

export type PlacedOrder = {
  orderNum: string;
  items: string[];
  total: string;
};

export function getProduct(id: string): Product | undefined {
  return PRODUCTS.find((p) => p.id === id);
}

export function getCategory(id: string): CategoryDef | undefined {
  return CATEGORIES.find((c) => c.id === id);
}

export function productsInBundle(bundleId: string): Product[] {
  const bundle = STYLE_BUNDLES.find((b) => b.id === bundleId);
  if (!bundle) return [];
  return bundle.productIds.map((id) => getProduct(id)).filter(Boolean) as Product[];
}

export function filterCatalog(opts: { category?: string | null; subcategory?: string | null } = {}): Product[] {
  const { category, subcategory } = opts;
  return PRODUCTS.filter((p) => {
    if (category && p.category !== category) return false;
    if (subcategory && p.subcategory !== subcategory) return false;
    return true;
  });
}

export function searchProducts(query: string, opts: { category?: string | null; subcategory?: string | null } = {}): Product[] {
  const base = filterCatalog(opts);
  const q = query.toLowerCase();
  const terms = q.split(/\s+/).filter(Boolean);
  if (!terms.length) return base;

  return base
    .filter((p) => {
      const haystack = [p.name, p.desc, p.category, p.subcategory, ...p.tags, ...(p.visualTags ?? [])].join(' ').toLowerCase();
      return terms.some((t) => haystack.includes(t));
    })
    .sort((a, b) => {
      const score = (prod: Product) =>
        terms.reduce(
          (s, t) =>
            s +
            (prod.tags.some((tag) => tag.includes(t)) ? 2 : 0) +
            (prod.visualTags?.some((tag) => tag.includes(t)) ? 2 : 0) +
            (prod.name.toLowerCase().includes(t) ? 1 : 0),
          0,
        );
      return score(b) - score(a);
    });
}

export function searchByImage(presetId: string): Product[] {
  const preset = IMAGE_SEARCH_PRESETS.find((p) => p.id === presetId);
  if (!preset) return PRODUCTS.slice(0, 4);

  const byId = preset.productIds.map((id) => getProduct(id)).filter(Boolean) as Product[];
  if (byId.length) return byId;

  const tags = new Set(preset.visualTags.map((t) => t.toLowerCase()));
  return PRODUCTS.map((p) => {
    const score = (p.visualTags ?? []).reduce((s, t) => s + (tags.has(t.toLowerCase()) ? 1 : 0), 0);
    return { p, score };
  })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((x) => x.p);
}

export function scoreByVisualTags(tags: string[]): Product[] {
  const set = new Set(tags.map((t) => t.toLowerCase()));
  return PRODUCTS.map((p) => {
    const score = (p.visualTags ?? []).reduce((s, t) => s + (set.has(t.toLowerCase()) ? 1 : 0), 0);
    return { p, score };
  })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((x) => x.p);
}

export function lowStockProducts(): Product[] {
  return PRODUCTS.filter((p) => p.lowStock || p.stock <= 10);
}

export function categoryCounts(): { id: string; label: string; count: number; subs: { id: string; label: string; count: number }[] }[] {
  return CATEGORIES.map((cat) => ({
    id: cat.id,
    label: cat.label,
    count: PRODUCTS.filter((p) => p.category === cat.id).length,
    subs: cat.subcategories.map((sub) => ({
      id: sub.id,
      label: sub.label,
      count: PRODUCTS.filter((p) => p.category === cat.id && p.subcategory === sub.id).length,
    })),
  }));
}
