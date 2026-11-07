import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Routes, Route } from 'react-router-dom';
import ScrollManager from './components/ScrollManager';
import { AuthProvider } from './context/AuthContext';
// The landing stays eager — it is the first paint. Every other route is a
// separate chunk fetched on navigation, so the landing bundle stops
// carrying the studio, admin and solutions code.
import LandingPage from './routes/LandingPage';
import FilmShell from './film/FilmShell';
import SiteChatWidget from './components/SiteChatWidget';
import './styles/mobile-shell.css';

const SolutionsPage = lazy(() => import('./routes/SolutionsPage'));
const AboutPage = lazy(() => import('./routes/AboutPage'));
const PrivateAIPage = lazy(() => import('./routes/PrivateAIPage'));
const ServicesPage = lazy(() => import('./routes/ServicesPage'));
const ApproachPage = lazy(() => import('./routes/ApproachPage'));
const ContactPage = lazy(() => import('./routes/ContactPage'));
const PrivacyPage = lazy(() => import('./routes/PrivacyPage'));
const TermsPage = lazy(() => import('./routes/TermsPage'));
const StudioPage = lazy(() => import('./routes/StudioPage'));
const EngagementsPage = lazy(() => import('./routes/EngagementsPage'));
const ResultPreviewPage = lazy(() => import('./routes/ResultPreviewPage'));
const SharedPage = lazy(() => import('./routes/SharedPage'));
const LoginPage = lazy(() => import('./routes/LoginPage'));
const SignupPage = lazy(() => import('./routes/SignupPage'));
const AdminLoginPage = lazy(() => import('./routes/AdminLoginPage'));
const AdminOpsPage = lazy(() => import('./routes/AdminOpsPage'));
const AdminDashboardPage = lazy(() => import('./routes/AdminDashboardPage'));
const AdminUsagePage = lazy(() => import('./routes/AdminUsagePage'));
const AdminRequestDetailPage = lazy(() => import('./routes/AdminRequestDetailPage'));
const AdminLayout = lazy(() => import('./components/AdminLayout'));

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ScrollManager />
        <Suspense fallback={null}>
        <Routes>
          {/* The public pages play inside one film shell: the light field behind
              them survives navigation, and moving between them is a cut. The
              list of paths lives in film/scenes.ts. */}
          <Route element={<FilmShell />}>
            <Route path="/" element={<LandingPage />} />
            {/* /solutions is the examples page. It replaced the old
                per-industry catalogue, so links to either still land here. */}
            <Route path="/solutions" element={<SolutionsPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/services" element={<ServicesPage />} />
            <Route path="/approach" element={<ApproachPage />} />
            <Route path="/contact" element={<ContactPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/private-ai" element={<PrivateAIPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
          </Route>
          <Route path="/solutions/:id" element={<Navigate to="/solutions" replace />} />
          <Route path="/examples" element={<Navigate to="/solutions" replace />} />
          <Route path="/submit" element={<Navigate to="/demo" replace />} />
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
          {/* The signed-in client's home: the list of their runs, and each
              run at its unguessable slug address. Numeric /demo/<id> stays
              for the showcase and legacy links. */}
          <Route path="/engagements" element={<EngagementsPage />} />
          <Route path="/engagements/:id" element={<StudioPage />} />
          <Route path="/result/:id" element={<ResultPreviewPage />} />
          <Route path="/share/:id" element={<ResultPreviewPage />} />
          {/* A consultation package an owner shared with a partner: read-only,
              through a revocable token. Not /share, which is the older preview-app
              page and keeps its own links working. */}
          <Route path="/shared/:token" element={<SharedPage />} />
          <Route path="/admin/login" element={<AdminLoginPage />} />
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminOpsPage />} />
            <Route path="requests" element={<AdminDashboardPage />} />
            <Route path="requests/:id" element={<AdminRequestDetailPage />} />
            <Route path="usage" element={<AdminUsagePage />} />
          </Route>
        </Routes>
        </Suspense>
        <SiteChatWidget />
      </BrowserRouter>
    </AuthProvider>
  );
}
