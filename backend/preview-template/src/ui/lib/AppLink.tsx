import * as React from 'react';
import { Link } from 'react-router-dom';

/**
 * True for in-app paths that must stay under Vite/React Router basename
 * (e.g. /api/preview-apps/5/). Raw <a href="/owner/..."> escapes that mount
 * and hits the API host with {"detail":"Not Found"}.
 */
export function isInAppPath(href: string): boolean {
  if (!href) return false;
  if (href.startsWith('#')) return false;
  if (href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('sms:')) return false;
  if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return false;
  if (href.startsWith('//')) return false;
  return href.startsWith('/');
}

type AppLinkProps = Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & {
  href: string;
  /**
   * Optional: catalogue components use AppLink as a full-area overlay click
   * target (`absolute inset-0` + aria-label, no children), which is a valid
   * accessible pattern. Requiring children made that a type error in the
   * shipped template, and every generated app inherited it.
   */
  children?: React.ReactNode;
};

/** Router-aware link for catalogue surfaces. External/hash hrefs stay as <a>. */
export function AppLink({ href, children, ...rest }: AppLinkProps) {
  if (isInAppPath(href)) {
    return (
      <Link to={href} {...rest}>
        {children}
      </Link>
    );
  }
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  );
}
