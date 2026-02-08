import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { login, clearAuth } from '../api';
import '../App.css';

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!username.trim()) {
      setError('Enter a username.');
      return;
    }
    if (!password) {
      setError('Enter your password.');
      return;
    }
    setLoading(true);
    try {
      clearAuth();
      await login(username.trim(), password);
      navigate('/');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h1>Log in</h1>
      <p className="team-summary-meta">Sign in to create and manage teams.</p>
      <form onSubmit={handleSubmit}>
        <div className="input-group">
          <label htmlFor="login-username">Username</label>
          <input
            id="login-username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username"
            autoComplete="username"
          />
        </div>
        <div className="input-group">
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoComplete="current-password"
          />
        </div>
        {error && <p className="error">{error}</p>}
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? 'Signing in…' : 'Log in'}
        </button>
      </form>
      <p className="team-summary-meta" style={{ marginTop: '1rem' }}>
        No account? <Link to="/signup">Sign up</Link>
      </p>
    </div>
  );
}
