import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import FilmAuth from '../film/FilmAuth';

import { usePageMeta } from '../utils/pageMeta';
export default function SignupPage() {
  usePageMeta('Create your account');
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
    <FilmAuth
      kicker="Account"
      title="Create your account"
      lead="Your account keeps your consultation, your answer and your files private to you."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" state={{ from: redirect }}>
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="film-form film-form--auth">
        <label className="film-field">
          Name
          <input
            type="text"
            autoComplete="name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
          />
        </label>
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
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
          />
        </label>
        {error ? <p className="film-error">{error}</p> : null}
        <button
          type="submit"
          className="film-pill"
          disabled={loading}
        >
          {loading ? 'Creating…' : 'Create account'}
        </button>
      </form>
    </FilmAuth>
  );
}
