export interface VisualTheme {
  style: string;
  primary_color: string;
  secondary_color: string;
  background_color: string;
  font_style: string;
}

export interface HeroSection {
  headline: string;
  subheadline: string;
  primary_cta: string;
  secondary_cta: string;
}

export interface FeatureCard {
  title: string;
  description: string;
  icon: string;
}

export interface JourneyStep {
  step: number;
  title: string;
  description: string;
}

export interface ScreenMockup {
  screen_name: string;
  screen_type: string;
  description: string;
  visible_elements: string[];
}

export interface DashboardCard {
  title: string;
  value: string;
  description: string;
}

export interface AdminDashboardPreview {
  should_show: boolean;
  cards: DashboardCard[];
  recent_activity: string[];
}

export interface AIWorkflowStep {
  step: number;
  title: string;
  description: string;
}

export interface FinalCTA {
  headline: string;
  description: string;
  button_text: string;
}

export interface PreviewService {
  name: string;
  description: string;
  duration?: string;
  cta?: string;
}

export interface PreviewConversation {
  name: string;
  channel: string;
  preview: string;
  time: string;
  unread?: boolean;
}

export interface PreviewMessage {
  role: 'user' | 'team';
  text: string;
  /** Showcase demos — marks AI-drafted or auto-sent replies */
  ai_assisted?: boolean;
}

export interface PreviewAppointment {
  time: string;
  client: string;
  service: string;
  status: 'confirmed' | 'available' | 'pending';
}

export interface PreviewLead {
  name: string;
  source: string;
  service: string;
  status: string;
}

export interface PreviewContent {
  image_theme?: 'wellness' | 'fitness' | 'saas' | 'generic';
  website?: {
    eyebrow?: string;
    services_label?: string;
    services?: PreviewService[];
    about_paragraphs?: string[];
    contact_intro?: string;
    form_fields?: string[];
    social_proof?: string;
    hero_highlight?: { label: string; title: string; subtitle: string };
    /** Floating automation badges on cinematic hero */
    ai_chips?: string[];
    automation_title?: string;
    automation_subtitle?: string;
    testimonial?: { quote: string; name: string; role: string; rating?: number };
  };
  inbox?: {
    conversations?: PreviewConversation[];
    messages?: PreviewMessage[];
    booked_banner?: string;
  };
  schedule?: {
    appointments?: PreviewAppointment[];
    week_stat?: string;
    week_detail?: string;
  };
  dashboard?: {
    leads?: PreviewLead[];
  };
}

export interface AppConfigTab {
  id: 'website' | 'inbox' | 'schedule' | 'dashboard';
  label: string;
  short: string;
  url_segment?: string;
}

export interface AppConfig {
  enabled_modules?: Array<'website' | 'inbox' | 'schedule' | 'dashboard'>;
  schedule_variant?: 'progress' | 'calendar';
  header_variant?: 'light' | 'dark';
  hero_layout?: 'split' | 'centered';
  home_sections?: Array<'hero' | 'features' | 'ai' | 'programs' | 'journey' | 'testimonial' | 'cta'>;
  website_nav?: Array<{ id: 'home' | 'services' | 'about' | 'contact'; label: string }>;
  tabs?: AppConfigTab[];
  features_section?: { title?: string; subtitle?: string };
  inbox?: {
    title?: string;
    subtitle?: string;
    footer?: string;
    status_label?: string;
    quick_replies?: string[];
  };
  schedule?: {
    title?: string;
    subtitle?: string;
    add_button?: string;
    today_label?: string;
    slots_label?: string;
  };
  dashboard?: {
    greeting?: string;
    subtitle?: string;
    nav?: Array<{ id: string; label: string }>;
    leads_panel?: string;
    bookings_panel?: string;
    clients_panel?: string;
    table_headers?: { client: string; source: string; service: string; status: string };
    fourth_metric?: { title: string; value: string; sub: string };
    settings_labels?: string[];
  };
  leads_panel_mode?: 'table' | 'adherence';
  bookings_panel_mode?: 'appointments' | 'programs';
}

export interface VisualDemo {
  product_name: string;
  visual_theme: VisualTheme;
  hero: HeroSection;
  feature_cards: FeatureCard[];
  user_journey: JourneyStep[];
  screen_mockups: ScreenMockup[];
  admin_dashboard_preview: AdminDashboardPreview;
  ai_workflow: AIWorkflowStep[];
  final_cta: FinalCTA;
  preview_content?: PreviewContent;
  app_config?: AppConfig;
}

// ─── Role-based page preview types ────────────────────────────────────────────

export interface RolePageFeature {
  icon: string;
  title: string;
  desc: string;
}

export interface RolePageService {
  name: string;
  tagline?: string;
  badge?: string | null;
  duration?: string;
  desc?: string;
}

export interface RolePageTestimonial {
  name: string;
  role: string;
  text: string;
  rating: number;
}

export interface RolePageMetric {
  label: string;
  value: string;
  change: string;
  trend: 'up' | 'down' | 'flat';
}

export interface RolePageBooking {
  client: string;
  service: string;
  time: string;
  status: 'confirmed' | 'pending' | 'cancelled';
}

export interface RolePageMessage {
  from: string;
  preview: string;
  time: string;
  unread: boolean;
}

export interface RolePageClient {
  name: string;
  service: string;
  since: string;
  sessions: number;
  status: 'active' | 'new' | 'inactive';
  last_seen: string;
}

export interface GeneratedPage {
  id: string;
  title: string;
  /** Raw AI-generated HTML for this page */
  html: string;
}

export interface GeneratedRole {
  id: string;
  label: string;
  tagline?: string;
  icon: string;
  accent?: string;
  defaultPath?: string;
  /** Single bundled website — navigate inside the iframe like a real site */
  site_html?: string;
  pages?: GeneratedPage[];
}

export interface PreviewAppRole {
  id: string;
  label: string;
  icon?: string;
  accent?: string;
  defaultPath?: string;
}

export interface PreviewAppInfo {
  url: string | null;
  status: 'ready' | 'failed' | 'building' | 'rebuilding';
  roles?: PreviewAppRole[];
  routes?: { path: string; title: string; role_id?: string }[];
  design_direction?: string;
  fallback_pages?: string[];
  last_refinement_error?: string | null;
  /** Epoch seconds — changes on rebuild so the iframe remounts past error boundaries. */
  built_at?: number | null;
}

export interface GeneratedPages {
  roles?: GeneratedRole[];
  preview_app?: PreviewAppInfo;
  experience_plan?: Record<string, unknown>;
}

// ─── Preview response ──────────────────────────────────────────────────────────

export interface PreviewResponse {
  id: number;
  business_name: string;
  business_fit_score: number | null;
  concept_name: string | null;
  preview_summary: string | null;
  preview_features: string[];
  ai_features?: Array<{
    id: string;
    name: string;
    description?: string;
    category?: string;
    surface?: string;
  }>;
  visual_demo: VisualDemo | null;
  generated_pages: GeneratedPages | null;
  status: string;
  is_generating: boolean;
  industry?: string | null;
  timeline?: string | null;
  budget_range?: string | null;
  desired_outcome?: string | null;
  main_problem?: string | null;
  screenshot_analysis?: string | null;
  reference_analysis?: string | null;
  reference_url?: string | null;
  what_you_like?: string | null;
  mvp_blueprint?: string | null;
  technical_plan?: string | null;
  /** AI-written Launch/Growth/Custom + add-ons (no prices). */
  build_plans?: {
    recommended_plan_id?: 'launch' | 'growth' | 'custom';
    plans?: Array<{
      id: 'launch' | 'growth' | 'custom';
      name: string;
      tagline: string;
      timeline: string;
      bestFor: string;
      includes: string[];
      badge?: string | null;
      highlight?: boolean;
    }>;
    addons?: Array<{
      id: string;
      name: string;
      description?: string;
      whyForYou?: string;
      includedIn?: Array<'launch' | 'growth'>;
    }>;
  } | null;
  build_requested?: boolean;
}

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface ChatSendResponse {
  reply: string;
  changes_made: string[];
  preview_updated: boolean;
  preview_rebuild_started?: boolean;
  concept_name?: string | null;
  preview_summary?: string | null;
  preview_features?: string[];
  business_fit_score?: number | null;
  visual_demo?: VisualDemo | null;
}

export interface RequestListItem {
  id: number;
  business_name: string;
  industry: string | null;
  email: string;
  whatsapp: string | null;
  status: string;
  created_at: string;
  business_fit_score: number | null;
  build_requested: boolean;
  cost_usd?: number;
  ai_calls?: number;
  ai_tokens?: number;
}

export interface RequestDetail {
  id: number;
  business_name: string;
  industry: string | null;
  business_description: string;
  target_customers: string | null;
  main_problem: string | null;
  reference_url: string | null;
  reference_file_path: string | null;
  what_you_like: string | null;
  desired_outcome: string | null;
  needs_ai: string | null;
  budget_range: string | null;
  timeline: string | null;
  email: string;
  whatsapp: string | null;
  status: string;
  admin_notes: string | null;
  screenshot_analysis: string | null;
  mvp_blueprint: string | null;
  visual_demo_json: string | null;
  technical_plan: string | null;
  proposal_draft: string | null;
  business_fit_score: number | null;
  concept_name: string | null;
  preview_summary: string | null;
  preview_features: string | null;
  reference_metadata: string | null;
  build_requested: boolean;
  build_requested_at: string | null;
  visual_demo_generated_at: string | null;
  created_at: string;
  updated_at: string;
}

export const STATUS_OPTIONS = [
  'all',
  'new',
  'reviewing',
  'proposal sent',
  'accepted',
  'in progress',
  'delivered',
  'lost',
] as const;
