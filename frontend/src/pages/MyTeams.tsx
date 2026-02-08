import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { listTeams, getAuth, type TeamListItem } from '../api';
import '../App.css';

export default function MyTeams() {
  const [teams, setTeams] = useState<TeamListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const auth = getAuth();
    if (!auth) {
      setError('You must be logged in to view your teams.');
      setLoading(false);
      return;
    }
    setError(null);
    listTeams(auth.user_id)
      .then(setTeams)
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        setError(
          msg === 'Failed to fetch'
            ? 'Could not reach the API. Make sure the backend is running (e.g. uvicorn backend.api:app --reload --port 8000).'
            : msg
        );
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="card">
        <h1>View Team</h1>
        <p className="team-summary-meta">Loading your teams…</p>
      </div>
    );
  }

  const auth = getAuth();
  if (!auth) {
    return (
      <div className="card">
        <h1>View Team</h1>
        <p className="error">{error ?? 'You must be logged in to view your teams.'}</p>
        <Link to="/login" className="nav-link">Log in</Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <h1>View Team</h1>
        <p className="error">{error}</p>
        <Link to="/" className="nav-link">Back to Home</Link>
      </div>
    );
  }

  return (
    <div className="card">
      <h1>View Team</h1>
      <p className="team-summary-meta">
        Select a team to view roster and last match points.
      </p>
      {teams.length === 0 ? (
        <p className="team-summary-meta">You have no teams yet.</p>
      ) : (
        <ul className="team-summary-list">
          {teams.map((t) => (
            <li key={t.id}>
              <Link to={`/team/${t.id}`}>
                {t.name}
                {t.gender ? ` (${t.gender})` : ''}
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p style={{ marginTop: '1rem' }}>
        <Link to="/create-phase2" className="nav-link">Create a team</Link>
      </p>
    </div>
  );
}
