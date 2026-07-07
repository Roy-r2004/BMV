import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { scrollToHashWhenReady, scrollToTop } from '../utils/scroll';

export default function ScrollManager() {
  const { pathname, hash } = useLocation();

  useEffect(() => {
    if (hash) {
      return scrollToHashWhenReady(hash);
    }
    scrollToTop('auto');
    return undefined;
  }, [pathname, hash]);

  return null;
}
