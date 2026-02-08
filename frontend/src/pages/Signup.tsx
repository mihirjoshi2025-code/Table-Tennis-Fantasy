import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { signup, clearAuth } from '../api';
import '../App.css';

const MIN_PASSWORD_LENGTH = 6;

export default function Signup() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!username.trim()) {
      setError('Choose a username.');
      return;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    setLoading(true);
    try {
      clearAuth();
      await signup(username.trim(), password);
      navigate('/');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sign up failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h1>Sign up</h1>
      <p className="team-summary-meta">Create an account to build teams and simulate matches.</p>
      <form onSubmit={handleSubmit}>
        <div className="input-group">
          <label htmlFor="signup-username">Username</label>
          <input
            id="signup-username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username"
            autoComplete="username"
          />
        </div>
        <div className="input-group">
          <label htmlFor="signup-password">Password</label>
          <input
            id="signup-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 6 characters"
            autoComplete="new-password"
          />
        </div>
        {error && <p className="error">{error}</p>}
        <button
          type="submit"
          className="btn-primary"
          disabled={loading || password.length < MIN_PASSWORD_LENGTH}
        >
          {loading ? 'Creating account…' : 'Sign up'}
        </button>
      </form>
      <p className="team-summary-meta" style={{ marginTop: '1rem' }}>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </div>
  );
}
