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
import { getLeagueMatchGame, explainLeagueMatchGame } from '../api';
import type { LeagueMatchGame } from '../api';
import '../App.css';

const NUM_SLOTS = 7;

export default function LeagueMatchGamePage() {
  const { matchId, slot: slotParam } = useParams<{ matchId: string; slot: string }>();
  const slot = Math.min(NUM_SLOTS, Math.max(1, parseInt(slotParam ?? '1', 10) || 1));
  const [game, setGame] = useState<LeagueMatchGame | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!matchId) return;
    setLoading(true);
    getLeagueMatchGame(matchId, slot)
      .then(setGame)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [matchId, slot]);

  useEffect(() => {
    if (!matchId || !game) return;
    setSummaryLoading(true);
    explainLeagueMatchGame(matchId, slot)
      .then((r) => setSummary(r.explanation_text))
      .catch(() => setSummary(null))
      .finally(() => setSummaryLoading(false));
  }, [matchId, slot, game != null]);

  if (loading || !matchId) {
    return (
      <div className="card">
        <p>{loading ? 'Loading…' : 'Match not found.'}</p>
        <Link to="/leagues" className="nav-link">← Leagues</Link>
      </div>
    );
  }

  if (!game) {
    return (
      <div className="card">
        <p>{error ?? 'Game not found.'}</p>
        <Link to={`/league-match/${matchId}`} className="nav-link">← Back to match</Link>
      </div>
    );
  }

  const momentumSeries = game.momentum_series ?? [];
  const hasMomentum = momentumSeries.length > 0;
  const chartData = hasMomentum
    ? momentumSeries.map((p) => ({
        time_seconds: p.time_seconds,
        home: p.cumul_tt_a,
        away: p.cumul_tt_b,
        differential: p.cumul_tt_a - p.cumul_tt_b,
      }))
    : [];

  const statsA = game.player_a_stats ?? {};
  const statsB = game.player_b_stats ?? {};

  return (
    <div className="card">
      <h1>Game {slot} of {NUM_SLOTS}</h1>
      <p className="team-summary-meta">
        {game.home_player_name} (home) vs {game.away_player_name} (away)
      </p>
      {error && <p className="error">{error}</p>}
      <p style={{ marginBottom: '1rem' }}>
        <Link to={`/league-match/${matchId}/live`} className="nav-link">← All games</Link>
        {' · '}
        <Link to={`/league-match/${matchId}`} className="nav-link">Match summary</Link>
      </p>

      <h2>Momentum (table tennis points)</h2>
      <p className="team-summary-meta" style={{ marginBottom: '0.75rem' }}>
        Time vs points scored in this game (actual table tennis points, not fantasy).
      </p>
      {hasMomentum && chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #333)" />
            <XAxis dataKey="time_seconds" unit="s" stroke="var(--muted, #888)" fontSize={12} />
            <YAxis stroke="var(--muted, #888)" fontSize={12} />
            <Tooltip
              contentStyle={{ background: 'var(--card-bg, #1a1a1a)', border: '1px solid var(--border, #333)' }}
              labelFormatter={(v) => `Time: ${v}s`}
            />
            <Legend />
            <Line type="monotone" dataKey="home" name={game.home_player_name} stroke="var(--primary, #0af)" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="away" name={game.away_player_name} stroke="var(--accent, #f80)" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="differential" name="Diff (H−A)" stroke="var(--text-muted, #888)" strokeWidth={1.5} dot={false} strokeDasharray="4 4" />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p className="team-summary-meta">No point-by-point data for this game.</p>
      )}

      <h2>Stats</h2>
      <div className="team-summary-meta" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
        <div style={{ padding: '0.75rem', background: 'var(--card-bg-alt, #222)', borderRadius: 8 }}>
          <strong>{game.home_player_name}</strong>
          <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem' }}>
            <li>Forehand winners: {Number(statsA.forehand_winners ?? 0)}</li>
            <li>Backhand winners: {Number(statsA.backhand_winners ?? 0)}</li>
            <li>Service winners: {Number(statsA.service_winners ?? 0)}</li>
            <li>Unforced errors: {Number(statsA.unforced_errors ?? 0)}</li>
            <li>Serve win %: {game.serve_win_pct_a != null ? `${game.serve_win_pct_a}%` : '—'}</li>
          </ul>
        </div>
        <div style={{ padding: '0.75rem', background: 'var(--card-bg-alt, #222)', borderRadius: 8 }}>
          <strong>{game.away_player_name}</strong>
          <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.25rem' }}>
            <li>Forehand winners: {Number(statsB.forehand_winners ?? 0)}</li>
            <li>Backhand winners: {Number(statsB.backhand_winners ?? 0)}</li>
            <li>Service winners: {Number(statsB.service_winners ?? 0)}</li>
            <li>Unforced errors: {Number(statsB.unforced_errors ?? 0)}</li>
            <li>Serve win %: {game.serve_win_pct_b != null ? `${game.serve_win_pct_b}%` : '—'}</li>
          </ul>
        </div>
      </div>
      <p className="team-summary-meta">
        Total points: {game.total_points} · Longest rally: {game.longest_rally ?? '—'} · Avg rally: {game.avg_rally_length ?? '—'}
      </p>

      <h2>AI game summary</h2>
      {summaryLoading ? (
        <p className="team-summary-meta">Loading summary…</p>
      ) : summary ? (
        <div className="team-summary-meta" style={{ padding: '1rem', background: 'var(--card-bg-alt, #222)', borderRadius: 8, whiteSpace: 'pre-wrap' }}>
          {summary}
        </div>
      ) : (
        <p className="team-summary-meta">Summary not available.</p>
      )}

      <p style={{ marginTop: '1.5rem' }}>
        {slot > 1 && (
          <Link to={`/league-match/${matchId}/live/game/${slot - 1}`} className="nav-link">← Game {slot - 1}</Link>
        )}
        {slot > 1 && slot < NUM_SLOTS && ' · '}
        {slot < NUM_SLOTS && (
          <Link to={`/league-match/${matchId}/live/game/${slot + 1}`} className="nav-link">Game {slot + 1} →</Link>
        )}
        {slot === NUM_SLOTS && slot > 1 && <Link to={`/league-match/${matchId}/live`} className="nav-link">← All games</Link>}
      </p>
    </div>
  );
}
