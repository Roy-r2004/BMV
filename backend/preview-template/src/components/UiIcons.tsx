import type { LucideIcon } from 'lucide-react';
import {
  ArrowRight,
  BarChart3,
  Bell,
  Calendar,
  Check,
  Circle,
  ClipboardList,
  Clock3,
  Home,
  LayoutDashboard,
  Mail,
  Menu,
  Phone,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Star,
  Target,
  User,
  Users,
  X,
  Zap,
} from 'lucide-react';

import { cn } from '../lib/cn.js';

const icons: Record<string, LucideIcon> = {
  'arrow-right': ArrowRight,
  bell: Bell,
  chart: BarChart3,
  check: Check,
  checkmark: Check,
  clipboard: ClipboardList,
  close: X,
  clock: Clock3,
  dashboard: LayoutDashboard,
  default: Circle,
  home: Home,
  mail: Mail,
  menu: Menu,
  phone: Phone,
  plus: Plus,
  search: Search,
  settings: Settings,
  shield: ShieldCheck,
  star: Star,
  target: Target,
  user: User,
  users: Users,
  x: X,
  zap: Zap,
  calendar: Calendar,
};

function normalizeIconName(name: string) {
  return name.trim().toLowerCase().replace(/[_\s]+/g, '-');
}

export function UiIcon({
  name,
  className = 'h-5 w-5',
  strokeWidth = 1.75,
}: {
  name: string;
  className?: string;
  strokeWidth?: number;
}) {
  const key = normalizeIconName(name || 'default');
  const Icon = icons[key] ?? icons.default;

  return <Icon aria-hidden="true" className={cn('shrink-0', className)} strokeWidth={strokeWidth} />;
}

export default UiIcon;
