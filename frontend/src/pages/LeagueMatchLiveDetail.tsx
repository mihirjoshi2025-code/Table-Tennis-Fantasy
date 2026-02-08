import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getLeagueMatch, leagueMatchWebSocketUrl } from '../api';
import type { LeagueMatch } from '../api';
import '../App.css';

const NUM_SLOTS = 7;

export default function LeagueMatchLiveDetail() {
  const { matchId } = useParams<{ matchId: string }>();
  const [match, setMatch] = useState<LeagueMatch | null>(null);
  const [live, setLive] = useState<{
    elapsed_seconds: number;
    home_score: number;
    away_score: number;
    highlights: Array<Record<string, unknown>>;
    done: boolean;
    games?: Array<Record<string, unknown>>;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!matchId) return;
    setLoading(true);
    getLeagueMatch(matchId)
      .then((m) => {
        setMatch(m);
        if (m.live) setLive(m.live);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [matchId]);

  useEffect(() => {
    if (!matchId || match?.status !== 'live') return;
    const url = leagueMatchWebSocketUrl(matchId);
    const ws = new WebSocket(url);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'live_update') {
          setLive({
            elapsed_seconds: data.elapsed_seconds ?? 0,
            home_score: data.home_score ?? 0,
            away_score: data.away_score ?? 0,
            highlights: data.highlights ?? [],
            done: data.done ?? false,
            games: data.games ?? [],
          });
          if (data.done) {
            setMatch((prev) => prev ? { ...prev, status: 'completed', home_score: data.home_score, away_score: data.away_score } : null);
          }
        }
      } catch {
        // ignore
      }
    };
    ws.onerror = () => {};
    return () => ws.close();
  }, [matchId, match?.status]);

  if (loading || !match) {
    return (
      <div className="card">
        <p>{loading ? 'Loading…' : 'Match not found.'}</p>
        <Link to={`/league-match/${matchId}`} className="nav-link">← Back to match</Link>
      </div>
    );
  }

  const isLive = match.status === 'live';
  const isCompleted = match.status === 'completed';
  const showDetail = isLive || isCompleted;
  const games = live?.games ?? [];

  if (!showDetail) {
    return (
      <div className="card">
        <p>Live summary is available when the match is running or completed.</p>
        <Link to={`/league-match/${matchId}`} className="nav-link">← Back to match</Link>
      </div>
    );
  }

  return (
    <div className="card">
      <h1>Games & momentum</h1>
      <p className="team-summary-meta">
        {match.home_team_name ?? 'Home'} vs {match.away_team_name ?? 'Away'}
        {isLive && <span className="live-badge"> LIVE</span>}
      </p>
      {error && <p className="error">{error}</p>}
      <p style={{ marginBottom: '1rem' }}>
        <Link to={`/league-match/${matchId}`} className="nav-link">← Back to match</Link>
      </p>

      {isCompleted && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h2>Full match</h2>
          <p>
            <Link to={`/league-match/${matchId}/summary`} className="nav-link">
              View full match momentum (time vs table tennis points)
            </Link>
          </p>
        </div>
      )}

      <h2>Per-game pages</h2>
      <p className="team-summary-meta" style={{ marginBottom: '0.75rem' }}>
        Each game has its own page with table tennis momentum and AI summary.
      </p>
      <ul className="team-summary-list" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '0.5rem' }}>
        {Array.from({ length: NUM_SLOTS }, (_, i) => i + 1).map((s) => {
          const g = games[s - 1] as Record<string, unknown> | undefined;
          const done = g && String(g.status) === 'completed';
          return (
            <li key={s}>
              <Link to={`/league-match/${matchId}/live/game/${s}`} className="nav-link">
                Game {s}
                {done ? ' ✓' : isLive ? ' …' : ''}
              </Link>
              {g && (
                <span className="team-summary-meta" style={{ display: 'block', marginTop: 2 }}>
                  {String(g.home_player_name ?? '—')} {Number(g.score_home ?? 0)} – {Number(g.score_away ?? 0)} {String(g.away_player_name ?? '—')}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      <p style={{ marginTop: '1.5rem' }}>
        <Link to={`/league-match/${matchId}`} className="nav-link">← Back to match</Link>
      </p>
    </div>
  );
}
