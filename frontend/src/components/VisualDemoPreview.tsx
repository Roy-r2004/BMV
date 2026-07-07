import type { VisualDemo } from '../types/request';
import LiveSitePreview from './preview/LiveSitePreview';
import type { PreviewMode } from './preview/LiveSitePreview';

interface Props {
  demo: VisualDemo | null;
  businessName?: string;
  industry?: string | null;
  previewFeatures?: string[];
  immersive?: boolean;
  mode?: PreviewMode;
}

export default function VisualDemoPreview({ demo, businessName, industry, previewFeatures, immersive = false, mode = 'product' }: Props) {
  if (!demo) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-16 text-center shadow-sm">
        <div className="w-14 h-14 border-2 border-indigo-200 border-t-indigo-500 rounded-full animate-spin mx-auto mb-5" />
        <p className="text-slate-500">Your product is being designed…</p>
      </div>
    );
  }

  return <LiveSitePreview demo={demo} businessName={businessName} industry={industry} previewFeatures={previewFeatures} immersive={immersive} mode={mode} />;
}
