export interface OverlaySection {
  id: string;
  title: string;
  subtitle?: string;
  body?: string;
  bullets?: string[];
  /** highlight | cards | banner | stats */
  style?: string;
  ctaLabel?: string;
}

export interface OverlayStat {
  label: string;
  value: string;
}

/** Virtual file written by the customization agent (per-user, not in shared repo) */
export interface GeneratedFile {
  id: string;
  path: string;
  kind: 'css' | 'markup';
  content: string;
}

export interface OverlayElementEdit {
  id: string;
  selector: string;
  text?: string;
  placeholder?: string;
  value?: string;
  ariaLabel?: string;
}

export interface UserPublic {
  id: number;
  name: string;
  email: string;
  is_admin?: boolean;
  created_at: string;
}

export interface AuthResponse {
  token: string;
  user: UserPublic;
}

export interface SolutionOverlay {
  businessName?: string;
  productName?: string;
  tagline?: string;
  heroHeadline?: string;
  heroSub?: string;
  primaryColor?: string;
  secondaryColor?: string;
  backgroundColor?: string;
  accentColor?: string;
  ctaPrimary?: string;
  ctaSecondary?: string;
  aiChips?: string[];
  heroStats?: OverlayStat[];
  /** User-added page sections (merged by id) */
  sections?: OverlaySection[];
  removeSectionIds?: string[];
  /** Agent-written virtual files (CSS, HTML blocks) */
  files?: GeneratedFile[];
  removeFileIds?: string[];
  /** Direct edits to selected preview DOM elements */
  elementEdits?: OverlayElementEdit[];
  removeElementEditIds?: string[];
  /** Catalog feature IDs the user has one-click integrated */
  integratedFeatures?: string[];
  /** Per-feature contribution snapshot for undo/remove */
  catalogContributions?: Record<string, CatalogFeatureContribution>;
  notes?: string[];
}

export interface CatalogFeatureContribution {
  sectionIds?: string[];
  aiChips?: string[];
  ctaPrimary?: string;
  ctaSecondary?: string;
  heroStats?: OverlayStat[];
}

export interface SolutionEditMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  attachment_name?: string | null;
  created_at: string;
}

export interface SolutionChatSendResponse {
  reply: string;
  changes_made: string[];
  overlay: SolutionOverlay;
  workspace_updated: boolean;
}
