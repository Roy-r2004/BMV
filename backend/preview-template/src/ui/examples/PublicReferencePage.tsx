import { useMemo } from 'react';

import {
  Badge,
  BrandFooter,
  Button,
  CTABand,
  FeatureBento,
  MarketingHero,
  ProcessSection,
  ProductShowcase,
  PublicShell,
  SkeletonComposer,
  TestimonialRail,
  getSkeleton,
} from '@/ui';

const SKELETON_ID = 'public-home' as const;

/** Reference public site — structure driven by skeleton registry. */
export default function PublicReferencePage() {
  const skeleton = getSkeleton(SKELETON_ID);

  const slots = useMemo(
    () => ({
      hero: (
        <MarketingHero
          variant="cinematic"
          brandName="Lumina"
          headline="Skin confidence, orchestrated."
          subcopy="A calm clinical brand surface — one hero, one promise, clear next steps. Built only from @/ui."
          imageSrc="/catalogue-hero.svg"
          imageAlt="Atmospheric clinical treatment space"
          primaryCta={{ label: 'Book consult', href: '#book' }}
          secondaryCta={{ label: 'Explore treatments', href: '#features' }}
        />
      ),
      trust: (
        <section className="border-y border-white/10 px-6 py-8 lg:px-10" aria-label="Trust">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3">
            <Badge>Board-led protocols</Badge>
            <Badge variant="secondary">AI concierge</Badge>
            <Badge variant="outline">Same-day follow-up</Badge>
            <p className="text-sm text-background/55">Trusted by returning members across three studio locations.</p>
          </div>
        </section>
      ),
      features: (
        <div id="features">
          <FeatureBento
            variant="bento"
            heading="What guests feel first"
            description="Varied hierarchy — not ten equal cards. Skeleton order from public-home."
            items={[
              {
                title: 'Concierge booking',
                description: 'Guided intake that mirrors your front desk without cluttering the hero.',
              },
              {
                title: 'Treatment clarity',
                description: 'Scannable service stories with one idea per tile.',
              },
              {
                title: 'Aftercare continuity',
                description: 'Follow-ups stay clinical-calm, never promotional noise.',
              },
              {
                title: 'Membership pacing',
                description: 'Cadence that protects utilization without feeling pushy.',
              },
            ]}
          />
        </div>
      ),
      showcase: (
        <ProductShowcase
          heading="Signature experiences"
          description="Dominant feature media, then supporting products — intentional hierarchy."
          items={[
            {
              title: 'HydraGlow Ritual',
              description: 'Deep cleanse, infusion, and LED calm in one orchestrated visit.',
              imageSrc: '/catalogue-product.svg',
              imageAlt: 'HydraGlow treatment preview',
            },
            {
              title: 'Precision Laser',
              description: 'Targeted clarity with measured downtime guidance.',
              imageSrc: '/catalogue-product.svg',
            },
            {
              title: 'Membership Reset',
              description: 'Monthly skin rhythm with concierge scheduling.',
              imageSrc: '/catalogue-product.svg',
            },
          ]}
        />
      ),
      process: (
        <ProcessSection
          heading="From curiosity to booked"
          description="Three calm steps — no marketing hero inside the flow."
          steps={[
            { title: 'Share goals', description: 'A short intake that captures skin goals and timing.' },
            { title: 'Match treatment', description: 'Concierge recommends a clear path with transparent pricing.' },
            { title: 'Confirm visit', description: 'Reminders and aftercare arrive in the same brand voice.' },
          ]}
        />
      ),
      testimonials: (
        <TestimonialRail
          heading="Trusted by returning clients"
          items={[
            {
              quote: 'The booking flow felt like the clinic itself — quiet, clear, and personal.',
              author: 'Maya R.',
              role: 'Hydrafacial guest',
            },
            {
              quote: 'Reminders arrived in the same brand voice. I never wondered what to do next.',
              author: 'Jordan K.',
              role: 'Membership client',
            },
            {
              quote: 'Premium without trying too hard. Exactly how Lumina feels in person.',
              author: 'Elena V.',
              role: 'First-time consult',
            },
          ]}
        />
      ),
      cta: (
        <div id="book">
          <CTABand
            heading="Ready for quieter confidence?"
            description="Book a consult — structure from skeleton, content from the brand."
            primaryCta={{ label: 'Book consult', href: '#book' }}
            secondaryCta={{ label: 'View services', href: '#features' }}
          />
        </div>
      ),
      footer: (
        <BrandFooter
          brandName="Lumina"
          description="Calm clinical aesthetics with an AI concierge that books, follows up, and protects brand tone."
          links={[
            { label: 'Treatments', href: '#features' },
            { label: 'Book', href: '#book' },
            { label: 'Stories', href: '#features' },
          ]}
          meta={`Skeleton ${skeleton.id} · ${skeleton.purpose}`}
        />
      ),
    }),
    [skeleton.id, skeleton.purpose]
  );

  return (
    <PublicShell
      brandName="Lumina"
      nav={
        <div className="flex items-center gap-4 text-sm text-background/70">
          <a href="#features" className="hover:text-background">
            Features
          </a>
          <a href="#book" className="hover:text-background">
            Book
          </a>
          <Button href="#book" size="sm">
            Book consult
          </Button>
        </div>
      }
    >
      <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />
    </PublicShell>
  );
}
