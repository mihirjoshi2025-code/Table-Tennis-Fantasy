import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { getLeagueMatch } from '../api';
import type { LeagueMatchWithSlots } from '../api';
import '../App.css';

export default function LeagueMatchSummary() {
  const { matchId } = useParams<{ matchId: string }>();
  const [match, setMatch] = useState<LeagueMatchWithSlots | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!matchId) return;
    setLoading(true);
    getLeagueMatch(matchId)
      .then((m) => setMatch(m as LeagueMatchWithSlots))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [matchId]);

  if (loading || !match) {
    return (
      <div className="card">
        <p>{loading ? 'Loading…' : 'Match not found.'}</p>
        <Link to="/leagues" className="nav-link">← Leagues</Link>
      </div>
    );
  }

  if (match.status !== 'completed') {
    return (
      <div className="card">
        <p>Full match momentum is available after the match completes.</p>
        <Link to={`/league-match/${matchId}`} className="nav-link">← Back to match</Link>
      </div>
    );
  }

  const totalMomentum = match.total_momentum ?? [];
  const hasData = totalMomentum.length > 0;

  return (
    <div className="card">
      <h1>Full match momentum</h1>
      <p className="team-summary-meta">
        {match.home_team_name ?? 'Home'} vs {match.away_team_name ?? 'Away'} · Table tennis points over time
      </p>
      {error && <p className="error">{error}</p>}
      <p style={{ marginBottom: '1rem' }}>
        <Link to={`/league-match/${matchId}`} className="nav-link">← Back to match</Link>
      </p>

      {hasData ? (
        <>
          <p className="team-summary-meta" style={{ marginBottom: '0.75rem' }}>
            Time (seconds) vs cumulative table tennis points scored (not fantasy points).
          </p>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={totalMomentum} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #333)" />
              <XAxis dataKey="time_seconds" unit="s" stroke="var(--muted, #888)" fontSize={12} />
              <YAxis stroke="var(--muted, #888)" fontSize={12} />
              <Tooltip
                contentStyle={{ background: 'var(--card-bg, #1a1a1a)', border: '1px solid var(--border, #333)' }}
                labelFormatter={(v) => `Time: ${v}s`}
                formatter={(value: number) => [value, '']}
              />
              <Legend />
              <Line type="monotone" dataKey="cumul_tt_home" name={match.home_team_name ?? 'Home'} stroke="var(--primary, #0af)" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="cumul_tt_away" name={match.away_team_name ?? 'Away'} stroke="var(--accent, #f80)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </>
      ) : (
        <p className="team-summary-meta">No momentum data for this match.</p>
      )}

      <p style={{ marginTop: '1.5rem' }}>
        <Link to={`/league-match/${matchId}/live`} className="nav-link">View games (1–7)</Link>
        {' · '}
        <Link to={`/league-match/${matchId}`} className="nav-link">Back to match</Link>
      </p>
    </div>
  );
}
