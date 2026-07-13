import {
  BookingPanel,
  BrandFooter,
  Button,
  CTABand,
  CredentialStrip,
  FeatureBento,
  LogoMarquee,
  MarketingHero,
  MotionPage,
  ProcessSection,
  ProductShowcase,
  PublicNav,
  PublicShell,
  ResultRail,
  SkeletonComposer,
  SpotlightCard,
  TestimonialRail,
  ToastHost,
  getSkeleton,
} from '@/ui';

const SKELETON_ID = 'public-home' as const;

const IMG = {
  hero: '/catalogue-hero.jpg',
  ritual: '/catalogue-ritual.jpg',
  laser: '/catalogue-laser.jpg',
  resultBefore1: '/catalogue-result-before-1.jpg',
  resultAfter1: '/catalogue-result-after-1.jpg',
  resultBefore2: '/catalogue-result-before-2.jpg',
  resultAfter2: '/catalogue-result-after-2.jpg',
  resultBefore3: '/catalogue-result-before-3.jpg',
  resultAfter3: '/catalogue-result-after-3.jpg',
};

/** Reference public site — daylight atelier + proof + booking. */
export default function PublicReferencePage() {
  const skeleton = getSkeleton(SKELETON_ID);

  const slots = {
    hero: (
      <MarketingHero
        variant="cinematic"
        brandName="Lumina"
        headline="Quiet skin rituals, arranged around your life."
        subcopy="Intake, chair time, and aftercare stay in one calm register — the same voice you hear at the front desk."
        imageSrc={IMG.hero}
        imageAlt="Bright calm treatment room with soft daylight"
        primaryCta={{ label: 'Book a consult', href: '#book' }}
        secondaryCta={{ label: 'See the ritual', href: '#features' }}
      />
    ),
    trust: (
        <LogoMarquee
          heading="In studio"
          items={[
            { label: 'Protocol-led care' },
            { label: 'Same-day aftercare' },
            { label: 'Membership cadence' },
            { label: 'Board-led protocols' },
            { label: 'Three studios' },
          ]}
        />
    ),
    credentials: (
      <CredentialStrip
        heading="Clinical trust"
        items={[
          {
            title: 'Medical director on protocol',
            detail: 'Every signature treatment is signed off by clinic medical leadership before it reaches the chair.',
          },
          {
            title: 'Measured downtime guidance',
            detail: 'Aftercare scripts stay clinical-calm — guests know what to expect in the first 48 hours.',
          },
          {
            title: 'Three daylight studios',
            detail: 'Same voice across locations. Chair inventory and membership cadence stay synchronized.',
          },
        ]}
      />
    ),
    features: (
      <div id="features">
        <FeatureBento
          variant="alternating"
          heading="How guests actually arrive."
          description="Curiosity, chair, aftercare — each surface keeps Lumina’s clinical-calm voice."
          items={[
            {
              title: 'Concierge booking',
              description: 'Guided intake captures goals and timing — without burying the hero in chat widgets.',
            },
            {
              title: 'Treatment clarity',
              description: 'One idea per surface. Guests know exactly what they are choosing.',
            },
            {
              title: 'Aftercare that continues',
              description: 'Reminders stay clinical-calm, never promotional — same voice as the desk.',
            },
            {
              title: 'Membership pacing',
              description: 'Cadence that protects chairs and guest energy alike.',
            },
          ]}
        />
      </div>
    ),
    spotlight: (
      <section className="px-6 pb-4 lg:px-12">
        <div className="mx-auto max-w-[92rem] border-y border-foreground/10 py-14">
          <SpotlightCard
            icon="shield"
            title="Brand voice that never slips"
            description="Every reminder, booking confirmation, and aftercare note stays in Lumina’s clinical-calm register — no generic SaaS tone."
            className="border-0 bg-transparent p-0 shadow-none"
          />
        </div>
      </section>
    ),
    showcase: (
      <div id="experiences">
        <ProductShowcase
          heading="Signature experiences"
          description="A lead ritual with supporting treatments — hierarchy guests can feel."
          items={[
            {
              title: 'HydraGlow Ritual',
              description: 'Deep cleanse, infusion, and LED calm in one orchestrated visit.',
              imageSrc: IMG.ritual,
              imageAlt: 'Calm spa interior',
            },
            {
              title: 'Precision Laser',
              description: 'Targeted clarity with measured downtime guidance.',
              imageSrc: IMG.laser,
              imageAlt: 'Soft towels and treatment atmosphere',
            },
            {
              title: 'Membership Reset',
              description: 'Monthly skin rhythm with concierge scheduling.',
              imageSrc: IMG.laser,
              imageAlt: 'Membership cadence',
            },
          ]}
        />
      </div>
    ),
    results: (
      <ResultRail
        heading="Outcomes guests can see."
        description="Representative protocol results from Lumina’s daylight studios — proof before the book step."
        items={[
          {
            label: 'HydraGlow Ritual',
            beforeSrc: IMG.resultBefore1,
            afterSrc: IMG.resultAfter1,
            note: 'Four visits · membership cadence',
          },
          {
            label: 'Clarity Laser',
            beforeSrc: IMG.resultBefore2,
            afterSrc: IMG.resultAfter2,
            note: 'Measured downtime · week two',
          },
          {
            label: 'Barrier Reset',
            beforeSrc: IMG.resultBefore3,
            afterSrc: IMG.resultAfter3,
            note: 'Consult-led protocol · calm finish',
          },
        ]}
      />
    ),
    process: (
      <div id="visit">
        <ProcessSection
          heading="From curiosity to booked"
          description="Three calm steps. Order matters."
          steps={[
            { title: 'Share goals', description: 'A short intake that captures skin goals and timing.' },
            { title: 'Match treatment', description: 'A clear path with transparent pricing and chair availability.' },
            { title: 'Confirm visit', description: 'Reminders and aftercare arrive in the same brand voice.' },
          ]}
        />
      </div>
    ),
    testimonials: (
      <TestimonialRail
        heading="What returning guests notice"
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
    booking: (
      <BookingPanel
        heading="Hold a consult in under a minute."
        description="Choose a treatment, pick a daylight slot, confirm. The same voice you’ll hear at the desk."
        treatments={[
          { id: 'hydraglow', name: 'HydraGlow Ritual', duration: '75 min' },
          { id: 'laser', name: 'Precision Laser consult', duration: '30 min' },
          { id: 'membership', name: 'Membership Reset', duration: '45 min' },
        ]}
        slots={[
          { id: 's1', startsAt: '2026-07-14T10:00:00' },
          { id: 's2', startsAt: '2026-07-14T14:30:00' },
          { id: 's3', startsAt: '2026-07-15T11:00:00' },
          { id: 's4', startsAt: '2026-07-16T09:30:00' },
        ]}
      />
    ),
    cta: (
      <CTABand
        heading="Prefer to talk first?"
        description="Ask the desk anything — we’ll keep the same calm register."
        primaryCta={{ label: 'Back to booking', href: '#book' }}
        secondaryCta={{ label: 'Browse treatments', href: '#features' }}
      />
    ),
    footer: (
      <BrandFooter
        brandName="Lumina"
        description="Clinical aesthetics with an AI concierge that books, follows up, and protects brand tone."
        links={[
          { label: 'Treatments', href: '#features' },
          { label: 'Experiences', href: '#experiences' },
          { label: 'Book', href: '#book' },
        ]}
        meta={skeleton.id}
      />
    ),
  };

  return (
    <MotionPage>
      <ToastHost />
      <PublicShell
        chrome="immersive"
        brandName="Lumina"
        nav={
          <PublicNav
            items={[
              { label: 'Treatments', href: '#features' },
              { label: 'Experiences', href: '#experiences' },
              { label: 'Visit', href: '#visit' },
              { label: 'Book', href: '#book' },
            ]}
            cta={{ label: 'Book consult', href: '#book' }}
          />
        }
        mobileDock={
          <Button href="#book" className="w-full" size="lg">
            Book consult
          </Button>
        }
      >
        <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />
      </PublicShell>
    </MotionPage>
  );
}
