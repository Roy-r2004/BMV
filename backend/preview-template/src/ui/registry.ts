/**
 * Canonical UI contract source.
 * catalogue.json is generated from this file via `npm run sync:ui`.
 * Do not hand-edit catalogue.json.
 */

export type UiSurface = 'core' | 'public' | 'ops';

export type ComponentMeta = {
  name: string;
  surface: UiSurface;
  path: string;
  requiredProps: string[];
  optionalProps: string[];
  variants?: Record<string, readonly string[]>;
};

export type SkeletonId =
  | 'public-home'
  | 'public-service'
  | 'public-detail'
  | 'public-catalog'
  | 'public-utility'
  | 'public-booking'
  | 'ops-dashboard'
  | 'ops-list'
  | 'ops-detail'
  | 'ops-settings';

export type SkeletonDefinition = {
  id: SkeletonId;
  surface: 'public' | 'ops';
  shell: 'PublicShell' | 'OpsShell';
  purpose: string;
  requiredSections: string[];
  optionalSections: string[];
  recommendedOrder: string[];
  allowedComponents: string[];
  supportedVariants: Record<string, readonly string[]>;
};

export const CATALOGUE_COMPONENTS: readonly ComponentMeta[] = [
  {
    name: 'Button',
    surface: 'core',
    path: 'core/Button.tsx',
    requiredProps: ['children'],
    optionalProps: ['variant', 'size', 'href', 'type', 'disabled', 'onClick', 'className', 'aria-label'],
    variants: { variant: ['default', 'secondary', 'outline', 'ghost', 'destructive'], size: ['default', 'sm', 'lg'] },
  },
  {
    name: 'Input',
    surface: 'core',
    path: 'core/Input.tsx',
    requiredProps: [],
    optionalProps: ['type', 'value', 'defaultValue', 'placeholder', 'disabled', 'required', 'checked', 'defaultChecked', 'id', 'name', 'label', 'error', 'min', 'max', 'step', 'as', 'rows', 'onChange', 'className', 'aria-label'],
    variants: { as: ['input', 'textarea'] },
  },
  {
    name: 'Select',
    surface: 'core',
    path: 'core/Select.tsx',
    requiredProps: ['options'],
    optionalProps: ['value', 'defaultValue', 'onValueChange', 'placeholder', 'disabled', 'required', 'name', 'label', 'className', 'aria-label'],
  },
  {
    name: 'Dialog',
    surface: 'core',
    path: 'core/Dialog.tsx',
    requiredProps: ['title', 'children'],
    optionalProps: ['description', 'triggerLabel', 'showTrigger', 'footer', 'open', 'defaultOpen', 'onOpenChange', 'className'],
  },
  {
    name: 'Tabs',
    surface: 'core',
    path: 'core/Tabs.tsx',
    requiredProps: ['items'],
    optionalProps: ['defaultValue', 'value', 'onValueChange', 'orientation', 'className'],
    variants: { orientation: ['horizontal', 'vertical'] },
  },
  {
    name: 'Card',
    surface: 'core',
    path: 'core/Card.tsx',
    requiredProps: ['children'],
    optionalProps: ['title', 'description', 'className'],
  },
  {
    name: 'Badge',
    surface: 'core',
    path: 'core/Badge.tsx',
    requiredProps: ['children'],
    optionalProps: ['variant', 'className'],
    variants: { variant: ['default', 'secondary', 'outline', 'destructive'] },
  },
  {
    name: 'UiIcon',
    surface: 'core',
    path: '../components/UiIcons.tsx',
    requiredProps: ['name'],
    optionalProps: ['className'],
  },
  {
    name: 'Tooltip',
    surface: 'core',
    path: 'core/Tooltip.tsx',
    requiredProps: ['content', 'children'],
    optionalProps: ['side'],
    variants: { side: ['top', 'right', 'bottom', 'left'] },
  },
  {
    name: 'Table',
    surface: 'core',
    path: 'core/Table.tsx',
    requiredProps: ['columns', 'rows'],
    optionalProps: ['caption', 'className'],
  },
  {
    name: 'PublicShell',
    surface: 'public',
    path: 'public/PublicShell.tsx',
    requiredProps: ['brandName', 'children'],
    optionalProps: ['nav', 'cta', 'footer', 'mobileDock', 'className', 'chrome', 'brandPlacement'],
    variants: {
      chrome: ['solid', 'immersive'],
      brandPlacement: ['start', 'center'],
    },
  },
  {
    name: 'PublicNav',
    surface: 'public',
    path: 'public/PublicNav.tsx',
    requiredProps: ['items'],
    optionalProps: ['cta', 'inverted', 'className', 'variant'],
    variants: { variant: ['default', 'minimal', 'stacked'] },
  },
  {
    name: 'MarketingHero',
    surface: 'public',
    path: 'public/MarketingHero.tsx',
    requiredProps: ['brandName', 'headline', 'subcopy', 'primaryCta', 'imageSrc'],
    optionalProps: ['secondaryCta', 'imageAlt', 'eyebrow', 'variant', 'className'],
    variants: { variant: ['cinematic', 'service', 'compact', 'product', 'editorial', 'split'] },
  },
  {
    name: 'FeatureBento',
    surface: 'public',
    path: 'public/FeatureBento.tsx',
    requiredProps: ['heading', 'items'],
    optionalProps: ['description', 'variant', 'className'],
    variants: { variant: ['bento', 'grid', 'alternating'] },
  },
  {
    name: 'ProductShowcase',
    surface: 'public',
    path: 'public/ProductShowcase.tsx',
    requiredProps: ['heading'],
    optionalProps: ['items', 'description', 'children', 'className'],
  },
  {
    name: 'TestimonialRail',
    surface: 'public',
    path: 'public/TestimonialRail.tsx',
    requiredProps: ['items'],
    optionalProps: ['heading', 'className'],
  },
  {
    name: 'ProcessSection',
    surface: 'public',
    path: 'public/ProcessSection.tsx',
    requiredProps: ['heading', 'steps'],
    optionalProps: ['description', 'className'],
  },
  {
    name: 'CTABand',
    surface: 'public',
    path: 'public/CTABand.tsx',
    requiredProps: ['heading', 'primaryCta'],
    optionalProps: ['description', 'secondaryCta', 'className'],
  },
  {
    name: 'ConfirmStage',
    surface: 'public',
    path: 'public/ConfirmStage.tsx',
    requiredProps: ['title', 'description'],
    optionalProps: ['detail', 'eyebrow', 'nextSteps', 'primaryCta', 'className'],
  },
  {
    name: 'ScheduleRail',
    surface: 'public',
    path: 'public/ScheduleRail.tsx',
    requiredProps: ['items'],
    optionalProps: ['heading', 'description', 'filterable', 'className'],
  },
  {
    name: 'BrandFooter',
    surface: 'public',
    path: 'public/BrandFooter.tsx',
    requiredProps: ['brandName'],
    optionalProps: ['description', 'links', 'meta', 'className', 'variant'],
    variants: { variant: ['statement', 'compact', 'columns'] },
  },
  {
    name: 'LogoMarquee',
    surface: 'public',
    path: 'public/LogoMarquee.tsx',
    requiredProps: ['items'],
    optionalProps: ['heading', 'size', 'className'],
    variants: { size: ['default', 'display'] },
  },
  {
    name: 'SpotlightCard',
    surface: 'public',
    path: 'public/SpotlightCard.tsx',
    requiredProps: ['title', 'description'],
    optionalProps: ['icon', 'className'],
  },
  {
    name: 'AccentBeam',
    surface: 'public',
    path: 'public/AccentBeam.tsx',
    requiredProps: ['children'],
    optionalProps: ['className'],
  },
  {
    name: 'CredentialStrip',
    surface: 'public',
    path: 'public/CredentialStrip.tsx',
    requiredProps: ['items'],
    optionalProps: ['heading', 'className'],
  },
  {
    name: 'ResultRail',
    surface: 'public',
    path: 'public/ResultRail.tsx',
    requiredProps: ['heading', 'items'],
    optionalProps: ['description', 'className'],
  },
  {
    name: 'AiFeatureDeck',
    surface: 'public',
    path: 'public/AiFeatureDeck.tsx',
    requiredProps: ['features'],
    optionalProps: ['brandName', 'className'],
  },
  {
    name: 'AiFeaturePanel',
    surface: 'public',
    path: 'public/AiFeaturePanel.tsx',
    requiredProps: ['feature'],
    optionalProps: ['brandName', 'className', 'compact'],
  },
  {
    name: 'BookingPanel',
    surface: 'public',
    path: 'public/BookingPanel.tsx',
    requiredProps: ['heading'],
    optionalProps: ['treatments', 'slots', 'description', 'confirmLabel', 'onConfirm', 'children', 'className'],
  },
  {
    name: 'OpsShell',
    surface: 'ops',
    path: 'ops/OpsShell.tsx',
    requiredProps: ['brandName', 'navItems', 'children'],
    optionalProps: ['topbar', 'rail', 'appearance', 'className', 'adjustableSidebar', 'defaultSidebarWidth', 'defaultSidebarCollapsed'],
    variants: { appearance: ['soft', 'floor'] },
  },
  {
    name: 'PageHeader',
    surface: 'ops',
    path: 'ops/PageHeader.tsx',
    requiredProps: ['title'],
    optionalProps: ['description', 'actions', 'meta', 'className'],
  },
  {
    name: 'StatCard',
    surface: 'ops',
    path: 'ops/StatCard.tsx',
    requiredProps: ['label', 'value'],
    optionalProps: ['delta', 'hint', 'icon', 'variant', 'className'],
    variants: { variant: ['card', 'strip'] },
  },
  {
    name: 'ChartCard',
    surface: 'ops',
    path: 'ops/ChartCard.tsx',
    requiredProps: ['title', 'data', 'dataKey', 'xKey'],
    optionalProps: ['description', 'insight', 'type', 'adjustable', 'density', 'valueFormat', 'className'],
    variants: { type: ['area', 'bar'], density: ['compact', 'comfortable'], valueFormat: ['number', 'currency', 'compact'] },
  },
  {
    name: 'DataTable',
    surface: 'ops',
    path: 'ops/DataTable.tsx',
    requiredProps: ['columns', 'rows'],
    optionalProps: ['emptyMessage', 'onRowSelect', 'className'],
  },
  {
    name: 'FilterBar',
    surface: 'ops',
    path: 'ops/FilterBar.tsx',
    requiredProps: ['searchPlaceholder'],
    optionalProps: ['searchValue', 'onSearchChange', 'filters', 'actions', 'className'],
  },
  {
    name: 'ActivityFeed',
    surface: 'ops',
    path: 'ops/ActivityFeed.tsx',
    requiredProps: ['items'],
    optionalProps: ['heading', 'className'],
  },
  {
    name: 'EmptyState',
    surface: 'ops',
    path: 'ops/EmptyState.tsx',
    requiredProps: ['title'],
    optionalProps: ['description', 'action', 'className'],
  },
  {
    name: 'RiskQueue',
    surface: 'ops',
    path: 'ops/RiskQueue.tsx',
    requiredProps: ['heading', 'items'],
    optionalProps: ['onAction', 'className'],
  },
] as const;

const PUBLIC_ALLOWED = [
  'PublicShell',
  'PublicNav',
  'MarketingHero',
  'FeatureBento',
  'ProductShowcase',
  'TestimonialRail',
  'ProcessSection',
  'CTABand',
  'ConfirmStage',
  'ScheduleRail',
  'BrandFooter',
  'LogoMarquee',
  'SpotlightCard',
  'AccentBeam',
  'CredentialStrip',
  'ResultRail',
  'BookingPanel',
  'AiFeatureDeck',
  'AiFeaturePanel',
  'Button',
  'Badge',
  'UiIcon',
] as const;

const OPS_ALLOWED = [
  'OpsShell',
  'PageHeader',
  'StatCard',
  'ChartCard',
  'DataTable',
  'FilterBar',
  'ActivityFeed',
  'EmptyState',
  'RiskQueue',
  'AiFeaturePanel',
  'Button',
  'Input',
  'Select',
  'Badge',
  'Tabs',
  'Dialog',
  'UiIcon',
] as const;

export const SKELETONS: readonly SkeletonDefinition[] = [
  {
    id: 'public-home',
    surface: 'public',
    shell: 'PublicShell',
    purpose:
      'Marketing landing — only hero/cta/footer are required; recipe/template chooses the middle stack.',
    requiredSections: ['shell', 'hero', 'cta', 'footer'],
    optionalSections: [
      'trust',
      'credentials',
      'features',
      'spotlight',
      'showcase',
      'results',
      'process',
      'testimonials',
      'booking',
    ],
    recommendedOrder: [
      'shell',
      'hero',
      'trust',
      'credentials',
      'features',
      'spotlight',
      'showcase',
      'results',
      'process',
      'testimonials',
      'booking',
      'cta',
      'footer',
    ],
    allowedComponents: [...PUBLIC_ALLOWED],
    supportedVariants: {
      MarketingHero: ['cinematic', 'service', 'compact', 'product', 'editorial', 'split'],
      FeatureBento: ['bento', 'grid', 'alternating'],
    },
  },
  {
    id: 'public-service',
    surface: 'public',
    shell: 'PublicShell',
    purpose: 'Service listing / category page — prefer ScheduleRail over card grids.',
    requiredSections: ['shell', 'hero', 'features', 'cta', 'footer'],
    optionalSections: ['process', 'testimonials', 'showcase'],
    recommendedOrder: ['shell', 'hero', 'features', 'showcase', 'process', 'testimonials', 'cta', 'footer'],
    allowedComponents: [...PUBLIC_ALLOWED, 'ScheduleRail', 'Badge'],
    supportedVariants: {
      MarketingHero: ['service', 'editorial', 'cinematic', 'compact', 'product', 'split'],
      FeatureBento: ['grid', 'alternating', 'bento'],
    },
  },
  {
    id: 'public-detail',
    surface: 'public',
    shell: 'PublicShell',
    purpose: 'Single product or treatment detail.',
    requiredSections: ['shell', 'hero', 'showcase', 'footer'],
    optionalSections: ['process', 'features', 'testimonials', 'credentials', 'booking', 'cta'],
    recommendedOrder: ['shell', 'hero', 'showcase', 'features', 'process', 'testimonials', 'cta', 'footer'],
    allowedComponents: [...PUBLIC_ALLOWED],
    supportedVariants: {
      MarketingHero: ['product', 'service', 'editorial', 'compact', 'split'],
      FeatureBento: ['alternating', 'grid'],
    },
  },
  {
    id: 'public-catalog',
    surface: 'public',
    shell: 'PublicShell',
    purpose: 'Browsable product / plan grid with filtering — merchandising, not storytelling.',
    requiredSections: ['shell', 'hero', 'showcase', 'footer'],
    optionalSections: ['trust', 'features', 'spotlight', 'testimonials', 'cta'],
    recommendedOrder: ['shell', 'hero', 'trust', 'showcase', 'features', 'spotlight', 'testimonials', 'cta', 'footer'],
    allowedComponents: [
      ...PUBLIC_ALLOWED,
      'ScheduleRail',
      'Input',
      'Select',
      'Tabs',
      'Card',
      'Table',
      'Dialog',
    ],
    supportedVariants: {
      MarketingHero: ['compact', 'editorial', 'product', 'split'],
      FeatureBento: ['grid', 'bento'],
    },
  },
  {
    id: 'public-utility',
    surface: 'public',
    shell: 'PublicShell',
    purpose:
      'Transactional flow (cart, checkout, order tracking, account, wishlist) — compact header and a task-focused workspace, no marketing sections.',
    requiredSections: ['shell', 'header', 'workspace', 'footer'],
    optionalSections: ['summary', 'spotlight', 'cta'],
    recommendedOrder: ['shell', 'header', 'workspace', 'summary', 'spotlight', 'cta', 'footer'],
    allowedComponents: [
      'PublicShell',
      'PublicNav',
      'PageHeader',
      'ConfirmStage',
      'Card',
      'Table',
      'Badge',
      'Button',
      'Input',
      'Select',
      'Tabs',
      'Dialog',
      'EmptyState',
      'SpotlightCard',
      'CTABand',
      'BrandFooter',
      'UiIcon',
    ],
    supportedVariants: {},
  },
  {
    id: 'public-booking',
    surface: 'public',
    shell: 'PublicShell',
    purpose: 'Booking / intake conversion flow surface.',
    requiredSections: ['shell', 'hero', 'booking', 'footer'],
    optionalSections: ['process', 'features', 'testimonials', 'cta', 'credentials', 'showcase'],
    recommendedOrder: ['shell', 'hero', 'credentials', 'process', 'features', 'testimonials', 'booking', 'cta', 'footer'],
    allowedComponents: [...PUBLIC_ALLOWED, 'Input', 'Select', 'Dialog'],
    supportedVariants: {
      MarketingHero: ['split', 'editorial'],
      FeatureBento: ['grid'],
    },
  },
  {
    id: 'ops-dashboard',
    surface: 'ops',
    shell: 'OpsShell',
    purpose:
      'Soft SaaS operations overview: main column (header, KPIs, chart, work list) + activity rail.',
    requiredSections: ['shell', 'header', 'kpis', 'chart', 'filters', 'table', 'activity'],
    optionalSections: ['risk'],
    recommendedOrder: ['shell', 'header', 'kpis', 'risk', 'chart', 'filters', 'table', 'activity'],
    allowedComponents: [...OPS_ALLOWED],
    supportedVariants: {
      ChartCard: ['area', 'bar'],
      StatCard: ['card', 'strip'],
    },
  },
  {
    id: 'ops-list',
    surface: 'ops',
    shell: 'OpsShell',
    purpose: 'Searchable operational list view.',
    requiredSections: ['shell', 'header', 'filters', 'table'],
    optionalSections: ['empty'],
    recommendedOrder: ['shell', 'header', 'filters', 'table', 'empty'],
    allowedComponents: [...OPS_ALLOWED],
    supportedVariants: {},
  },
  {
    id: 'ops-detail',
    surface: 'ops',
    shell: 'OpsShell',
    purpose: 'Single record detail with activity context.',
    requiredSections: ['shell', 'header', 'table', 'activity'],
    optionalSections: ['kpis'],
    recommendedOrder: ['shell', 'header', 'kpis', 'table', 'activity'],
    allowedComponents: [...OPS_ALLOWED],
    supportedVariants: {},
  },
  {
    id: 'ops-settings',
    surface: 'ops',
    shell: 'OpsShell',
    purpose: 'Settings / configuration surface.',
    requiredSections: ['shell', 'header'],
    optionalSections: ['filters', 'table', 'empty'],
    recommendedOrder: ['shell', 'header', 'filters', 'table', 'empty'],
    allowedComponents: [...OPS_ALLOWED],
    supportedVariants: {},
  },
] as const;

export function getSkeleton(id: SkeletonId): SkeletonDefinition {
  const skeleton = SKELETONS.find((item) => item.id === id);
  if (!skeleton) {
    throw new Error(`Unknown skeleton id: ${id}`);
  }
  return skeleton;
}

export function getCatalogueComponentNames(): string[] {
  return CATALOGUE_COMPONENTS.map((item) => item.name);
}
