import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import AuthShell from '../components/AuthShell';

export default function SignupPage() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirect = (location.state as { from?: string } | null)?.from ?? '/solutions';
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signup(name, email, password);
      navigate(redirect, { replace: true });
    } catch {
      setError('Could not create account. Email may already be in use.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Account"
      title="Create your account"
      lead="Everyone sees the same industry template. Your account keeps your personalized version private."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" state={{ from: redirect }}>
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="auth-shell__form">
        <label className="auth-shell__label">
          Name
          <input
            type="text"
            autoComplete="name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="auth-shell__input"
            placeholder="Your name"
          />
        </label>
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
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="auth-shell__input"
            placeholder="At least 8 characters"
          />
        </label>
        {error ? <p className="auth-shell__error">{error}</p> : null}
        <button
          type="submit"
          className="gradient-btn auth-shell__submit disabled:opacity-60"
          disabled={loading}
        >
          {loading ? 'Creating…' : 'Create account'}
        </button>
      </form>
    </AuthShell>
  );
}
