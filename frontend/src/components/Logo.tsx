import { Link, useLocation } from 'react-router-dom';
import { scrollToTop } from '../utils/scroll';

interface Props {
  to?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  showTagline?: boolean;
  showName?: boolean;
  theme?: 'light' | 'dark';
}

const sizes = {
  sm: 'h-9 w-9',
  md: 'h-10 w-10',
  lg: 'h-16 w-16',
  xl: 'h-[4.5rem] w-[4.5rem] sm:h-20 sm:w-20',
};

/** BMV AI logo — circular mark with cyan ring identity preserved */
export default function Logo({ to = '/', size = 'md', showTagline = false, showName = false, theme = 'light' }: Props) {
  const location = useLocation();
  const nameClass = theme === 'dark' ? 'text-white' : 'text-navy';
  const subClass = theme === 'dark' ? 'text-slate-400' : 'text-slate-500';
  const taglineClass = theme === 'dark' ? 'text-slate-400' : 'text-slate-500';

  const mark = (
    <div className="flex items-center gap-2.5">
      <div className={`logo-mark shrink-0 ${sizes[size]}`}>
        <img
          src="/logo.png"
          alt="Build My Version"
          className="h-full w-full object-contain"
        />
      </div>
      {showName && (
        <div className="leading-tight">
          <span className={`block font-bold text-sm sm:text-base tracking-tight ${nameClass}`}>Build My Version</span>
          <span className={`block text-[10px] sm:text-xs font-medium ${subClass}`}>BMV AI</span>
        </div>
      )}
      {showTagline && !showName && (
        <span className={`hidden sm:block text-xs leading-tight max-w-[140px] ${taglineClass}`}>
          Build My Version
        </span>
      )}
    </div>
  );

  const targetPath = to.split('#')[0] || '/';

  const handleClick = () => {
    if (location.pathname === targetPath) {
      scrollToTop('smooth');
    }
  };

  return to ? (
    <Link to={to} onClick={handleClick} className="hover:opacity-95 transition-opacity">
      {mark}
    </Link>
  ) : mark;
}
