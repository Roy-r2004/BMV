import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/** Hash aliases that should land on the inquire / contact form. */
const HASH_ALIASES: Record<string, string> = {
  contact: 'inquire',
  'contact-form': 'inquire',
  purchase: 'inquire',
  'inquire-form': 'inquire',
  enquiry: 'inquire',
  enquiries: 'inquire',
};

/**
 * Every in-app navigation lands at the top of the destination — unless a hash
 * is present, in which case we scroll that section into view (with room for the
 * fixed/sticky public nav).
 *
 * **Template-only.** A generated app never imports this file: `assemble.py`
 * rewrites `src/App.tsx` from `app/templates/codegen/app_tsx.j2`, which carries
 * its own inline copy so the emitted App.tsx cannot depend on a file that has
 * to survive the workspace copy. Two copies drift, so
 * `test_the_scroll_reset_ships_one_behaviour_from_two_files` pins them to the
 * same alias set — change one, change both.
 */
export function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    const raw = (hash || '').replace(/^#/, '').trim();
    if (raw) {
      const id = HASH_ALIASES[raw] || raw;
      const scrollToHash = () => {
        const el = document.getElementById(id);
        if (!el) return false;
        // Measure the header now rather than trusting `--public-header-h`.
        // On a cold load of `/painting/1#inquire` this runs before PublicShell
        // has measured anything, so the CSS variable is still undefined and the
        // stylesheet fallback fires — request 67 landed such deep links 18px
        // *under* a 114px header, while the same anchor clicked in-page landed
        // correctly at +23. Reading the rendered header cannot race itself.
        const header = document.querySelector('[data-public-header]');
        const offset = (header ? header.getBoundingClientRect().height : 112) + 24;
        const top = el.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top: Math.max(0, top), left: 0, behavior: 'instant' });
        return true;
      };
      if (scrollToHash()) return;
      const t = window.setTimeout(() => {
        if (!scrollToHash()) window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      }, 50);
      return () => window.clearTimeout(t);
    }
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    return undefined;
  }, [pathname, hash]);
  return null;
}
