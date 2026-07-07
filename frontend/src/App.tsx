import { BrowserRouter, Routes, Route } from 'react-router-dom';
import ScrollManager from './components/ScrollManager';
import LandingPage from './routes/LandingPage';
import ExamplesPage from './routes/ExamplesPage';
import DemoPage from './routes/DemoPage';
import SolutionsPage from './routes/SolutionsPage';
import SolutionDetailPage from './routes/SolutionDetailPage';
import AboutPage from './routes/AboutPage';
import SubmitPage from './routes/SubmitPage';
import ResultPreviewPage from './routes/ResultPreviewPage';
import AdminLoginPage from './routes/AdminLoginPage';
import AdminDashboardPage from './routes/AdminDashboardPage';
import AdminRequestDetailPage from './routes/AdminRequestDetailPage';
import AdminLayout from './components/AdminLayout';

export default function App() {
  return (
    <BrowserRouter>
      <ScrollManager />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/examples" element={<ExamplesPage />} />
        <Route path="/demo" element={<DemoPage />} />
        <Route path="/solutions" element={<SolutionsPage />} />
        <Route path="/solutions/:id" element={<SolutionDetailPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/submit" element={<SubmitPage />} />
        <Route path="/result/:id" element={<ResultPreviewPage />} />
        <Route path="/admin/login" element={<AdminLoginPage />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminDashboardPage />} />
          <Route path="requests/:id" element={<AdminRequestDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
