import type { PreviewResponse } from '../types/request';

/** Whether the analysis section should appear at all. */
export function hasReferenceAnalysis(preview: PreviewResponse): boolean {
  return Boolean(
    preview.screenshot_analysis?.trim()
    || preview.reference_url
    || preview.what_you_like,
  );
}

/** Rich AI-written analysis only — never the raw metadata fallback. */
export function getAiAnalysisText(preview: PreviewResponse): string | null {
  const text = preview.screenshot_analysis?.trim();
  if (!text || isMetadataDump(text)) return null;
  return fixEncoding(text);
}

function isMetadataDump(text: string): boolean {
  return /\*\*Reference tool:\*\*/i.test(text) && /\*\*What you admire:\*\*/i.test(text);
}

/** Fix common UTF-8 mojibake from scraped pages (â€œ → "). */
export function fixEncoding(text: string): string {
  return text
    .replace(/â€™/g, "'")
    .replace(/â€˜/g, "'")
    .replace(/â€œ/g, '"')
    .replace(/â€\u009d/g, '"')
    .replace(/â€"/g, '—')
    .replace(/â€"/g, '–')
    .replace(/Ã©/g, 'é')
    .replace(/Ã /g, 'à');
}
