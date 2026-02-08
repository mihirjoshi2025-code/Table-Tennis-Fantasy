import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { getPlayers, createTeam, getAuth, listRoles, type Player, type RosterSlot, type RoleDefinition } from '../api';
import RoleAdvisorBubble from '../components/RoleAdvisorBubble';
import '../App.css';

const TEAM_ACTIVE = 7;
const TEAM_TOTAL = 10;

export default function CreateTeamPhase2() {
  const navigate = useNavigate();
  const auth = getAuth();
  const [teamName, setTeamName] = useState('');
  const [gender, setGender] = useState<'men' | 'women'>('men');
  const [budget, setBudget] = useState<number>(950);
  const [players, setPlayers] = useState<Player[]>([]);
  const [roles, setRoles] = useState<RoleDefinition[]>([]);
  const [roster, setRoster] = useState<(string | null)[]>(Array(TEAM_TOTAL).fill(null));
  const [rosterRoles, setRosterRoles] = useState<(string | null)[]>(Array(TEAM_ACTIVE).fill(null));
  const [captainSlot, setCaptainSlot] = useState<number>(1);
  const [loading, setLoading] = useState(false);
  const [loadingPlayers, setLoadingPlayers] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    listRoles().then(setRoles).catch(() => {});
  }, []);

  useEffect(() => {
    abortRef.current?.abort();
    const c = new AbortController();
    abortRef.current = c;
    setLoadingPlayers(true);
    setError(null);
    setRoster(Array(TEAM_TOTAL).fill(null));
    getPlayers(gender, 50, c.signal)
      .then((list) => {
        if (!c.signal.aborted) setPlayers(list);
      })
      .catch((e) => {
        if (!c.signal.aborted && e.name !== 'AbortError') setError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setLoadingPlayers(false);
      });
    return () => {
      c.abort();
      abortRef.current = null;
    };
  }, [gender]);

  const assignedIds = new Set(roster.filter(Boolean) as string[]);
  const totalSalary = roster.reduce(
    (sum, pid) => sum + (pid ? (players.find((p) => p.id === pid)?.salary ?? 0) : 0),
    0
  );
  const isValid =
    teamName.trim() &&
    roster.every(Boolean) &&
    totalSalary <= budget &&
    captainSlot >= 1 &&
    captainSlot <= TEAM_ACTIVE;

  const setSlot = (index: number, playerId: string | null) => {
    setRoster((prev) => {
      const next = [...prev];
      next[index] = playerId;
      return next;
    });
  };

  const setSlotRole = (index: number, roleId: string | null) => {
    if (index < 0 || index >= TEAM_ACTIVE) return;
    setRosterRoles((prev) => {
      const next = [...prev];
      next[index] = roleId || null;
      return next;
    });
  };

  const rolesUsed = new Set(rosterRoles.filter(Boolean) as string[]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!auth) {
      setError('You must be logged in to create a team.');
      return;
    }
    if (!isValid) return;
    setError(null);
    setLoading(true);
    try {
      const rosterPayload: RosterSlot[] = roster.map((player_id, i) => ({
        player_id: player_id!,
        slot: i + 1,
        is_captain: i + 1 === captainSlot,
        role: i < TEAM_ACTIVE ? rosterRoles[i] ?? undefined : undefined,
      }));
      const team = await createTeam({
        name: teamName.trim(),
        gender,
        budget,
        roster: rosterPayload,
      });
      navigate(`/team/${team.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create team');
    } finally {
      setLoading(false);
    }
  };

  if (!auth) {
    return (
      <div className="card">
        <h1>Create Team</h1>
        <p className="error">You must log in to create a team. Use the link below to sign in or sign up.</p>
        <Link to="/login" className="nav-link">Log in</Link>
        <Link to="/signup" className="nav-link">Sign up</Link>
      </div>
    );
  }

  return (
    <>
    <div className="card">
      <h1>Create Team (Phase 2)</h1>
      <p className="team-summary-meta">
        Budget: ${budget}. Pick 10 players: slots 1–7 active (one captain), slots 8–10 bench. Total salary cannot exceed budget.
      </p>
      {roles.length > 0 && (
        <div className="roles-description-block" aria-label="Player roles">
          <h2 className="roles-description-title">Player roles (optional)</h2>
          <p className="team-summary-meta" style={{ marginBottom: '0.75rem' }}>
            Assign at most one role per active slot (1–7). Each role can be used only once per team.
          </p>
          <ul className="roles-description-list">
            {roles.map((r) => (
              <li key={r.id}>
                <strong>{r.name}</strong>: {r.description}
              </li>
            ))}
          </ul>
        </div>
      )}
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
          <select id="gender" value={gender} onChange={(e) => setGender(e.target.value as 'men' | 'women')}>
            <option value="men">Men</option>
            <option value="women">Women</option>
          </select>
        </div>
        <div className="input-group">
          <label htmlFor="budget">Budget</label>
          <input
            id="budget"
            type="number"
            min={1}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value) || 0)}
          />
        </div>
        <div className="input-group">
          <span className="team-summary-meta">
            Total salary: ${totalSalary} {totalSalary > budget && '(over budget)'}
          </span>
        </div>
        {loadingPlayers ? (
          <p className="team-summary-meta">Loading players…</p>
        ) : (
          <div className="roster-slots">
            {Array.from({ length: TEAM_TOTAL }, (_, i) => (
              <div key={i} className="roster-slot-row">
                <div className="roster-slot-main">
                  <label>
                    Slot {i + 1} {i < TEAM_ACTIVE ? '(Active)' : '(Bench)'}
                  </label>
                  <select
                    value={roster[i] ?? ''}
                    onChange={(e) => setSlot(i, e.target.value || null)}
                  >
                    <option value="">— Select player —</option>
                    {players.map((p) => (
                      <option
                        key={p.id}
                        value={p.id}
                        disabled={assignedIds.has(p.id) && roster[i] !== p.id}
                      >
                        {p.name} · {p.country} · Rank {p.rank} · ${p.salary ?? 100}
                      </option>
                    ))}
                  </select>
                </div>
                {i < TEAM_ACTIVE && (
                  <div className="roster-slot-active-options">
                    <label className="captain-check">
                      <input
                        type="radio"
                        name="captain"
                        checked={captainSlot === i + 1}
                        onChange={() => setCaptainSlot(i + 1)}
                      />
                      Captain
                    </label>
                    <div className="role-select">
                      <label htmlFor={`role-${i}`}>Role</label>
                      <select
                        id={`role-${i}`}
                        value={rosterRoles[i] ?? ''}
                        onChange={(e) => setSlotRole(i, e.target.value || null)}
                        title={roles.find((r) => r.id === rosterRoles[i])?.description}
                      >
                        <option value="">— None —</option>
                        {roles.map((r) => (
                          <option
                            key={r.id}
                            value={r.id}
                            disabled={rolesUsed.has(r.id) && rosterRoles[i] !== r.id}
                            title={r.description}
                          >
                            {r.name}
                          </option>
                        ))}
                      </select>
                      {rosterRoles[i] && (
                        <span className="role-summary" title={roles.find((r) => r.id === rosterRoles[i])?.description}>
                          {roles.find((r) => r.id === rosterRoles[i])?.modifier_summary}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {error && <p className="error">{error}</p>}
        <button
          type="submit"
          className="btn-primary"
          disabled={loading || loadingPlayers || !isValid}
        >
          {loading ? 'Creating…' : 'Create Team'}
        </button>
      </form>
    </div>
    <RoleAdvisorBubble gender={gender} />
    </>
  );
}
