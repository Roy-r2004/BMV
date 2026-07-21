import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { persistAdminSession } from '../api/admin';
import { useAuth } from '../context/AuthContext';
import AuthShell from '../components/AuthShell';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirect = (location.state as { from?: string } | null)?.from ?? '/solutions';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const user = await login(email, password);
      if (user.is_admin) {
        const token = localStorage.getItem('bmv_user_token');
        if (token) {
          persistAdminSession({
            success: true,
            message: 'ok',
            token,
            user: { id: user.id, name: user.name, email: user.email, is_admin: true },
          });
        }
        navigate('/admin', { replace: true });
        return;
      }
      navigate(redirect, { replace: true });
    } catch {
      setError('Invalid email or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Account"
      title="Welcome back"
      lead="Sign in to keep your industry template versions private and edit them with AI."
      footer={
        <>
          New here?{' '}
          <Link to="/signup" state={{ from: redirect }}>
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="auth-shell__form">
        <label className="auth-shell__label">
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="auth-shell__input"
            placeholder="you@company.com"
          />
        </label>
        <label className="auth-shell__label">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="auth-shell__input"
          />
        </label>
        {error ? <p className="auth-shell__error">{error}</p> : null}
        <button
          type="submit"
          className="gradient-btn auth-shell__submit disabled:opacity-60"
          disabled={loading}
        >
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </AuthShell>
  );
}
