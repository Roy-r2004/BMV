/**
 * Facts about the company, said the same way on every page. Only facts the
 * firm has confirmed belong here: no invented clients, names, offices or
 * results. Ask before adding one.
 */
import { CONSULTING_EMAIL } from '../api/client';

export const COMPANY = {
  name: 'Build My Version',
  short: 'BMV',
  registered: 'Registered in Dubai, United Arab Emirates',
  email: CONSULTING_EMAIL,
} as const;

/** The public sections of the site, in the order the navigation shows them. */
export const SECTIONS = [
  { to: '/services', label: 'Services', hint: 'What we offer and what it costs' },
  { to: '/approach', label: 'Approach', hint: 'How a consultation is run' },
  { to: '/solutions', label: 'Examples', hint: 'Systems we design, screen by screen' },
  { to: '/private-ai', label: 'Private AI', hint: 'AI inside your own infrastructure' },
  { to: '/about', label: 'About', hint: 'The firm and the people behind the method' },
  { to: '/contact', label: 'Contact', hint: 'Write to us' },
] as const;
