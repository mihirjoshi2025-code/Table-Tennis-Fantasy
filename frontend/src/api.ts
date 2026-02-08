/**
 * Centralized API client for Table Tennis Fantasy backend.
 * All HTTP calls to the backend go through this module.
 * Phase 2: auth token stored in localStorage; requests send Authorization when logged in.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

const AUTH_KEY = 'ttf_auth';

export interface AuthInfo {
  user_id: string;
  username: string;
  token: string;
}

export function getToken(): string | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as AuthInfo;
    return data.token ?? null;
  } catch {
    return null;
  }
}

export function getAuth(): AuthInfo | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthInfo;
  } catch {
    return null;
  }
}

export function setAuth(auth: AuthInfo): void {
  localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
}

export function clearAuth(): void {
  localStorage.removeItem(AUTH_KEY);
}

export function getUserId(): string | null {
  return getAuth()?.user_id ?? null;
}

async function apiRequest<T>(
  path: string,
  options: RequestInit & { skipAuth?: boolean } = {}
): Promise<T> {
  const { skipAuth, ...init } = options;
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  const isGet = (init.method ?? 'GET').toUpperCase() === 'GET';
  if (!isGet && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  if (!skipAuth) {
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  const text = await res.text();
  if (!res.ok) {
    let message: string;
    try {
      const parsed = JSON.parse(text);
      message = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail ?? text);
    } catch {
      message = text || `Request failed with status ${res.status}`;
    }
    throw new Error(message);
  }
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export interface Player {
  id: string;
  name: string;
  country: string;
  gender: string;
  rank: number;
  points: number;
  salary?: number;
}

export interface TeamPlayer {
  id: string;
  name?: string;
  country?: string;
}

export interface RoleDefinition {
  id: string;
  name: string;
  description: string;
  modifier_summary: string;
}

export interface RosterSlot {
  player_id: string;
  slot: number;
  is_captain: boolean;
  /** One of: anchor, aggressor, closer, wildcard, stabilizer. Only for slots 1-7; at most one per role per team. */
  role?: string | null;
  /** Fantasy points from player's most recent match; null if none. */
  last_match_points?: number | null;
}

export interface Team {
  id: string;
  user_id: string;
  name: string;
  gender: string;
  budget?: number;
  roster?: RosterSlot[];
  players?: TeamPlayer[];
  player_ids?: string[];
  created_at: string;
}

export interface TeamListItem {
  id: string;
  user_id: string;
  name: string;
  gender: string;
  budget?: number;
  created_at: string;
}

export async function signup(username: string, password: string): Promise<AuthInfo> {
  const data = await apiRequest<AuthInfo>('/signup', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
    skipAuth: true,
  });
  setAuth(data);
  return data;
}

export async function login(username: string, password: string): Promise<AuthInfo> {
  const data = await apiRequest<AuthInfo>('/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
    skipAuth: true,
  });
  setAuth(data);
  return data;
}

export async function getPlayers(
  gender?: 'men' | 'women',
  limit = 50,
  signal?: AbortSignal
): Promise<Player[]> {
  const params = new URLSearchParams();
  if (gender) params.set('gender', gender);
  params.set('limit', String(limit));
  const res = await fetch(`${API_BASE}/players?${params}`, { signal });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.players;
}

export async function createTeam(payload: {
  user_id?: string;
  name: string;
  gender: 'men' | 'women';
  player_ids?: string[];
  budget?: number;
  roster?: RosterSlot[];
}): Promise<Team> {
  const body = payload.roster
    ? {
        name: payload.name,
        gender: payload.gender,
        budget: payload.budget!,
        roster: payload.roster,
        ...(payload.user_id ? { user_id: payload.user_id } : {}),
      }
    : {
        user_id: payload.user_id!,
        name: payload.name,
        gender: payload.gender,
        player_ids: payload.player_ids!,
      };
  return apiRequest<Team>('/teams', { method: 'POST', body: JSON.stringify(body) });
}

export async function getTeam(teamId: string): Promise<Team> {
  return apiRequest<Team>(`/teams/${teamId}`);
}

export async function listRoles(): Promise<RoleDefinition[]> {
  const data = await apiRequest<{ roles: RoleDefinition[] }>('/roles');
  return data.roles;
}

export interface RoleRecommendation {
  player_id: string;
  player_name: string;
  suggested_role: string;
  why_fit: string;
  risk: string;
}

export interface RoleAdvisorResponse {
  recommendations: RoleRecommendation[];
  explanation: string;
  tradeoffs?: string | null;
}

export async function adviseRoles(params: {
  query: string;
  team_id?: string | null;
  gender?: 'men' | 'women' | null;
}): Promise<RoleAdvisorResponse> {
  const body: Record<string, string> = { query: params.query };
  if (params.team_id) body.team_id = params.team_id;
  if (params.gender) body.gender = params.gender;
  return apiRequest<RoleAdvisorResponse>('/advise/roles', { method: 'POST', body: JSON.stringify(body) });
}

export async function listTeams(
  userId: string,
  gender?: 'men' | 'women'
): Promise<TeamListItem[]> {
  let path = `/teams?user_id=${encodeURIComponent(userId)}`;
  if (gender) path += `&gender=${encodeURIComponent(gender)}`;
  const data = await apiRequest<{ teams: TeamListItem[] }>(path);
  return data.teams;
}

export interface TeamMatchResult {
  id: string;
  team_a_id: string;
  team_b_id: string;
  score_a: number;
  score_b: number;
  captain_a_id: string | null;
  captain_b_id: string | null;
  match_ids: string[];
  highlights: Array<{
    slot: number;
    player_a_id: string;
    player_b_id: string;
    player_a_name?: string;
    player_b_name?: string;
    points_a: number;
    points_b: number;
    winner_id: string;
    match_id: string;
    /** Role-triggered effects for this slot (e.g. "Aggressor bonus applied"). */
    role_log?: Array<{ player_id: string; role: string; game_slot: number; description: string; raw_score: number; adjusted_score: number }>;
  }>;
  created_at: string;
}

export interface PointEventDict {
  match_id: string;
  point_index: number;
  set_index: number;
  game_index: number;
  score_before: number[];
  score_after: number[];
  set_scores_before: number[];
  set_scores_after: number[];
  server_id: string;
  outcome: { winner_id: string; loser_id: string; shot_type: string };
  rally_length: number;
  rally_category: string;
  streak_continuing?: string | null;
  streak_broken?: boolean;
  comeback_threshold?: boolean;
  deciding_set_point?: boolean;
}

export interface MatchWithEvents {
  id: string;
  team_a_id: string;
  team_b_id: string;
  player_a_id: string;
  player_b_id: string;
  player_a_name?: string;
  player_b_name?: string;
  winner_id: string;
  sets_a: number;
  sets_b: number;
  best_of: number;
  seed: number;
  created_at: string;
  events?: PointEventDict[];
}

export interface MatchAnalysis {
  match_id: string;
  outcome: { winner_id: string; sets_a: number; sets_b: number; best_of: number };
  player_a_id: string;
  player_b_id: string;
  player_a_name?: string;
  player_b_name?: string;
  player_a_stats: Record<string, unknown> | null;
  player_b_stats: Record<string, unknown> | null;
  fantasy_scores: Record<string, number>;
  total_points_played: number;
  longest_rally?: number;
  avg_rally_length?: number;
  serve_win_pct_a?: number | null;
  serve_win_pct_b?: number | null;
  estimated_duration_seconds?: number;
}

export async function getMatch(matchId: string): Promise<MatchWithEvents> {
  return apiRequest<MatchWithEvents>(`/matches/${matchId}`);
}

export async function getMatchAnalysis(matchId: string): Promise<MatchAnalysis> {
  return apiRequest<MatchAnalysis>(`/analysis/match/${matchId}`);
}

export async function simulateTeamMatch(params: {
  team_a_id: string;
  team_b_id: string;
  seed?: number;
  best_of?: number;
}): Promise<TeamMatchResult> {
  return apiRequest<TeamMatchResult>('/simulate/team-match', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export interface ExplainResponse {
  explanation_text: string;
  supporting_facts: string[];
}

export async function explainMatch(matchId: string, userQuery?: string): Promise<ExplainResponse> {
  return apiRequest<ExplainResponse>('/explain/match', {
    method: 'POST',
    body: JSON.stringify({ match_id: matchId, user_query: userQuery ?? undefined }),
  });
}

// ---------- Leagues (Step 3) ----------

export interface League {
  id: string;
  name: string;
  creator_user_id?: string;
  owner_id: string;
  status: string;
  max_teams: number;
  created_at: string;
  started_at?: string | null;
}

export interface LeagueDetail extends League {
  members?: Array<{ user_id: string; team_id: string; team_name?: string | null; joined_at: string }>;
  current_week?: number;
  total_weeks?: number;
  started_at?: string | null;
  current_week_matches?: Array<{
    id: string;
    home_team_id: string;
    away_team_id: string | null;
    status: string;
    home_score: number;
    away_score: number;
  }>;
  /** Full schedule: all weeks and matches. Present when league has been started. */
  schedule?: Array<{
    week_number: number;
    week_id: string;
    matches: Array<{
      id: string;
      home_team_id: string;
      away_team_id: string | null;
      status: string;
      home_score: number;
      away_score: number;
    }>;
  }>;
}

export interface LeagueStanding {
  team_id: string;
  wins: number;
  losses: number;
  draws: number;
  points_for: number;
  points_against: number;
  differential: number;
}

/** When mine is true and user is logged in, returns only leagues the user owns or has joined. */
export async function listLeagues(mine?: boolean): Promise<League[]> {
  const url = mine ? '/leagues?mine=true' : '/leagues';
  const data = await apiRequest<{ leagues: League[] }>(url);
  return data.leagues;
}

export async function createLeague(name: string, max_teams: number): Promise<League> {
  return apiRequest<League>('/leagues', {
    method: 'POST',
    body: JSON.stringify({ name, max_teams }),
  });
}

export async function getLeague(leagueId: string): Promise<LeagueDetail> {
  return apiRequest<LeagueDetail>(`/leagues/${leagueId}`);
}

export async function joinLeague(leagueId: string, teamId: string): Promise<{ joined: boolean }> {
  return apiRequest<{ joined: boolean }>(`/leagues/${leagueId}/join`, {
    method: 'POST',
    body: JSON.stringify({ team_id: teamId }),
  });
}

export async function startLeague(leagueId: string): Promise<{ started: boolean }> {
  return apiRequest<{ started: boolean }>(`/leagues/${leagueId}/start`, {
    method: 'POST',
  });
}

export async function fastForwardWeek(leagueId: string, seed?: number): Promise<{
  advanced: boolean;
  current_week?: number;
  total_weeks?: number;
  league_completed?: boolean;
}> {
  return apiRequest(`/leagues/${leagueId}/fast-forward-week`, {
    method: 'POST',
    body: JSON.stringify(seed != null ? { seed } : {}),
  });
}

export async function getLeagueStandings(leagueId: string): Promise<LeagueStanding[]> {
  const data = await apiRequest<{ standings: LeagueStanding[] }>(`/leagues/${leagueId}/standings`);
  return data.standings;
}

// ---------- League matches (Step 4: live + fast-forward) ----------

export interface LeagueMatch {
  id: string;
  week_id: string;
  home_team_id: string;
  away_team_id: string | null;
  home_team_name?: string;
  away_team_name?: string;
  home_score: number;
  away_score: number;
  status: string;
  simulation_log?: string | null;
  created_at: string | null;
  live?: {
    elapsed_seconds: number;
    home_score: number;
    away_score: number;
    highlights: Array<Record<string, unknown>>;
    done: boolean;
    /** Per-game state (7 slots). Bootstraped when match goes live for late join. */
    games?: Array<{
      slot: number;
      home_player_id: string;
      away_player_id: string;
      home_player_name: string;
      away_player_name: string;
      score_home: number;
      score_away: number;
      status: string;
    }>;
  };
}

export async function getLeagueMatch(matchId: string): Promise<LeagueMatch> {
  return apiRequest<LeagueMatch>(`/league-matches/${matchId}`);
}

export async function startLiveLeagueMatch(matchId: string, seed?: number): Promise<{ started: boolean }> {
  return apiRequest(`/league-matches/${matchId}/start-live`, {
    method: 'POST',
    body: JSON.stringify(seed != null ? { seed } : {}),
  });
}

export async function fastForwardLeagueMatch(matchId: string, seed?: number): Promise<{
  status: string;
  home_score: number;
  away_score: number;
  highlights?: Array<Record<string, unknown>>;
}> {
  return apiRequest(`/league-matches/${matchId}/fast-forward`, {
    method: 'POST',
    body: JSON.stringify(seed != null ? { seed } : {}),
  });
}

/** Reset a league match to scheduled (for testing). Lets you rerun live or fast-forward. */
export async function restartLeagueMatch(matchId: string): Promise<{ status: string; restarted: boolean }> {
  return apiRequest(`/league-matches/${matchId}/restart`, { method: 'POST' });
}

/** WebSocket URL for live league match updates (ws or wss from current origin). */
export function leagueMatchWebSocketUrl(matchId: string): string {
  const base = API_BASE.replace(/^http/, 'ws');
  return `${base}/ws/league-match/${matchId}`;
}

/** Total momentum: time_seconds vs cumul_tt_home, cumul_tt_away (table tennis points). */
export interface TotalMomentumPoint {
  time_seconds: number;
  cumul_tt_home: number;
  cumul_tt_away: number;
}

/** Completed league match can include slot_data and total_momentum. */
export interface LeagueMatchWithSlots extends LeagueMatch {
  slot_data?: Array<Record<string, unknown>>;
  total_momentum?: TotalMomentumPoint[];
}

/** One game (slot) data: TT momentum series, stats, player names. */
export interface LeagueMatchGame {
  match_id: string;
  slot: number;
  home_team_name: string;
  away_team_name: string;
  home_player_id: string;
  away_player_id: string;
  home_player_name: string;
  away_player_name: string;
  momentum_series: Array<{ point_index: number; time_seconds: number; cumul_tt_a: number; cumul_tt_b: number }>;
  total_points: number;
  longest_rally?: number;
  avg_rally_length?: number;
  serve_win_pct_a?: number;
  serve_win_pct_b?: number;
  player_a_stats?: Record<string, unknown>;
  player_b_stats?: Record<string, unknown>;
  winner_id?: string;
}

export async function getLeagueMatchGame(matchId: string, slot: number): Promise<LeagueMatchGame> {
  return apiRequest<LeagueMatchGame>(`/league-matches/${matchId}/games/${slot}`);
}

export interface ExplainResponse {
  explanation_text: string;
  supporting_facts: string[];
}

export async function explainLeagueMatchGame(leagueMatchId: string, slot: number): Promise<ExplainResponse> {
  return apiRequest<ExplainResponse>('/explain/league-match-game', {
    method: 'POST',
    body: JSON.stringify({ league_match_id: leagueMatchId, slot }),
  });
}
