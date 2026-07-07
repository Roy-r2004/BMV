import type { PreviewResponse } from '../../types/request';
import type { DeliveryNavItem } from './DeliveryNavigator';
import { hasReferenceAnalysis } from '../../utils/referenceAnalysis';

export function buildDeliveryNavItems(
  preview: PreviewResponse,
  liveSiteAbove = false,
): DeliveryNavItem[] {
  const hasAnalysis = hasReferenceAnalysis(preview);

  return [
    ...(liveSiteAbove
      ? [{ id: 'live-product', label: 'Live Product', short: 'Product', ready: Boolean(preview.visual_demo) }]
      : [{ id: 'delivery-live-site', label: 'Live Product', short: 'Product', ready: Boolean(preview.visual_demo) }]),
    { id: 'delivery-overview', label: 'Overview', short: 'Overview', ready: Boolean(preview.concept_name) },
    { id: 'delivery-analysis', label: 'Analysis', short: 'Analysis', ready: hasAnalysis },
    { id: 'delivery-blueprint', label: 'Blueprint', short: 'Plan', ready: Boolean(preview.mvp_blueprint) },
    { id: 'delivery-technical', label: 'Technical', short: 'Tech', ready: Boolean(preview.technical_plan) },
    { id: 'delivery-proposal', label: 'Proposal', short: 'Proposal', ready: Boolean(preview.proposal_draft) },
  ];
}
