import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';

interface Props {
  to: string;
  children: React.ReactNode;
  variant?: 'primary' | 'ghost';
  className?: string;
}

export default function GlowButton({ to, children, variant = 'primary', className = '' }: Props) {
  if (variant === 'ghost') {
    return (
      <Link to={to}>
        <motion.span
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.98 }}
          className={`inline-block px-6 py-3 rounded-xl border border-white/20 text-white/90 font-medium hover:bg-white/10 hover:border-cyan-400/40 transition-colors ${className}`}
        >
          {children}
        </motion.span>
      </Link>
    );
  }

  return (
    <Link to={to} className="inline-flex">
      <motion.span
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.98 }}
        className={`gradient-btn inline-flex items-center justify-center cursor-pointer whitespace-nowrap ${className}`}
      >
        {children}
      </motion.span>
    </Link>
  );
}
