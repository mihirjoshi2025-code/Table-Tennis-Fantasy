import { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  getLeagueMatch,
  startLiveLeagueMatch,
  fastForwardLeagueMatch,
  leagueMatchWebSocketUrl,
} from '../api';
import type { LeagueMatch } from '../api';
import '../App.css';

export default function LeagueMatchLive() {
  const { matchId } = useParams<{ matchId: string }>();
  const [match, setMatch] = useState<LeagueMatch | null>(null);
  const [live, setLive] = useState<{
    elapsed_seconds: number;
    home_score: number;
    away_score: number;
    highlights: Array<Record<string, unknown>>;
    done: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

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
    wsRef.current = ws;
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'live_update') {
          const elapsed = data.elapsed_seconds ?? 0;
          const home = data.home_score ?? 0;
          const away = data.away_score ?? 0;
          setLive({
            elapsed_seconds: elapsed,
            home_score: home,
            away_score: away,
            highlights: data.highlights ?? [],
            done: data.done ?? false,
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
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [matchId, match?.status]);

  const handleStartLive = async () => {
    if (!matchId) return;
    setError(null);
    setActionLoading(true);
    try {
      await startLiveLeagueMatch(matchId);
      setMatch((prev) => prev ? { ...prev, status: 'live' } : null);
      getLeagueMatch(matchId).then(setMatch);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionLoading(false);
    }
  };

  const handleFastForward = async () => {
    if (!matchId) return;
    setError(null);
    setActionLoading(true);
    try {
      const result = await fastForwardLeagueMatch(matchId);
      setMatch((prev) => prev ? { ...prev, status: 'completed', home_score: result.home_score, away_score: result.away_score } : null);
      setLive({ elapsed_seconds: 7 * 35, home_score: result.home_score, away_score: result.away_score, highlights: result.highlights ?? [], done: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionLoading(false);
    }
  };

  if (loading || !match) {
    return (
      <div className="card">
        <p>{loading ? 'Loading…' : 'Match not found.'}</p>
        <Link to="/leagues" className="nav-link">← Leagues</Link>
      </div>
    );
  }

  const homeScore = live?.home_score ?? match.home_score;
  const awayScore = live?.away_score ?? match.away_score;
  const isLive = match.status === 'live';
  const isCompleted = match.status === 'completed';
  const isScheduled = match.status === 'scheduled';
  const totalLiveSeconds = 7 * 35;  // ~245s total (35s per game)
  const remainingSeconds = isLive && live ? Math.max(0, totalLiveSeconds - (live.elapsed_seconds ?? 0)) : 0;

  return (
    <div className="card">
      <h1>League match</h1>
      <p className="team-summary-meta">
        {match.home_team_name ?? match.home_team_id.slice(0, 12) + '…'} vs {match.away_team_id ? (match.away_team_name ?? match.away_team_id.slice(0, 12) + '…') : 'Bye'}
        {isLive && <span className="live-badge"> LIVE</span>}
      </p>
      {error && <p className="error">{error}</p>}

      <div className="live-score" style={{ display: 'flex', gap: '2rem', alignItems: 'center', margin: '1rem 0' }}>
        <div>
          <div className="score-value">{homeScore}</div>
          <div className="team-summary-meta">{match.home_team_name ?? 'Home'}</div>
        </div>
        <div className="team-summary-meta">–</div>
        <div>
          <div className="score-value">{awayScore}</div>
          <div className="team-summary-meta">{match.away_team_id ? (match.away_team_name ?? 'Away') : 'Bye'}</div>
        </div>
      </div>

      {isLive && (
        <p className="team-summary-meta">
          Elapsed: {live?.elapsed_seconds?.toFixed(1) ?? 0}s · Remaining: ~{remainingSeconds.toFixed(0)}s
          {' · '}
          <Link to={`/league-match/${matchId}/live`} className="nav-link">
            View live summary & momentum graph
          </Link>
        </p>
      )}
      {(isLive || isCompleted) && (
        <p className="team-summary-meta" style={{ marginBottom: '0.5rem' }}>
          <Link to={`/league-match/${matchId}/live`} className="nav-link">
            View games & momentum
          </Link>
          {isCompleted && (
            <>
              {' · '}
              <Link to={`/league-match/${matchId}/summary`} className="nav-link">
                Full match momentum (TT points)
              </Link>
            </>
          )}
        </p>
      )}

      {isScheduled && match.away_team_id && (
        <>
          <button type="button" className="btn-primary" onClick={handleStartLive} disabled={actionLoading}>
            Start live (~4–5 min: 35s per game)
          </button>
          <button type="button" className="btn-secondary" style={{ marginLeft: '0.5rem' }} onClick={handleFastForward} disabled={actionLoading}>
            Simulate instantly
          </button>
        </>
      )}
      {isLive && (
        <button type="button" className="btn-secondary" onClick={handleFastForward} disabled={actionLoading}>
          Fast forward match
        </button>
      )}

      <p style={{ marginTop: '1rem' }}>
        <Link to="/leagues" className="nav-link">← Leagues</Link>
      </p>
    </div>
  );
}
