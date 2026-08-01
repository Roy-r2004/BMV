import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import PublicLayout from './layouts/PublicLayout';
import AdminLayout from './layouts/AdminLayout';
import HomePage from './pages/HomePage';
import AdminDashboardPage from './pages/admin/AdminDashboardPage';
import { ScrollToTop } from './components/ScrollToTop';
import { notifyParent, registerPreviewNavigate, setupPreviewBridge } from './lib/preview-bridge';
import { roles } from './data/mock';

function RouteBridge() {
  const location = useLocation();
  useEffect(() => {
    notifyParent(location.pathname);
  }, [location.pathname]);
  return null;
}

function RoleBridge() {
  const navigate = useNavigate();
  useEffect(() => {
    registerPreviewNavigate((path) => navigate(path));
    setupPreviewBridge((roleId, path) => {
      if (path) {
        navigate(path);
        return;
      }
      const role = roles.find((r) => r.id === roleId)
        ?? roles.find((r) => roleId === 'owner' && (r.id.includes('admin') || r.label.toLowerCase().includes('admin')))
        ?? roles.find((r) => roleId === 'admin' && (r.id.includes('owner') || r.label.toLowerCase().includes('owner')));
      navigate(role?.defaultPath ?? roles[0]?.defaultPath ?? '/');
    });
  }, [navigate]);
  return null;
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <ScrollToTop />
      <RouteBridge />
      <RoleBridge />
      <Routes>
        <Route element={<PublicLayout />}>
          <Route path="/" element={<HomePage />} />
        </Route>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminDashboardPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
