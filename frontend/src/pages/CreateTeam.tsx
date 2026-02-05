import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPlayers, createTeam, type Player } from '../api';
import '../App.css';

const MOCK_USER_ID = '1';
const MIN_PLAYERS = 1;
const MAX_PLAYERS = 10;

export default function CreateTeam() {
  const navigate = useNavigate();
  const [teamName, setTeamName] = useState('');
  const [gender, setGender] = useState<'men' | 'women'>('men');
  const [players, setPlayers] = useState<Player[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [loadingPlayers, setLoadingPlayers] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingPlayers(true);
    setError(null);
    getPlayers(gender, 50)
      .then(setPlayers)
      .catch((e) => setError(e.message))
      .finally(() => setLoadingPlayers(false));
    setSelectedIds(new Set());
  }, [gender]);

  const togglePlayer = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < MAX_PLAYERS) next.add(id);
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const ids = Array.from(selectedIds);
    if (ids.length < MIN_PLAYERS) {
      setError(`Select at least ${MIN_PLAYERS} player(s).`);
      return;
    }
    if (ids.length > MAX_PLAYERS) {
      setError(`Select at most ${MAX_PLAYERS} players.`);
      return;
    }
    if (!teamName.trim()) {
      setError('Enter a team name.');
      return;
    }
    setLoading(true);
    try {
      const team = await createTeam({
        user_id: MOCK_USER_ID,
        name: teamName.trim(),
        gender,
        player_ids: ids,
      });
      navigate(`/team/${team.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create team');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h1>Create Team</h1>
      <p className="team-summary-meta">
        Choose a name, gender, and up to {MAX_PLAYERS} players. Team is saved when you submit.
      </p>

      <form onSubmit={handleSubmit}>
        <div className="input-group">
          <label htmlFor="team-name">Team name</label>
          <input
            id="team-name"
            type="text"
            value={teamName}
            onChange={(e) => setTeamName(e.target.value)}
            placeholder="e.g. Champions"
            maxLength={200}
          />
        </div>

        <div className="input-group">
          <label htmlFor="gender">Gender</label>
          <select
            id="gender"
            value={gender}
            onChange={(e) => setGender(e.target.value as 'men' | 'women')}
          >
            <option value="men">Men</option>
            <option value="women">Women</option>
          </select>
        </div>

        <div className="input-group">
          <label>Players ({selectedIds.size} / {MAX_PLAYERS} selected)</label>
          {loadingPlayers ? (
            <p className="team-summary-meta">Loading players…</p>
          ) : (
            <ul className="player-list">
              {players.map((p) => (
                <li key={p.id}>
                  <input
                    type="checkbox"
                    id={`player-${p.id}`}
                    checked={selectedIds.has(p.id)}
                    onChange={() => togglePlayer(p.id)}
                    disabled={!selectedIds.has(p.id) && selectedIds.size >= MAX_PLAYERS}
                  />
                  <label htmlFor={`player-${p.id}`} className="player-info">
                    <span className="name">{p.name}</span>
                    <span className="meta"> {p.country} · Rank {p.rank}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p className="error">{error}</p>}

        <button
          type="submit"
          className="btn-primary"
          disabled={loading || loadingPlayers || selectedIds.size < MIN_PLAYERS || !teamName.trim()}
        >
          {loading ? 'Creating…' : 'Create Team'}
        </button>
      </form>
    </div>
  );
}
