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
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
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
        <Link to="/teams" className="nav-link">← View Team</Link>
      </div>
    );
  }

  const players = team.players ?? [];
  const roster = team.roster ?? [];
  const created = team.created_at ? new Date(team.created_at).toLocaleString() : '—';
  const playerById = Object.fromEntries(players.map((p) => [p.id, p]));

  return (
    <div className="card">
      <h1>{team.name}</h1>
      <p className="team-summary-meta">
        Gender: {team.gender} · Created: {created}
        {team.budget != null ? ` · Budget: ${team.budget}` : ''}
      </p>

      {roster.length > 0 ? (
        <>
          <h2>Roster</h2>
          <table className="roster-table">
            <thead>
              <tr>
                <th>Slot</th>
                <th>Player</th>
                <th>Captain</th>
                <th>Role</th>
                <th>Last match points</th>
              </tr>
            </thead>
            <tbody>
              {roster.map((r) => {
                const p = playerById[r.player_id];
                const name = p?.name ?? r.player_id;
                const country = p?.country ? ` (${p.country})` : '';
                const points =
                  r.last_match_points != null && r.last_match_points !== undefined
                    ? String(r.last_match_points)
                    : '--';
                const roleLabel = r.role ? r.role.charAt(0).toUpperCase() + r.role.slice(1) : '—';
                return (
                  <tr key={r.player_id}>
                    <td>{r.slot}</td>
                    <td>{name}{country}</td>
                    <td>{r.is_captain ? 'Yes' : '—'}</td>
                    <td title={r.role ?? undefined}>{roleLabel}</td>
                    <td>{points}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      ) : (
        <>
          <h2>Players ({players.length})</h2>
          <ul className="team-summary-list">
            {players.map((p, i) => (
              <li key={p.id}>
                {i + 1}. {p.name ?? p.id} {p.country ? `(${p.country})` : ''}
              </li>
            ))}
          </ul>
        </>
      )}

      <button
        type="button"
        className="btn-secondary"
        onClick={() => window.history.back()}
        style={{ marginTop: '1rem' }}
      >
        Back
      </button>
      <p style={{ marginTop: '1rem' }}>
        <Link to="/teams" className="nav-link">View all teams</Link>
        {' · '}
        <Link to="/create-phase2" className="nav-link">Create another team</Link>
      </p>
    </div>
  );
}
