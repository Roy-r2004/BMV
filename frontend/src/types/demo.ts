export interface DemoListItem {
  id: number;
  business_name: string;
  concept_name: string;
  industry: string | null;
  business_fit_score: number | null;
  preview_summary: string | null;
  preview_features: string[];
  primary_color: string | null;
  secondary_color: string | null;
  reference_url: string | null;
  created_at: string;
}

export interface DemoListResponse {
  demos: DemoListItem[];
}
