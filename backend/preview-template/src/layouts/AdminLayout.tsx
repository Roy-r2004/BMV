import { Outlet } from 'react-router-dom';

/**
 * Ops pages compose their own chrome via OpsShell.
 * Keep this layout as a thin outlet so we don't double-wrap sidebars.
 */
export default function AdminLayout() {
  return <Outlet />;
}
