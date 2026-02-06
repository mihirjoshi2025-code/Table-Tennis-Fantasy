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

export interface RosterSlot {
  player_id: string;
  slot: number;
  is_captain: boolean;
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
