import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getTeam, type Team } from '../api';
import '../App.css';

export default function TeamSummary() {
  const { teamId } = useParams<{ teamId: string }>();
  const [team, setTeam] = useState<Team | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!teamId) return;
    setLoading(true);
    setError(null);
    getTeam(teamId)
      .then(setTeam)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [teamId]);

  if (loading) {
    return (
      <div className="card">
        <p className="team-summary-meta">Loading team…</p>
      </div>
    );
  }

  if (error || !team) {
    return (
      <div className="card">
        <h1>Team</h1>
        <p className="error">{error ?? 'Team not found.'}</p>
        <Link to="/" className="nav-link">← Back to Create Team</Link>
      </div>
    );
  }

  const players = team.players ?? [];
  const created = team.created_at ? new Date(team.created_at).toLocaleString() : '—';

  return (
    <div className="card">
      <h1>{team.name}</h1>
      <p className="team-summary-meta">
        Gender: {team.gender} · Created: {created}
      </p>
      <p className="team-summary-meta" style={{ marginBottom: '1rem' }}>
        Team saved. Data round-trip confirmed.
      </p>

      <h2>Players ({players.length})</h2>
      <ul className="team-summary-list">
        {players.map((p, i) => (
          <li key={p.id}>
            {i + 1}. {p.name ?? p.id} {p.country ? `(${p.country})` : ''}
          </li>
        ))}
      </ul>

      <button
        type="button"
        className="btn-secondary"
        onClick={() => window.history.back()}
        style={{ marginTop: '1rem' }}
      >
        Back
      </button>
      <p style={{ marginTop: '1rem' }}>
        <Link to="/" className="nav-link">Create another team</Link>
      </p>
    </div>
  );
}
