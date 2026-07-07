import { useState } from 'react';
import type { VisualDemo } from '../../types/request';
import { resolvePreviewContent } from './demoContent';
import { resolvePreviewShell } from './resolveAppShell';
import { fontClass } from './liveSiteTheme';
import DesktopWindow from './DesktopWindow';
import PublicWebsiteView, { type WebsitePage } from './app/PublicWebsiteView';

interface HistoryEntry {
  page: WebsitePage;
}

interface Props {
  demo: VisualDemo;
  businessName?: string;
  industry?: string | null;
  previewFeatures?: string[];
}

export default function WebsiteExperience({ demo, businessName, industry, previewFeatures }: Props) {
  const content = resolvePreviewContent(demo, { businessName, industry, previewFeatures });
  const branding = resolvePreviewShell(demo, content.imageTheme);
  const font = fontClass(demo.visual_theme?.font_style);
  const [page, setPage] = useState<WebsitePage>('home');
  const [history, setHistory] = useState<HistoryEntry[]>([{ page: 'home' }]);
  const [historyIdx, setHistoryIdx] = useState(0);

  const siteSlug = businessName?.toLowerCase().replace(/[^a-z0-9]/g, '') || 'yourbusiness';
  const currentUrl = `https://${siteSlug}.com${page === 'home' ? '' : `/${page}`}`;

  const navigatePage = (nextPage: WebsitePage) => {
    setPage(nextPage);
    setHistory((h) => [...h.slice(0, historyIdx + 1), { page: nextPage }]);
    setHistoryIdx((i) => i + 1);
  };

  const goBack = () => {
    if (historyIdx <= 0) return;
    const nextIdx = historyIdx - 1;
    setHistoryIdx(nextIdx);
    setPage(history[nextIdx].page);
  };

  const goForward = () => {
    if (historyIdx >= history.length - 1) return;
    const nextIdx = historyIdx + 1;
    setHistoryIdx(nextIdx);
    setPage(history[nextIdx].page);
  };

  return (
    <div className={`website-experience ${font}`}>
      <DesktopWindow
        title={businessName || demo.product_name}
        url={currentUrl}
        canGoBack={historyIdx > 0}
        canGoForward={historyIdx < history.length - 1}
        onBack={goBack}
        onForward={goForward}
      >
        <div className="website-experience__viewport">
          <PublicWebsiteView
            demo={demo}
            businessName={businessName}
            industry={industry}
            previewFeatures={previewFeatures}
            branding={branding}
            content={content}
            primary={branding.primary}
            secondary={branding.secondary}
            page={page}
            onNavigate={navigatePage}
            websiteTone
          />
        </div>
      </DesktopWindow>
    </div>
  );
}
