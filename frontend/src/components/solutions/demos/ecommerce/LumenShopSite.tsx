import { useCallback, useMemo, useRef, useState } from 'react';
import { IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import {
  CATEGORIES,
  IMAGE_SEARCH_PRESETS,
  PRODUCTS,
  STYLE_BUNDLES,
  STORE,
  filterCatalog,
  getProduct,
  searchByImage,
  searchProducts,
  type ImageSearchPreset,
  type PlacedOrder,
  type Product,
  type ProductCategory,
} from './lumenData.ts';
import LumenShopChat from './LumenShopChat.tsx';
import OverlayCustomSections from '../shared/OverlayCustomSections.tsx';
import { onLumenImageError } from './lumenImageFallback.ts';
import { OverlayAiChips, OverlayPlainHero, OverlayPlainSub } from '../shared/overlayUi.tsx';

const SEARCH_HINTS = [
  'warm minimalist lamp for bedroom',
  'cozy neutral throw',
  'sculptural decor under $50',
];

const TRUST = [
  { label: 'Free shipping', detail: 'On orders $75 and up' },
  { label: '30-day returns', detail: 'Simple, no-hassle policy' },
  { label: 'Curated bundles', detail: 'Save up to 15% with AI edits' },
];

const CATEGORY_MOOD: Record<ProductCategory, { blurb: string; image: string }> = {
  lighting: {
    blurb: 'Warm glow, sculptural silhouettes, quiet evenings.',
    image: 'https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=1200&h=700&fit=crop&q=85',
  },
  textiles: {
    blurb: 'Soft layers, oatmeal tones, lived-in calm.',
    image: 'https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?w=1200&h=700&fit=crop&q=85',
  },
  decor: {
    blurb: 'Objects with presence — matte ceramic, brass, form.',
    image: 'https://images.unsplash.com/photo-1578500494198-246f612d3b3d?w=1200&h=700&fit=crop&q=85',
  },
  furniture: {
    blurb: 'Grounded pieces in walnut, oak, and quiet geometry.',
    image: 'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=1200&h=700&fit=crop&q=85',
  },
};

const FEATURED_IDS = ['arc-lamp', 'cloud-throw'] as const;

interface Props {
  onOrderPlaced: (order: PlacedOrder) => void;
}

function subLabel(product: Product) {
  const cat = CATEGORIES.find((c) => c.id === product.category);
  return cat?.subcategories.find((s) => s.id === product.subcategory)?.label ?? product.subcategory;
}

function ProductTile({ product, featured }: { product: Product; featured?: boolean }) {
  return (
    <article className={`lh-shop__tile ${featured ? 'lh-shop__tile--featured' : ''}`}>
      <div className="lh-shop__tile-media">
        <img src={product.imageUrl} alt={product.name} loading="lazy" onError={(e) => onLumenImageError(e, product.name)} />
        {product.lowStock && <span className="lh-shop__tile-badge">Low stock</span>}
        <div className="lh-shop__tile-hover">
          <button type="button">Add to cart</button>
        </div>
      </div>
      <div className="lh-shop__tile-body">
        <span className="lh-shop__tile-meta">{subLabel(product)}</span>
        <h3>{product.name}</h3>
        <p>{product.desc}</p>
        <div className="lh-shop__tile-foot">
          <strong>{product.price}</strong>
          <button type="button" className="lh-shop__tile-add">
            Add
          </button>
        </div>
      </div>
    </article>
  );
}

function IconCamera({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}

export default function LumenShopSite({ onOrderPlaced }: Props) {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<Product[] | null>(null);
  const [aiNote, setAiNote] = useState('');
  const [chatOpen, setChatOpen] = useState(false);
  const [category, setCategory] = useState<ProductCategory | null>(null);
  const [subcategory, setSubcategory] = useState<string | null>(null);
  const [visionPreset, setVisionPreset] = useState<ImageSearchPreset | null>(null);
  const [visionPreview, setVisionPreview] = useState<string | null>(null);
  const [showVisionMenu, setShowVisionMenu] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const shopRef = useRef<HTMLElement>(null);
  const bundlesRef = useRef<HTMLElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const activeCategory = useMemo(() => CATEGORIES.find((c) => c.id === category) ?? null, [category]);
  const featuredProducts = useMemo(
    () => FEATURED_IDS.map((id) => getProduct(id)).filter(Boolean) as Product[],
    [],
  );
  const primaryBundle = STYLE_BUNDLES[0];
  const secondaryBundles = STYLE_BUNDLES.slice(1);

  const clearVision = useCallback(() => {
    setVisionPreset(null);
    setVisionPreview(null);
  }, []);

  const applyCatalogFilter = useCallback(
    (cat: ProductCategory | null, sub: string | null) => {
      setCategory(cat);
      setSubcategory(sub);
      setResults(null);
      setAiNote('');
      clearVision();
      setQuery('');
    },
    [clearVision],
  );

  const runSearch = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setQuery(trimmed);
      setSearching(true);
      setResults(null);
      clearVision();
      window.setTimeout(() => {
        const found = searchProducts(trimmed, { category, subcategory });
        setResults(found.length ? found : filterCatalog({ category, subcategory }).slice(0, 4));
        setAiNote(
          found.length
            ? `Shopper AI matched ${found.length} piece${found.length > 1 ? 's' : ''} for "${trimmed}"${category ? ` in ${activeCategory?.label}` : ''} — ranked by style fit.`
            : `No exact match — showing closest alternatives for "${trimmed}".`,
        );
        setSearching(false);
        shopRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 680);
    },
    [category, subcategory, activeCategory, clearVision],
  );

  const runImageSearch = useCallback(
    (preset: ImageSearchPreset, previewUrl?: string) => {
      setShowVisionMenu(false);
      setVisionPreset(preset);
      setVisionPreview(previewUrl ?? preset.thumbnailUrl);
      setQuery('');
      setSearching(true);
      setResults(null);
      setAiNote('');
      window.setTimeout(() => {
        let found = searchByImage(preset.id);
        if (category) {
          const filtered = found.filter((p) => p.category === category && (!subcategory || p.subcategory === subcategory));
          if (filtered.length) found = filtered;
        }
        setResults(found);
        setAiNote('Vision matched materials & palette — ranked by visual similarity to your photo.');
        setSearching(false);
        shopRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 680);
    },
    [category, subcategory],
  );

  const handleFileUpload = (file: File | undefined) => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    const name = file.name.toLowerCase();
    let preset = IMAGE_SEARCH_PRESETS[0];
    if (name.includes('brass') || name.includes('lamp') || name.includes('metal')) preset = IMAGE_SEARCH_PRESETS[1];
    else if (name.includes('living') || name.includes('oak') || name.includes('wool')) preset = IMAGE_SEARCH_PRESETS[2];
    runImageSearch(preset, url);
  };

  const handleBundle = (bundleId?: string) => {
    const bundle = STYLE_BUNDLES.find((b) => b.id === bundleId) ?? STYLE_BUNDLES[0];
    const total = bundle.productIds.reduce((sum, id) => sum + (getProduct(id)?.priceNum ?? 0), 0);
    onOrderPlaced({
      orderNum: '#LM-48302',
      items: bundle.productIds.map((id) => getProduct(id)?.name ?? id),
      total: `$${Math.round(total * 0.88)}`,
    });
  };

  const browseProducts = useMemo(() => filterCatalog({ category, subcategory }), [category, subcategory]);
  const displayProducts = results ?? browseProducts;
  const mood = category ? CATEGORY_MOOD[category] : null;

  const scrollTo = (section: 'shop' | 'bundles') => {
    const el = section === 'bundles' ? bundlesRef.current : shopRef.current;
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const gridTitle = visionPreset
    ? 'Vision search results'
    : results
      ? 'AI search results'
      : category
        ? `${activeCategory?.label}${subcategory ? ` · ${activeCategory?.subcategories.find((s) => s.id === subcategory)?.label}` : ''}`
        : 'Shop the collection';

  return (
    <div className="lh-shop">
      <header className="lh-shop__nav">
        <div className="lh-shop__brand">
          <span className="lh-shop__wordmark">LUMEN</span>
          <span className="lh-shop__brand-tag">{STORE.tagline}</span>
        </div>
        <nav className="lh-shop__nav-links" aria-label="Store">
          <button
            type="button"
            onClick={() => {
              applyCatalogFilter(null, null);
              scrollTo('shop');
            }}
          >
            Shop
          </button>
          <button type="button" onClick={() => scrollTo('bundles')}>
            Bundles
          </button>
          <button type="button">Track order</button>
        </nav>
        <button type="button" className="lh-shop__cart" aria-label="Cart">
          Cart <span>0</span>
        </button>
      </header>

      <div className="lh-shop__cats" role="navigation" aria-label="Categories">
        <button
          type="button"
          className={`lh-shop__cat ${!category ? 'lh-shop__cat--on' : ''}`}
          onClick={() => applyCatalogFilter(null, null)}
        >
          All
        </button>
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            type="button"
            className={`lh-shop__cat ${category === c.id ? 'lh-shop__cat--on' : ''}`}
            onClick={() => applyCatalogFilter(c.id, null)}
          >
            {c.label}
          </button>
        ))}
      </div>

      {activeCategory && (
        <div className="lh-shop__subs" role="navigation" aria-label="Subcategories">
          <button
            type="button"
            className={`lh-shop__sub ${!subcategory ? 'lh-shop__sub--on' : ''}`}
            onClick={() => applyCatalogFilter(category, null)}
          >
            All {activeCategory.label}
          </button>
          {activeCategory.subcategories.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`lh-shop__sub ${subcategory === s.id ? 'lh-shop__sub--on' : ''}`}
              onClick={() => applyCatalogFilter(category, s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}

      <div className="lh-shop__scroll" ref={scrollRef}>
        <section className="lh-shop__hero" data-overlay-target="hero">
          <div className="lh-shop__hero-mesh" aria-hidden />
          <div className="lh-shop__hero-layout">
            <div className="lh-shop__hero-copy">
              <span className="lh-shop__hero-eyebrow">
                <IconSparkle className="lh-shop__sparkle" />
                Curated home
              </span>
              <OverlayPlainHero
                primary="Find the feeling."
                accent="Then the piece."
                accentTag="em"
              />
              <OverlayPlainSub>
                Natural-language search and vision matching — for rooms that already know what they want.
              </OverlayPlainSub>
              <OverlayAiChips
                className="lh-shop__ai-chips"
                aria-label="AI commerce capabilities"
                defaults={['Natural search', 'Vision match', 'Style bundles']}
              />
            </div>
            <div className="lh-shop__hero-duo" aria-hidden={!featuredProducts.length}>
              {featuredProducts.map((p, i) => (
                <figure key={p.id} className={i === 0 ? 'lh-shop__hero-duo-main' : 'lh-shop__hero-duo-side'}>
                  <img src={p.imageUrl} alt="" onError={(e) => onLumenImageError(e, p.name)} />
                  <figcaption>
                    <span>{p.name}</span>
                    <strong>{p.price}</strong>
                  </figcaption>
                </figure>
              ))}
            </div>
          </div>

          <form
            className={`lh-shop__search ${searching ? 'lh-shop__search--busy' : ''}`}
            onSubmit={(e) => {
              e.preventDefault();
              runSearch(query);
            }}
          >
            <IconSparkle className="lh-shop__search-icon" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Describe a room, material, or mood…"
              aria-label="AI product search"
            />
            <div className="lh-shop__vision-wrap">
              <button
                type="button"
                className="lh-shop__vision-btn"
                aria-label="Search by image"
                aria-expanded={showVisionMenu}
                onClick={() => setShowVisionMenu((v) => !v)}
              >
                <IconCamera className="lh-shop__vision-icon" />
              </button>
              {showVisionMenu && (
                <div className="lh-shop__vision-menu" role="menu">
                  <p className="lh-shop__vision-menu-title">Search by image</p>
                  <button type="button" className="lh-shop__vision-upload" onClick={() => fileRef.current?.click()}>
                    Upload a photo
                  </button>
                  <p className="lh-shop__vision-menu-label">Or try a room mood</p>
                  {IMAGE_SEARCH_PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      className="lh-shop__vision-preset"
                      role="menuitem"
                      onClick={() => runImageSearch(preset)}
                    >
                      <img src={preset.thumbnailUrl} alt="" onError={onLumenImageError} />
                      <span>
                        <strong>{preset.label}</strong>
                        <small>{preset.description}</small>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="lh-shop__file-input"
              aria-hidden
              tabIndex={-1}
              onChange={(e) => {
                handleFileUpload(e.target.files?.[0]);
                e.target.value = '';
              }}
            />
            <button type="submit" disabled={searching || !query.trim()}>
              {searching ? 'Searching…' : 'Search'}
            </button>
          </form>

          {(visionPreview || visionPreset) && (
            <div className="lh-shop__vision-chip">
              <img src={visionPreview ?? visionPreset?.thumbnailUrl} alt="" onError={onLumenImageError} />
              <div>
                <strong>{searching ? 'Matching materials…' : (visionPreset?.label ?? 'Your photo')}</strong>
                <span>{searching ? 'Vision AI scanning palette' : 'Vision matched materials & palette'}</span>
              </div>
              <button
                type="button"
                aria-label="Clear image search"
                onClick={() => {
                  clearVision();
                  setResults(null);
                  setAiNote('');
                }}
              >
                ×
              </button>
            </div>
          )}

          <div className="lh-shop__hints">
            <span className="lh-shop__hints-label">Try</span>
            {SEARCH_HINTS.map((h) => (
              <button key={h} type="button" onClick={() => runSearch(h)}>
                {h}
              </button>
            ))}
          </div>

          {aiNote && (
            <p className="lh-shop__ai-note" role="status">
              <IconSparkle className="lh-shop__sparkle" />
              {aiNote}
            </p>
          )}
        </section>

        <OverlayCustomSections />

        <section className="lh-shop__bundles" aria-label="AI picked for you" ref={bundlesRef}>
          <header className="lh-shop__bundles-head">
            <div>
              <span className="lh-shop__section-eyebrow">Style edits</span>
              <h2>AI picked for you</h2>
              <p>Bundles curated from room mood and search context</p>
            </div>
          </header>

          <article className="lh-shop__bundle-feature">
            <div className="lh-shop__bundle-feature-media">
              <img src={primaryBundle.imageUrl} alt="" loading="lazy" onError={onLumenImageError} />
              <span className="lh-shop__bundle-tag">{primaryBundle.savings}</span>
            </div>
            <div className="lh-shop__bundle-feature-body">
              <h3>{primaryBundle.title}</h3>
              <p>{primaryBundle.subtitle}</p>
              <ul>
                {primaryBundle.productIds.map((id) => {
                  const p = getProduct(id);
                  return p ? (
                    <li key={id}>
                      <img src={p.imageUrl} alt="" onError={(e) => onLumenImageError(e, p.name)} />
                      <span>
                        <strong>{p.name}</strong>
                        <small>{p.price}</small>
                      </span>
                    </li>
                  ) : null;
                })}
              </ul>
              <button type="button" onClick={() => handleBundle(primaryBundle.id)}>
                Add bundle to cart
              </button>
            </div>
          </article>

          {secondaryBundles.length > 0 && (
            <div className="lh-shop__bundle-row">
              {secondaryBundles.map((bundle) => (
                <article key={bundle.id} className="lh-shop__bundle-mini">
                  <img src={bundle.imageUrl} alt="" loading="lazy" onError={onLumenImageError} />
                  <div>
                    <span className="lh-shop__bundle-tag">{bundle.savings}</span>
                    <h3>{bundle.title}</h3>
                    <p>{bundle.subtitle}</p>
                    <button type="button" onClick={() => handleBundle(bundle.id)}>
                      Add edit
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="lh-shop__grid-section" ref={shopRef}>
          {mood && activeCategory && !results && !visionPreset && (
            <div className="lh-shop__mood">
              <img src={mood.image} alt="" onError={onLumenImageError} />
              <div>
                <span className="lh-shop__section-eyebrow">Collection</span>
                <h2>{activeCategory.label}</h2>
                <p>{mood.blurb}</p>
                <strong>
                  {displayProducts.length} piece{displayProducts.length === 1 ? '' : 's'}
                  {subcategory ? ` · ${activeCategory.subcategories.find((s) => s.id === subcategory)?.label}` : ''}
                </strong>
              </div>
            </div>
          )}

          <header className="lh-shop__grid-head">
            <h2>{mood && !results && !visionPreset ? 'In this edit' : gridTitle}</h2>
            <span>
              {displayProducts.length} items
              {category ? ` · ${PRODUCTS.filter((p) => p.category === category).length} in category` : ''}
            </span>
          </header>
          <div className="lh-shop__masonry">
            {displayProducts.map((p, i) => (
              <ProductTile key={p.id} product={p} featured={i % 5 === 0 || i % 5 === 3} />
            ))}
          </div>
        </section>

        <section className="lh-shop__trust">
          {TRUST.map((t) => (
            <article key={t.label}>
              <strong>{t.label}</strong>
              <span>{t.detail}</span>
            </article>
          ))}
        </section>

        <footer className="lh-shop__footer">
          <div className="lh-shop__footer-brand">
            <span className="lh-shop__wordmark lh-shop__wordmark--footer">LUMEN</span>
            <p>{STORE.name}</p>
          </div>
          <div className="lh-shop__footer-meta">
            <p>
              {STORE.address} · {STORE.city}
            </p>
            <p>{STORE.email}</p>
          </div>
        </footer>
      </div>

      <LumenShopChat
        open={chatOpen}
        onOpenChange={setChatOpen}
        onShopClick={() => {
          setChatOpen(false);
          runSearch('warm minimalist bedroom');
        }}
      />
    </div>
  );
}
