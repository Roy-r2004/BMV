import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { persistAdminSession } from '../api/admin';
import { useAuth } from '../context/AuthContext';
import FilmAuth from '../film/FilmAuth';


import { usePageMeta } from '../utils/pageMeta';
export default function LoginPage() {

  usePageMeta('Sign in');
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
    <FilmAuth
      kicker="Account"
      title="Welcome back"
      lead="Sign in to pick up your consultation, your answer and every file in your package."
      footer={
        <>
          New here?{' '}
          <Link to="/signup" state={{ from: redirect }}>
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="film-form film-form--auth">
        <label className="film-field">
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
          />
        </label>
        <label className="film-field">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error ? <p className="film-error">{error}</p> : null}
        <button
          type="submit"
          className="film-pill"
          disabled={loading}
        >
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </FilmAuth>
  );
}
