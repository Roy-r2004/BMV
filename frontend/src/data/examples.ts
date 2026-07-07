export interface ExampleOutput {
  id: string;
  name: string;
  score: number;
  industry: string;
  accent: string;
  icon: string;
  tagline: string;
  reference: string;
  inspiredBy: string;
  features: string[];
  screens: string[];
}

/** Example concepts — inspired by production systems the engineering team has shipped */
export const EXAMPLE_OUTPUTS: ExampleOutput[] = [
  {
    id: 'business-xray',
    name: 'AI Business Intelligence Hub',
    score: 88,
    industry: 'Sales & Marketing',
    accent: 'from-blue-600 to-indigo-600',
    icon: '📊',
    tagline: 'Enter any company URL — get SWOT, market gaps, and a competitive attack plan in under 30 seconds.',
    reference: 'Inspired by competitive intelligence SaaS workflows',
    inspiredBy: 'AI Business X-Ray',
    features: ['Autonomous company crawling', 'SWOT & gap analysis', 'Side-by-side comparisons', 'PDF export & sharing', 'Bulk analysis mode'],
    screens: ['Analysis dashboard', 'Report viewer', 'Compare view', 'Admin panel'],
  },
  {
    id: 'hirewise',
    name: 'Smart Recruitment Portal',
    score: 84,
    industry: 'HR & Recruitment',
    accent: 'from-cyan-500 to-teal-600',
    icon: '🎯',
    tagline: 'AI matches CVs to job requirements, ranks candidates, and cuts hours of manual screening.',
    reference: 'Inspired by AI-powered hiring platforms',
    inspiredBy: 'HireWise',
    features: ['CV–job matching engine', 'Match score ranking', 'Admin & candidate portals', 'Resume processing', 'Workflow automation'],
    screens: ['Candidate portal', 'Admin dashboard', 'Match results', 'Job posting'],
  },
  {
    id: 'cashpath',
    name: 'AI Expense Assistant',
    score: 81,
    industry: 'FinTech / SMB',
    accent: 'from-emerald-500 to-cyan-600',
    icon: '💳',
    tagline: 'Smart categorization, spending insights, and predictive analytics for business owners.',
    reference: 'Inspired by expense intelligence apps',
    inspiredBy: 'CashPath',
    features: ['Smart categorization', 'Predictive analytics', 'Spending insights', 'Mobile + web sync', 'Actionable recommendations'],
    screens: ['Expense feed', 'Insights dashboard', 'Categories', 'Reports'],
  },
  {
    id: 'clinic',
    name: 'AI Clinic Booking Assistant',
    score: 86,
    industry: 'Healthcare & Wellness',
    accent: 'from-blue-500 to-cyan-500',
    icon: '🏥',
    tagline: 'Turn Instagram and WhatsApp inquiries into booked appointments with an AI intake assistant.',
    reference: 'Inspired by booking + CRM workflows',
    inspiredBy: 'Healthcare automation patterns',
    features: ['Lead intake assistant', 'Treatment FAQ bot', 'Booking flow', 'Admin dashboard', 'Daily summaries'],
    screens: ['Patient booking', 'AI chat', 'Staff dashboard', 'Calendar'],
  },
  {
    id: 'scaleyou',
    name: 'Autonomous Sales Engine',
    score: 85,
    industry: 'Sales & Marketing',
    accent: 'from-violet-500 to-blue-600',
    icon: '⚡',
    tagline: 'Launch a business vertical and let AI find leads, send outreach, handle replies, and book meetings.',
    reference: 'Inspired by autonomous revenue systems',
    inspiredBy: 'ScaleYou',
    features: ['Lead discovery', 'Personalized outreach', 'Reply handling', 'Meeting booking', 'Self-optimizing campaigns'],
    screens: ['Campaign hub', 'Lead pipeline', 'Outreach editor', 'Analytics'],
  },
  {
    id: 'visioncommerce',
    name: 'Smart Marketplace Platform',
    score: 83,
    industry: 'E-commerce',
    accent: 'from-indigo-500 to-purple-600',
    icon: '🛒',
    tagline: 'Image-based listings, AI chat search, vector similarity, and real-time personalized recommendations.',
    reference: 'Inspired by AI-powered marketplaces',
    inspiredBy: 'VisionCommerce',
    features: ['Image metadata generation', 'LLM product search', 'Vector similarity', 'Real-time chat', 'Recommendation engine'],
    screens: ['Storefront', 'Product detail', 'AI search', 'Seller admin'],
  },
];

export const INDUSTRIES = ['All', ...Array.from(new Set(EXAMPLE_OUTPUTS.map((e) => e.industry)))];
