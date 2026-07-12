import { Outlet } from 'react-router-dom';

/**
 * Public pages compose chrome via PublicShell.
 * Keep this layout as a thin outlet so we don't double-wrap marketing shells.
 */
export default function PublicLayout() {
  return <Outlet />;
}
