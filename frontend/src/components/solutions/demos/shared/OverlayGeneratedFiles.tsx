import { useShowcaseOverlay } from '../../../../context/ShowcaseOverlayContext';
import type { GeneratedFile } from '../../../../types/auth';

interface Props {
  solutionId: string;
}

function normalizeGeneratedCss(content: string): string {
  return content
    .replace(/\.overlay-feature-widget__inline\.([a-z0-9-]+-widget)/gi, '.overlay-feature-widget.$1')
    .replace(/(\.[a-z0-9-]+-widget)\s+h3/gi, '$1 h2');
}

function MarkupBlock({ file }: { file: GeneratedFile }) {
  return (
    <div
      className="overlay-generated-markup"
      data-codegen-path={file.path}
      // User-owned workspace HTML from sanitized agent output
      dangerouslySetInnerHTML={{ __html: file.content }}
    />
  );
}

/** Injects per-user virtual CSS/HTML files written by the customization agent */
export default function OverlayGeneratedFiles({ solutionId }: Props) {
  const { overlay } = useShowcaseOverlay();
  const files = overlay.files;
  if (!files?.length) return null;

  const cssFiles = files.filter((f) => f.kind === 'css');
  const markupFiles = files.filter((f) => f.kind === 'markup');

  return (
    <div className={`user-codegen user-codegen-${solutionId}`} aria-label="Your custom code">
      {cssFiles.map((f) => (
        <style key={f.id} data-codegen-path={f.path}>
          {normalizeGeneratedCss(f.content)}
        </style>
      ))}
      {markupFiles.length > 0 && (
        <div className="overlay-generated-files">
          {markupFiles.map((f) => (
            <MarkupBlock key={f.id} file={f} />
          ))}
        </div>
      )}
    </div>
  );
}
