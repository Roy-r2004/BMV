import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { adminLogin, persistAdminSession } from '../api/admin';
import { setUserToken } from '../api/auth';
import AuthShell from '../components/AuthShell';

export default function AdminLoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const result = await adminLogin(password, email);
      if (!result.success) {
        setError(result.message || 'Invalid credentials');
        return;
      }
      persistAdminSession(result, email.trim() ? undefined : password);
      if (result.token) setUserToken(result.token);
      navigate('/admin');
    } catch {
      setError('Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Operations"
      title="Admin sign in"
      lead="Use your admin email and password to open the ops dashboard, costs, and request controls."
      visualTitle="Ops control"
      visualCopy="Pause AI, watch spend, manage requests, and keep the pipeline under your control."
      footer={
        <>
          Need a public account?{' '}
          <Link to="/login">User sign in</Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="auth-shell__form">
        <label className="auth-shell__label">
          Email
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="auth-shell__input"
            placeholder="you@company.com"
            required
          />
        </label>
        <label className="auth-shell__label">
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="auth-shell__input"
            required
          />
        </label>
        {error ? <p className="auth-shell__error">{error}</p> : null}
        <button type="submit" disabled={loading} className="gradient-btn auth-shell__submit disabled:opacity-50">
          {loading ? 'Signing in…' : 'Enter dashboard'}
        </button>
      </form>
    </AuthShell>
  );
}
