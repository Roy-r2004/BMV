import { useShowcaseOverlay } from '../../../../context/ShowcaseOverlayContext';
import { getCatalogForSolution, type AIFeatureCatalogItem } from '../../../../data/aiFeatureCatalog';
import type { OverlaySection } from '../../../../types/auth';
import CatalogFeatureWidget from './CatalogFeatureWidget';

function isCatalogFeature(feature: AIFeatureCatalogItem | undefined): feature is AIFeatureCatalogItem {
  return Boolean(feature);
}

function useIntegratedCatalogFeatures(): AIFeatureCatalogItem[] {
  const { overlay, solutionId } = useShowcaseOverlay();
  const ids = overlay.integratedFeatures ?? [];
  if (!solutionId || ids.length === 0) return [];
  const catalog = getCatalogForSolution(solutionId);
  return ids
    .map((id) => catalog.find((feature) => feature.id === id))
    .filter(isCatalogFeature);
}

function SectionBlock({ section }: { section: OverlaySection }) {
  const style = section.style ?? 'highlight';

  if (style === 'stats' && section.bullets?.length) {
    return (
      <section
        className="overlay-custom-section overlay-custom-section--stats"
        data-overlay-target={`section-${section.id}`}
      >
        <h2 className="overlay-custom-section__title">{section.title}</h2>
        {section.subtitle && <p className="overlay-custom-section__sub">{section.subtitle}</p>}
        <div className="overlay-custom-section__stats">
          {section.bullets.map((b) => {
            const [value, ...rest] = b.split('—').map((s) => s.trim());
            return (
              <div key={b} className="overlay-custom-section__stat">
                <strong>{value || b}</strong>
                <span>{rest.join(' — ') || section.body}</span>
              </div>
            );
          })}
        </div>
      </section>
    );
  }

  if (style === 'cards' && section.bullets?.length) {
    return (
      <section
        className="overlay-custom-section overlay-custom-section--cards"
        data-overlay-target={`section-${section.id}`}
      >
        <h2 className="overlay-custom-section__title">{section.title}</h2>
        {section.subtitle && <p className="overlay-custom-section__sub">{section.subtitle}</p>}
        <div className="overlay-custom-section__cards">
          {section.bullets.map((item) => (
            <article key={item} className="overlay-custom-section__card">
              <p>{item}</p>
            </article>
          ))}
        </div>
        {section.ctaLabel && (
          <button type="button" className="overlay-custom-section__cta">
            {section.ctaLabel}
          </button>
        )}
      </section>
    );
  }

  if (style === 'banner') {
    return (
      <section
        className="overlay-custom-section overlay-custom-section--banner"
        data-overlay-target={`section-${section.id}`}
      >
        <div>
          <h2 className="overlay-custom-section__title">{section.title}</h2>
          {section.subtitle && <p className="overlay-custom-section__sub">{section.subtitle}</p>}
          {section.body && <p className="overlay-custom-section__body">{section.body}</p>}
        </div>
        {section.ctaLabel && (
          <button type="button" className="overlay-custom-section__cta">
            {section.ctaLabel}
          </button>
        )}
      </section>
    );
  }

  return (
    <section
      className="overlay-custom-section overlay-custom-section--highlight"
      data-overlay-target={`section-${section.id}`}
    >
      <h2 className="overlay-custom-section__title">{section.title}</h2>
      {section.subtitle && <p className="overlay-custom-section__sub">{section.subtitle}</p>}
      {section.body && <p className="overlay-custom-section__body">{section.body}</p>}
      {section.bullets && section.bullets.length > 0 && (
        <ul className="overlay-custom-section__list">
          {section.bullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}
      {section.ctaLabel && (
        <button type="button" className="overlay-custom-section__cta">
          {section.ctaLabel}
        </button>
      )}
    </section>
  );
}

/** Renders AI-added sections inside the live demo site */
export default function OverlayCustomSections() {
  const { overlay } = useShowcaseOverlay();
  const sections = overlay.sections;
  const catalogFeatures = useIntegratedCatalogFeatures();
  const catalogSectionIds = new Set(
    catalogFeatures.flatMap((feature) => (feature.patch.sections ?? []).map((section) => section.id)),
  );
  const customSections = sections?.filter((section) => !catalogSectionIds.has(section.id));
  const hasSections = Boolean(customSections?.length);
  const hasCatalogWidgets = catalogFeatures.length > 0;
  if (!hasSections && !hasCatalogWidgets) return null;

  return (
    <div className="overlay-custom-sections" aria-label="Your custom sections">
      {catalogFeatures.map((feature) => (
        <CatalogFeatureWidget key={feature.id} feature={feature} />
      ))}
      {customSections?.map((s) => (
        <SectionBlock key={s.id} section={s} />
      ))}
    </div>
  );
}
