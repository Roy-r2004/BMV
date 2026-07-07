import type { VisualDemo } from '../../types/request';
import AppExperience from './AppExperience';
import WebsiteExperience from './WebsiteExperience';
import { resolvePreviewContent } from './demoContent';
import { fontClass } from './liveSiteTheme';

export type PreviewMode = 'website' | 'product';

interface Props {
  demo: VisualDemo;
  businessName?: string;
  industry?: string | null;
  previewFeatures?: string[];
  immersive?: boolean;
  mode?: PreviewMode;
}

export default function LiveSitePreview({ demo, businessName, industry, previewFeatures, immersive = false, mode = 'website' }: Props) {
  const content = resolvePreviewContent(demo, { businessName, industry, previewFeatures });
  const font = fontClass(demo.visual_theme?.font_style);
  const bg = immersive ? 'transparent' : content.imageTheme === 'fitness' ? '#fffbeb' : demo.visual_theme?.background_color || '#ffffff';
  const websiteMode = mode === 'website';

  return (
    <div
      className={`live-site-preview ${immersive ? 'live-site-preview--immersive live-site-preview--app h-full' : ''} ${websiteMode ? 'live-site-preview--website' : ''} ${font}`}
      style={{ backgroundColor: immersive ? 'transparent' : bg }}
    >
      {websiteMode ? (
        <WebsiteExperience demo={demo} businessName={businessName} industry={industry} previewFeatures={previewFeatures} />
      ) : (
        <AppExperience demo={demo} businessName={businessName} industry={industry} previewFeatures={previewFeatures} />
      )}
    </div>
  );
}
