/**
 * The public pages as scenes, in the order the site is read. The number and
 * title appear in the slate and on the cut between pages. Only these paths
 * live inside the film shell; the consultation, engagements, results and
 * admin keep their own layouts.
 */
export const SCENES = [
  { path: '/', title: 'Home' },
  { path: '/services', title: 'Services' },
  { path: '/approach', title: 'Approach' },
  { path: '/solutions', title: 'Examples' },
  { path: '/private-ai', title: 'Private AI' },
  { path: '/about', title: 'About' },
  { path: '/contact', title: 'Contact' },
  { path: '/login', title: 'Sign in' },
  { path: '/signup', title: 'Create an account' },
  { path: '/privacy', title: 'Privacy notice' },
  { path: '/terms', title: 'Terms of engagement' },
] as const;

export function sceneFor(pathname: string) {
  const i = SCENES.findIndex((s) => s.path === pathname);
  return i < 0 ? null : { number: i + 1, title: SCENES[i].title };
}

export function isFilmPath(pathname: string): boolean {
  return SCENES.some((s) => s.path === pathname);
}

export const pad2 = (n: number) => String(n).padStart(2, '0');
