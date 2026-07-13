import type { LucideIcon } from 'lucide-react';
import {
  Bell,
  Calendar,
  ChartNoAxesCombined,
  Check,
  Circle,
  ClipboardList,
  Clock,
  Search,
  Shield,
  Target,
  Users,
  Zap,
} from 'lucide-react';

const icons: Record<string, LucideIcon> = {
  clipboard: ClipboardList,
  chart: ChartNoAxesCombined,
  target: Target,
  clock: Clock,
  users: Users,
  zap: Zap,
  shield: Shield,
  bell: Bell,
  calendar: Calendar,
  check: Check,
  search: Search,
  default: Circle,
};

export function UiIcon({ name, className = 'w-5 h-5' }: { name: string; className?: string }) {
  const key = (name || 'default').toLowerCase();
  const Icon = icons[key] ?? icons.default;
  return <Icon aria-hidden="true" className={className} strokeWidth={1.75} />;
}

export default UiIcon;
