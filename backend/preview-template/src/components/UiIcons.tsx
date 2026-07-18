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

function iconKey(name: unknown): string {
  if (typeof name === 'string' && name.trim()) return name.trim().toLowerCase();
  return 'default';
}

export function UiIcon({ name, className = 'w-5 h-5' }: { name?: unknown; className?: string }) {
  // Generators sometimes pass a React node; never crash the preview on that.
  const Icon = icons[iconKey(name)] ?? icons.default;
  return <Icon aria-hidden="true" className={className} strokeWidth={1.75} />;
}

export default UiIcon;
