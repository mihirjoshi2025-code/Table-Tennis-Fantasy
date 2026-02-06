/**
 * Centralized API client for Table Tennis Fantasy backend.
 * All HTTP calls to the backend go through this module.
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

export interface Player {
  id: string;
  name: string;
  country: string;
  gender: string;
  rank: number;
  points: number;
}

export interface TeamPlayer {
  id: string;
  name?: string;
  country?: string;
}

export interface Team {
  id: string;
  user_id: string;
  name: string;
  gender: string;
  players?: TeamPlayer[];
  player_ids?: string[];
  created_at: string;
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
  user_id: string;
  name: string;
  gender: 'men' | 'women';
  player_ids: string[];
}): Promise<Team> {
  const res = await fetch(`${API_BASE}/teams`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.text();
    let message: string;
    try {
      const parsed = JSON.parse(body);
      message = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail ?? body);
    } catch {
      message = body || `Request failed with status ${res.status}`;
    }
    throw new Error(message);
  }
  return res.json();
}

export async function getTeam(teamId: string): Promise<Team> {
  const res = await fetch(`${API_BASE}/teams/${teamId}`);
  if (!res.ok) {
    if (res.status === 404) throw new Error('Team not found');
    throw new Error(await res.text());
  }
  return res.json();
}
