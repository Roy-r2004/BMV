import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import AdminLayout from './layouts/AdminLayout';
import HomePage from './pages/HomePage';
import ServicesPage from './pages/ServicesPage';
import TeamPage from './pages/TeamPage';
import BookingPage from './pages/BookingPage';
import GalleryPage from './pages/GalleryPage';
import ContactPage from './pages/ContactPage';
import OwnerDashboardPage from './pages/OwnerDashboardPage';
import BookingsAdminPage from './pages/admin/BookingsPage';
import ClientsPage from './pages/admin/ClientsPage';
import AiFrontDeskPage from './pages/admin/AiFrontDeskPage';
import SettingsPage from './pages/admin/SettingsPage';
import ReportsPage from './pages/admin/ReportsPage';
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
        {/* Design-draft review: these pages carry their own chrome, so they
            render outside PublicLayout while the speechless-face draft is
            iterated across the full salon site (Home/Services/Team/Booking). */}
        <Route path="/" element={<HomePage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/booking" element={<BookingPage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/contact" element={<ContactPage />} />
        <Route path="/owner" element={<OwnerDashboardPage />} />
        <Route path="/owner/bookings" element={<BookingsAdminPage />} />
        <Route path="/owner/clients" element={<ClientsPage />} />
        <Route path="/owner/ai" element={<AiFrontDeskPage />} />
        <Route path="/owner/settings" element={<SettingsPage />} />
        <Route path="/owner/reports" element={<ReportsPage />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminDashboardPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
