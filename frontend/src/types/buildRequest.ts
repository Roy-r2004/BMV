export interface BuildRequestContact {
  contact_name: string;
  email: string;
  whatsapp?: string;
  notes?: string;
  package_id?: 'launch' | 'growth' | 'custom';
  addon_ids?: string[];
  estimate_from_usd?: number;
}
