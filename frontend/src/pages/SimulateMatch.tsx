import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  getAuth,
  listTeams,
  simulateTeamMatch,
  type TeamListItem,
  type TeamMatchResult,
} from '../api';
import '../App.css';

export default function SimulateMatch() {
  const navigate = useNavigate();
  const auth = getAuth();
  const [gender, setGender] = useState<'men' | 'women'>('men');
  const [teams, setTeams] = useState<TeamListItem[]>([]);
  const [teamAId, setTeamAId] = useState('');
  const [teamBId, setTeamBId] = useState('');
  const [loadingTeams, setLoadingTeams] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [result, setResult] = useState<TeamMatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!auth?.user_id) return;
    setLoadingTeams(true);
    setError(null);
    setTeamAId('');
    setTeamBId('');
    setResult(null);
    listTeams(auth.user_id, gender)
      .then(setTeams)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load teams'))
      .finally(() => setLoadingTeams(false));
  }, [auth?.user_id, gender]);

  const handleSimulate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!teamAId || !teamBId || teamAId === teamBId) {
      setError('Select two different teams.');
      return;
    }
    setError(null);
    setResult(null);
    setSimulating(true);
    try {
      const res = await simulateTeamMatch({ team_a_id: teamAId, team_b_id: teamBId });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Simulation failed');
    } finally {
      setSimulating(false);
    }
  };

  const goToMatchDetail = (matchId: string) => {
    navigate(`/match/${matchId}`);
  };

  if (!auth) {
    return (
      <div className="card">
        <h1>Simulate Match</h1>
        <p className="error">You must log in to simulate matches.</p>
        <Link to="/login" className="nav-link">Log in</Link>
      </div>
    );
  }

  const teamA = teams.find((t) => t.id === teamAId);
  const teamB = teams.find((t) => t.id === teamBId);

  return (
    <div className="card">
      <h1>Simulate Match</h1>
      <p className="team-summary-meta">
        Choose gender, then two teams of that gender. 7 active players each; captain gets +50% points.
      </p>

      <div className="simulate-gender">
        <label className="simulate-gender-label">Gender</label>
        <div className="simulate-gender-options">
          <button
            type="button"
            className={gender === 'men' ? 'btn-primary' : 'btn-secondary'}
            onClick={() => setGender('men')}
          >
            Men
          </button>
          <button
            type="button"
            className={gender === 'women' ? 'btn-primary' : 'btn-secondary'}
            onClick={() => setGender('women')}
          >
            Women
          </button>
        </div>
      </div>

      {loadingTeams ? (
        <p className="team-summary-meta">Loading your {gender}&apos;s teams…</p>
      ) : teams.length < 2 ? (
        <p className="team-summary-meta">
          You need at least two <strong>{gender}</strong> teams to simulate.{' '}
          <Link to="/create-phase2">Create a team</Link> first and select &quot;{gender}&quot;.
        </p>
      ) : (
        <form onSubmit={handleSimulate} className="simulate-form">
          <div className="simulate-teams-row">
            <div className="input-group">
              <label htmlFor="team-a">Team A</label>
              <select
                id="team-a"
                value={teamAId}
                onChange={(e) => setTeamAId(e.target.value)}
              >
                <option value="">— Select team —</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
            <div className="input-group">
              <label htmlFor="team-b">Team B</label>
              <select
                id="team-b"
                value={teamBId}
                onChange={(e) => setTeamBId(e.target.value)}
              >
                <option value="">— Select team —</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
          </div>
          {error && <p className="error">{error}</p>}
          <button
            type="submit"
            className="btn-primary"
            disabled={simulating || !teamAId || !teamBId || teamAId === teamBId}
          >
            {simulating ? 'Simulating…' : 'Simulate Match'}
          </button>
        </form>
      )}

      {result && result.highlights.length > 0 && (
        <div className="matchup-result">
          <h2>Matchup</h2>
          <div className="matchup-score-summary">
            <div className="matchup-team-col">
              <span className="matchup-team-name">{teamA?.name ?? result.team_a_id}</span>
              <span className="matchup-team-score">{result.score_a}</span>
            </div>
            <div className="matchup-vs">–</div>
            <div className="matchup-team-col">
              <span className="matchup-team-name">{teamB?.name ?? result.team_b_id}</span>
              <span className="matchup-team-score">{result.score_b}</span>
            </div>
          </div>
          <div className="matchup-rows">
            <div className="matchup-row matchup-row-header">
              <div className="matchup-cell matchup-team-a">Team A</div>
              <div className="matchup-cell matchup-slot">Slot</div>
              <div className="matchup-cell matchup-team-b">Team B</div>
            </div>
            {result.highlights.map((h) => (
              <div key={h.match_id} className="matchup-row-wrapper">
                <button
                  type="button"
                  className="matchup-row matchup-row-clickable"
                  onClick={() => goToMatchDetail(h.match_id)}
                >
                  <div className="matchup-cell matchup-team-a">
                    <span className="matchup-player-name">{h.player_a_name ?? h.player_a_id}</span>
                    <span className="matchup-points">{h.points_a} pts</span>
                  </div>
                  <div className="matchup-cell matchup-slot">{h.slot}</div>
                  <div className="matchup-cell matchup-team-b">
                    <span className="matchup-player-name">{h.player_b_name ?? h.player_b_id}</span>
                    <span className="matchup-points">{h.points_b} pts</span>
                  </div>
                </button>
                {h.role_log && h.role_log.length > 0 && (
                  <ul className="role-log-inline" aria-label="Role effects">
                    {h.role_log.map((entry, idx) => (
                      <li key={idx} className="role-log-entry">
                        {entry.description}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
          <p className="team-summary-meta" style={{ marginTop: '0.75rem' }}>
            Click a row to open Match Detail (AI summary, momentum graph, serve %, rally stats).
          </p>
        </div>
      )}
    </div>
  );
}
