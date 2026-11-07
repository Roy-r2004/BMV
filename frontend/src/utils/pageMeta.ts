/**
 * Each page names itself in the browser tab and in a shared link's preview.
 * index.html carries the home page's values, so a crawler that never runs
 * this script still reads something true.
 */
import { useEffect } from 'react';

const SITE = 'Build My Version';

function setMeta(attr: 'name' | 'property', key: string, value: string) {
  let tag = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute(attr, key);
    document.head.appendChild(tag);
  }
  tag.content = value;
}

export function usePageMeta(title: string, description?: string) {
  useEffect(() => {
    const full = title ? `${title} · ${SITE}` : SITE;
    document.title = full;
    setMeta('property', 'og:title', full);
    if (description) {
      setMeta('name', 'description', description);
      setMeta('property', 'og:description', description);
    }
  }, [title, description]);
}
