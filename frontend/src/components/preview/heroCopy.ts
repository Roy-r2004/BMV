import type { VisualDemo } from '../../types/request';

/** Turn generic AI headlines into something that sells the dream. */
export function getHeroCopy(demo: VisualDemo, businessName?: string, industry?: string | null) {
  const raw = demo.hero.headline?.trim() ?? '';
  const generic = /welcome to your custom|your custom .+ solution/i.test(raw);

  let headline = generic ? '' : raw;
  if (!headline) {
    const i = (industry || '').toLowerCase();
    if (/fitness|nutrition|diet|coach|meal|workout/.test(i)) {
      headline = 'Your plan. Your progress. One place.';
    } else if (/health|wellness|clinic|aesthetic|spa/.test(i)) {
      headline = 'Turn inquiries into booked appointments';
    } else {
      headline = 'Run your business without the busywork';
    }
  }

  const sub = demo.hero.subheadline?.trim()
    || (businessName
      ? `${demo.product_name} is built for ${businessName} — tailored to how you actually work with clients.`
      : `${demo.product_name} turns inquiries into results while you focus on delivery.`);

  return { headline, subheadline: sub };
}
