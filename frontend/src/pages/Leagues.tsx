import { useState, useEffect, useRef } from 'react';
import { Link, useParams, useLocation } from 'react-router-dom';
import {
  listLeagues,
  createLeague,
  getLeague,
  joinLeague,
  startLeague,
  fastForwardWeek,
  getLeagueStandings,
  listTeams,
  restartLeagueMatch,
  type League,
  type LeagueDetail,
  type LeagueStanding,
} from '../api';
import { getAuth } from '../api';
import '../App.css';

export default function Leagues() {
  const { leagueId } = useParams<{ leagueId: string }>();
  const [leagues, setLeagues] = useState<League[]>([]);
  const [detail, setDetail] = useState<LeagueDetail | null>(null);
  const [standings, setStandings] = useState<LeagueStanding[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createName, setCreateName] = useState('');
  const [createMax, setCreateMax] = useState(8);
  const [joinLeagueIdInput, setJoinLeagueIdInput] = useState('');
  const [joinTeamId, setJoinTeamId] = useState('');
  const [userTeams, setUserTeams] = useState<Array<{ id: string; name: string }>>([]);
  const [createdLeagueId, setCreatedLeagueId] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState(false);
  const createSectionRef = useRef<HTMLDivElement>(null);
  const joinSectionRef = useRef<HTMLDivElement>(null);
  const auth = getAuth();
  const location = useLocation();

  useEffect(() => {
    listLeagues(!!auth?.user_id)
      .then((data) => setLeagues(data))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [auth?.user_id]);

  useEffect(() => {
    if (auth?.user_id) {
      listTeams(auth.user_id)
        .then((teams) => setUserTeams(teams.map((t) => ({ id: t.id, name: t.name }))))
        .catch(() => setUserTeams([]));
    }
  }, [auth?.user_id]);

  useEffect(() => {
    const hash = location.hash.slice(1);
    if (hash === 'create' && createSectionRef.current) {
      createSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else if (hash === 'join' && joinSectionRef.current) {
      joinSectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [location.pathname, location.hash]);

  useEffect(() => {
    if (leagueId) {
      setLoading(true);
      getLeague(leagueId)
        .then((d) => {
          setDetail(d);
          return getLeagueStandings(leagueId);
        })
        .then((s) => setStandings(s))
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false));
    } else {
      setDetail(null);
      setStandings([]);
    }
  }, [leagueId]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setCreatedLeagueId(null);
    setLoading(true);
    try {
      const league = await createLeague(createName.trim(), createMax);
      setLeagues((prev) => [league, ...prev]);
      setCreateName('');
      setCreatedLeagueId(league.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const copyLeagueId = () => {
    if (!createdLeagueId) return;
    navigator.clipboard.writeText(createdLeagueId).then(() => {
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
    });
  };

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!joinLeagueIdInput.trim() || !joinTeamId) return;
    setLoading(true);
    try {
      await joinLeague(joinLeagueIdInput.trim(), joinTeamId);
      setLeagues((prev) => prev.map((l) => (l.id === joinLeagueIdInput ? { ...l } : l)));
      if (leagueId === joinLeagueIdInput) {
        getLeague(leagueId).then(setDetail);
      }
      setJoinLeagueIdInput('');
      setJoinTeamId('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleStart = async () => {
    if (!detail?.id) return;
    setError(null);
    setLoading(true);
    try {
      await startLeague(detail.id);
      getLeague(detail.id).then(setDetail);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleFastForwardWeek = async () => {
    if (!detail?.id) return;
    setError(null);
    setLoading(true);
    try {
      await fastForwardWeek(detail.id);
      getLeague(detail.id).then(setDetail);
      getLeagueStandings(detail.id).then(setStandings);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const [restartingMatchId, setRestartingMatchId] = useState<string | null>(null);
  const handleRestartMatch = async (matchId: string) => {
    if (!detail?.id) return;
    setError(null);
    setRestartingMatchId(matchId);
    try {
      await restartLeagueMatch(matchId);
      getLeague(detail.id).then(setDetail);
      getLeagueStandings(detail.id).then(setStandings);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRestartingMatchId(null);
    }
  };

  if (leagueId && !detail && loading) {
    return (
      <div className="card">
        <p>Loading league…</p>
        <Link to="/leagues" className="nav-link">← All leagues</Link>
      </div>
    );
  }
  if (leagueId && !detail && !loading) {
    return (
      <div className="card">
        <p>League not found.</p>
        <Link to="/leagues" className="nav-link">← All leagues</Link>
      </div>
    );
  }
  if (leagueId && detail) {
    const isOwner = auth?.user_id === detail.owner_id;
    const canStart = detail.status === 'open' && (detail.members?.length ?? 0) >= 2 && isOwner;
    const canFastForward = detail.status === 'active' && isOwner;

    return (
      <div className="card">
        <h1>{detail.name}</h1>
        <p className="team-summary-meta">
          Status: {detail.status}
          {detail.started_at != null && (
            <> · Started {new Date(detail.started_at).toLocaleDateString()}</>
          )}
          {detail.current_week != null && detail.total_weeks != null && (
            <> · Week {detail.current_week} of {detail.total_weeks}</>
          )}
          {detail.members != null && (
            <> · {detail.members.length} of {detail.max_teams} teams</>
          )}
        </p>
        {error && <p className="error">{error}</p>}

        {detail.members && detail.members.length > 0 && (
          <>
            <h2>Teams in this league</h2>
            <ul className="team-summary-list">
              {detail.members.map((m) => (
                <li key={m.team_id}>
                  <Link to={`/team/${m.team_id}`}>
                    {m.team_name ?? m.team_id}
                  </Link>
                  <span className="team-summary-meta" style={{ marginLeft: '0.5rem' }}>
                    — View roster
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        {standings.length > 0 && (
          <>
            <h2>Standings</h2>
            <table className="roster-table">
              <thead>
                <tr>
                  <th>Team</th>
                  <th>W</th>
                  <th>L</th>
                  <th>D</th>
                  <th>PF</th>
                  <th>PA</th>
                  <th>Diff</th>
                </tr>
              </thead>
              <tbody>
                {standings.map((s) => {
                  const member = detail.members?.find((m) => m.team_id === s.team_id);
                  const teamName = member?.team_name ?? s.team_id.slice(0, 8) + '…';
                  return (
                    <tr key={s.team_id}>
                      <td>
                        <Link to={`/team/${s.team_id}`}>{teamName}</Link>
                      </td>
                      <td>{s.wins}</td>
                      <td>{s.losses}</td>
                      <td>{s.draws}</td>
                      <td>{s.points_for}</td>
                      <td>{s.points_against}</td>
                      <td>{s.differential}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}

        {detail.schedule && detail.schedule.length > 0 && (
          <>
            <h2>Schedule</h2>
            <p className="team-summary-meta" style={{ marginBottom: '0.75rem' }}>
              Round-robin: every team plays every other team once. BYE when odd number of teams.
            </p>
            {detail.schedule.map((week) => {
              const isCurrent = detail.current_week != null && week.week_number === detail.current_week;
              const isPast = detail.current_week != null && week.week_number < detail.current_week;
              const weekLabel = isPast ? `Week ${week.week_number} (completed)` : isCurrent ? `Week ${week.week_number} (current)` : `Week ${week.week_number}`;
              return (
                <div key={week.week_id} className="schedule-week" style={{ marginBottom: '1rem' }}>
                  <h3 className="team-summary-meta" style={{ fontWeight: 600, marginBottom: '0.35rem' }}>{weekLabel}</h3>
                  <ul className="team-summary-list">
                    {week.matches.map((m) => {
                      const homeName = detail.members?.find((mb) => mb.team_id === m.home_team_id)?.team_name ?? m.home_team_id.slice(0, 8) + '…';
                      const awayName = m.away_team_id
                        ? (detail.members?.find((mb) => mb.team_id === m.away_team_id)?.team_name ?? m.away_team_id.slice(0, 8) + '…')
                        : null;
                      const label = awayName ? `${homeName} vs ${awayName}` : `${homeName} — BYE`;
                      const score = m.status === 'completed' ? ` ${m.home_score}–${m.away_score}` : '';
                      return (
                        <li key={m.id}>
                          {m.away_team_id ? (
                            <Link to={`/league-match/${m.id}`}>{label}{score}</Link>
                          ) : (
                            <span>{label}{score}</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </>
        )}

        {detail.current_week_matches && detail.current_week_matches.length > 0 && (
          <>
            <h2>Current week matches</h2>
            <ul className="team-summary-list">
              {detail.current_week_matches.map((m) => {
                const homeName = detail.members?.find((mb) => mb.team_id === m.home_team_id)?.team_name ?? m.home_team_id.slice(0, 8) + '…';
                const awayName = m.away_team_id ? (detail.members?.find((mb) => mb.team_id === m.away_team_id)?.team_name ?? m.away_team_id.slice(0, 8) + '…') : 'Bye';
                const canRestart = m.status === 'completed' || m.status === 'live';
                return (
                  <li key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <Link to={`/league-match/${m.id}`}>
                      {homeName} vs {awayName} — {m.status} {m.status === 'completed' ? `${m.home_score}–${m.away_score}` : ''}
                    </Link>
                    {canRestart && (
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.85rem' }}
                        onClick={() => handleRestartMatch(m.id)}
                        disabled={restartingMatchId === m.id}
                      >
                        {restartingMatchId === m.id ? 'Restarting…' : 'Restart match'}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}

        {canStart && (
          <button type="button" className="btn-primary" onClick={handleStart} disabled={loading}>
            Start league
          </button>
        )}
        {canFastForward && (
          <button type="button" className="btn-secondary" onClick={handleFastForwardWeek} disabled={loading}>
            Fast forward week
          </button>
        )}

        <p style={{ marginTop: '1rem' }}>
          <Link to="/leagues" className="nav-link">← All leagues</Link>
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <h1>Leagues</h1>
      {error && <p className="error">{error}</p>}

      {auth && (
        <>
          <div id="create" ref={createSectionRef}>
            <h2>Create league</h2>
            {createdLeagueId && (
              <div className="league-id-success">
                <p className="team-summary-meta">
                  League created. Share this <strong>League ID</strong> so others can join:
                </p>
                <div className="league-id-row">
                  <code className="league-id-value">{createdLeagueId}</code>
                  <button type="button" className="btn-secondary league-id-copy" onClick={copyLeagueId}>
                    {copyFeedback ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <p className="team-summary-meta" style={{ marginTop: '0.5rem' }}>
                  <Link to={`/leagues/${createdLeagueId}`}>Open league →</Link>
                </p>
              </div>
            )}
            <form onSubmit={handleCreate}>
              <div className="input-group">
                <label htmlFor="league-name">Name</label>
                <input
                  id="league-name"
                  type="text"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="League name"
                />
              </div>
              <div className="input-group">
                <label htmlFor="league-max">Max teams</label>
                <input
                  id="league-max"
                  type="number"
                  min={2}
                  max={20}
                  value={createMax}
                  onChange={(e) => setCreateMax(Number(e.target.value))}
                />
              </div>
              <button type="submit" className="btn-primary" disabled={loading || !createName.trim()}>
                Create
              </button>
            </form>
          </div>

          <div id="join" ref={joinSectionRef}>
            <h2>Join league</h2>
            <form onSubmit={handleJoin}>
              <div className="input-group">
                <label htmlFor="join-league-id">League ID</label>
                <input
                  id="join-league-id"
                  type="text"
                  value={joinLeagueIdInput}
                  onChange={(e) => setJoinLeagueIdInput(e.target.value)}
                  placeholder="Paste league ID (from league creator)"
                />
              </div>
              <div className="input-group">
                <label htmlFor="join-team-id">Your team</label>
                <select
                  id="join-team-id"
                  value={joinTeamId}
                  onChange={(e) => setJoinTeamId(e.target.value)}
                >
                  <option value="">Select team</option>
                  {userTeams.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>
              <button type="submit" className="btn-secondary" disabled={loading || !joinLeagueIdInput.trim() || !joinTeamId}>
                Join
              </button>
            </form>
          </div>
        </>
      )}

      <h2>My leagues</h2>
      <ul className="team-summary-list">
        {leagues.map((l) => (
          <li key={l.id}>
            <Link to={`/leagues/${l.id}`}>{l.name}</Link>
            <span className="team-summary-meta"> — {l.status} · {l.max_teams} max</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
