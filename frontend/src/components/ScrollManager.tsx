import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { isFilmPath } from '../film/scenes';
import { scrollToHashWhenReady, scrollToTop } from '../utils/scroll';

export default function ScrollManager() {
  const { pathname, hash } = useLocation();

  useEffect(() => {
    // the film shell scrolls its own pages, after the cut has closed over the old one
    if (isFilmPath(pathname)) return undefined;
    if (hash) {
      return scrollToHashWhenReady(hash);
    }
    scrollToTop('auto');
    return undefined;
  }, [pathname, hash]);

  return null;
}
