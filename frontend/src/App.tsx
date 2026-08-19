import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import ScrollManager from './components/ScrollManager';
import { AuthProvider } from './context/AuthContext';
// The landing stays eager — it is the first paint. Every other route is a
// separate chunk fetched on navigation, so the landing bundle stops
// carrying the studio, admin and solutions code.
import LandingPage from './routes/LandingPage';
import SiteChatWidget from './components/SiteChatWidget';
import './styles/mobile-shell.css';

const ExamplesPage = lazy(() => import('./routes/ExamplesPage'));
const SolutionsPage = lazy(() => import('./routes/SolutionsPage'));
const SolutionDetailPage = lazy(() => import('./routes/SolutionDetailPage'));
const AboutPage = lazy(() => import('./routes/AboutPage'));
const PrivateAIPage = lazy(() => import('./routes/PrivateAIPage'));
const SubmitPage = lazy(() => import('./routes/SubmitPage'));
const StudioPage = lazy(() => import('./routes/StudioPage'));
const EngagementsPage = lazy(() => import('./routes/EngagementsPage'));
const ResultPreviewPage = lazy(() => import('./routes/ResultPreviewPage'));
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
          <Route path="/" element={<LandingPage />} />
          <Route path="/examples" element={<ExamplesPage />} />

          <Route path="/solutions" element={<SolutionsPage />} />
          <Route path="/solutions/:id" element={<SolutionDetailPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/private-ai" element={<PrivateAIPage />} />
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
          {/* The signed-in client's home: the list of their runs, and each
              run at its unguessable slug address. Numeric /demo/<id> stays
              for the showcase and legacy links. */}
          <Route path="/engagements" element={<EngagementsPage />} />
          <Route path="/engagements/:id" element={<StudioPage />} />
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
        </Suspense>
        <SiteChatWidget />
      </BrowserRouter>
    </AuthProvider>
  );
}
