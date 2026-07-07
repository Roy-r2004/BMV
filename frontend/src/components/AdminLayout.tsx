import { Link, Outlet, useNavigate } from 'react-router-dom';
import Logo from './Logo';

export default function AdminLayout() {
  const navigate = useNavigate();

  const logout = () => {
    sessionStorage.removeItem('admin_password');
    navigate('/admin/login');
  };

  return (
    <div className="min-h-screen bg-off-white">
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Logo to="/admin" size="sm" />
            <Link to="/admin" className="font-bold text-lg hidden sm:inline">Admin</Link>
            <Link to="/admin" className="text-sm text-slate-600 hover:text-accent">Requests</Link>
          </div>
          <button onClick={logout} className="text-sm text-slate-500 hover:text-red-500">Logout</button>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
