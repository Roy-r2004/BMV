import AppExperience from '../../preview/AppExperience';
import type { ShowcaseDemoProps } from './showcaseRegistry';

/** Fallback for industries without a bespoke demo yet */
export default function GenericShowcaseDemo({ showcase, onRequestClick }: ShowcaseDemoProps) {
  return (
    <div className="sol-detail-demo__showcase">
      <p className="sol-detail-demo__hint">
        <span className="sol-detail-demo__hint-dot" aria-hidden />
        Preview demo — bespoke UI for this industry is coming next.
      </p>
      <div className="sol-detail-demo__experience sol-detail-demo__experience--cinematic">
        <AppExperience
          demo={showcase.demo}
          businessName={showcase.businessName}
          industry={showcase.industry}
          websiteTone
          cinematic
        />
      </div>
      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          This is the same platform we customize for <strong>{showcase.businessName}</strong>.
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my business
        </button>
      </div>
    </div>
  );
}
