import { BrowserRouter, Routes, Route } from 'react-router-dom';
import ScrollManager from './components/ScrollManager';
import { AuthProvider } from './context/AuthContext';
import LandingPage from './routes/LandingPage';
import ExamplesPage from './routes/ExamplesPage';
import SolutionsPage from './routes/SolutionsPage';
import SolutionDetailPage from './routes/SolutionDetailPage';
import AboutPage from './routes/AboutPage';
import SubmitPage from './routes/SubmitPage';
import StudioPage from './routes/StudioPage';
import ResultPreviewPage from './routes/ResultPreviewPage';
import LoginPage from './routes/LoginPage';
import SignupPage from './routes/SignupPage';
import AdminLoginPage from './routes/AdminLoginPage';
import AdminOpsPage from './routes/AdminOpsPage';
import AdminDashboardPage from './routes/AdminDashboardPage';
import AdminUsagePage from './routes/AdminUsagePage';
import AdminRequestDetailPage from './routes/AdminRequestDetailPage';
import AdminLayout from './components/AdminLayout';
import SiteChatWidget from './components/SiteChatWidget';
import './styles/mobile-shell.css';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ScrollManager />
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/examples" element={<ExamplesPage />} />

          <Route path="/solutions" element={<SolutionsPage />} />
          <Route path="/solutions/:id" element={<SolutionDetailPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/submit" element={<SubmitPage />} />
          {/* The client-facing generator, addressed as /demo. It used to be
              /studio, beside a separate /demo page that listed generated
              preview apps — two entries offering the client two different
              things to generate. The image demo is the one we sell, so it
              took the name. */}
          <Route path="/demo" element={<StudioPage />} />
          {/* The permanent address of one run. A generation costs real money;
              the result it produces has to survive a refresh, a bookmark and
              a forwarded link, not just the tab that started it. Both spellings
              resolve: every /studio/<id> link already handed out, written into
              an evidence document or bookmarked has to keep working. */}
          <Route path="/demo/:id" element={<StudioPage />} />
          <Route path="/studio" element={<StudioPage />} />
          <Route path="/studio/:id" element={<StudioPage />} />
          <Route path="/result/:id" element={<ResultPreviewPage />} />
          <Route path="/share/:id" element={<ResultPreviewPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/admin/login" element={<AdminLoginPage />} />
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminOpsPage />} />
            <Route path="requests" element={<AdminDashboardPage />} />
            <Route path="requests/:id" element={<AdminRequestDetailPage />} />
            <Route path="usage" element={<AdminUsagePage />} />
          </Route>
        </Routes>
        <SiteChatWidget />
      </BrowserRouter>
    </AuthProvider>
  );
}
