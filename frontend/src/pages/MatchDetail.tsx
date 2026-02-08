import { useState, useEffect, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  ReferenceLine,
} from 'recharts';
import {
  getMatch,
  getMatchAnalysis,
  explainMatch,
  type MatchWithEvents,
  type MatchAnalysis,
  type ExplainResponse,
  type PointEventDict,
} from '../api';
import '../App.css';

function buildMomentumData(events: PointEventDict[], playerAId: string): { point: number; diff: number; scoreA: number; scoreB: number }[] {
  const out: { point: number; diff: number; scoreA: number; scoreB: number }[] = [];
  let scoreA = 0;
  let scoreB = 0;
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    const winner = e.outcome?.winner_id;
    if (winner === playerAId) scoreA += 1;
    else scoreB += 1;
    out.push({
      point: i + 1,
      diff: scoreA - scoreB,
      scoreA,
      scoreB,
    });
  }
  return out;
}

export default function MatchDetail() {
  const { matchId } = useParams<{ matchId: string }>();
  const [match, setMatch] = useState<MatchWithEvents | null>(null);
  const [analysis, setAnalysis] = useState<MatchAnalysis | null>(null);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!matchId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      getMatch(matchId),
      getMatchAnalysis(matchId),
    ])
      .then(([m, a]) => {
        setMatch(m);
        setAnalysis(a);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load match'))
      .finally(() => setLoading(false));
  }, [matchId]);

  useEffect(() => {
    if (!matchId || error) return;
    explainMatch(matchId)
      .then(setExplanation)
      .catch(() => setExplanation(null));
  }, [matchId, error]);

  const momentumData = useMemo(() => {
    if (!match?.events?.length || !analysis?.player_a_id) return [];
    return buildMomentumData(match.events, analysis.player_a_id);
  }, [match?.events, analysis?.player_a_id]);

  const serveChartData = useMemo(() => {
    if (!analysis) return [];
    const a = analysis.player_a_name ?? analysis.player_a_id;
    const b = analysis.player_b_name ?? analysis.player_b_id;
    return [
      { name: a, pct: analysis.serve_win_pct_a ?? 0 },
      { name: b, pct: analysis.serve_win_pct_b ?? 0 },
    ].filter((d) => d.pct > 0 || d.name);
  }, [analysis]);

  if (loading) {
    return (
      <div className="card">
        <p className="team-summary-meta">Loading match…</p>
      </div>
    );
  }

  if (error || !match || !analysis) {
    return (
      <div className="card">
        <h1>Match Detail</h1>
        <p className="error">{error ?? 'Match not found.'}</p>
        <Link to="/simulate" className="nav-link">← Back to Simulate Match</Link>
      </div>
    );
  }

  const nameA = match.player_a_name ?? match.player_a_id;
  const nameB = match.player_b_name ?? match.player_b_id;
  const durationMin = analysis.estimated_duration_seconds
    ? Math.round(analysis.estimated_duration_seconds / 60)
    : null;

  return (
    <div className="card">
      <div className="match-detail-header">
        <Link to="/simulate" className="nav-link" style={{ marginBottom: '0.5rem', display: 'inline-block' }}>
          ← Back to Simulate Match
        </Link>
        <h1>Match Detail</h1>
        <p className="team-summary-meta">
          {nameA} vs {nameB}
        </p>
        <p className="match-detail-score">
          {match.sets_a} – {match.sets_b} sets
          {analysis.total_points_played != null && ` · ${analysis.total_points_played} points`}
        </p>
      </div>

      {explanation?.explanation_text && (
        <section className="match-detail-section">
          <h3>AI Match Summary</h3>
          <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {explanation.explanation_text}
          </p>
          {explanation.supporting_facts?.length > 0 && (
            <ul className="team-summary-list" style={{ marginTop: '0.75rem' }}>
              {explanation.supporting_facts.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="match-detail-section">
        <h3>Statistics</h3>
        <div className="match-detail-stats-grid">
          {durationMin != null && (
            <div className="match-detail-stat-card">
              <div className="match-detail-stat-label">Match duration (est.)</div>
              <div className="match-detail-stat-value">{durationMin} min</div>
            </div>
          )}
          {analysis.longest_rally != null && (
            <div className="match-detail-stat-card">
              <div className="match-detail-stat-label">Longest rally</div>
              <div className="match-detail-stat-value">{analysis.longest_rally} shots</div>
            </div>
          )}
          {analysis.avg_rally_length != null && (
            <div className="match-detail-stat-card">
              <div className="match-detail-stat-label">Avg rally length</div>
              <div className="match-detail-stat-value">{analysis.avg_rally_length} shots</div>
            </div>
          )}
          {analysis.total_points_played != null && (
            <div className="match-detail-stat-card">
              <div className="match-detail-stat-label">Total points</div>
              <div className="match-detail-stat-value">{analysis.total_points_played}</div>
            </div>
          )}
        </div>
      </section>

      {momentumData.length > 0 && (
        <section className="match-detail-section">
          <h3>Momentum</h3>
          <p className="team-summary-meta" style={{ marginBottom: '0.75rem' }}>
            Score differential over time (positive = {nameA} ahead)
          </p>
          <div className="match-detail-chart-wrap">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={momentumData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="point" stroke="var(--text-secondary)" fontSize={11} />
                <YAxis stroke="var(--text-secondary)" fontSize={11} />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid rgba(255,255,255,0.1)' }}
                  labelStyle={{ color: 'var(--text-primary)' }}
                />
                <ReferenceLine y={0} stroke="var(--text-secondary)" strokeDasharray="2 2" />
                <Line
                  type="monotone"
                  dataKey="diff"
                  name="Score diff"
                  stroke="var(--accent-primary)"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {serveChartData.length > 0 && (
        <section className="match-detail-section">
          <h3>Serve performance</h3>
          <p className="team-summary-meta" style={{ marginBottom: '0.75rem' }}>
            % of points won on serve
          </p>
          <div className="match-detail-chart-wrap">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={serveChartData} layout="vertical" margin={{ top: 8, right: 24, left: 60, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis type="number" domain={[0, 100]} stroke="var(--text-secondary)" fontSize={11} />
                <YAxis type="category" dataKey="name" stroke="var(--text-secondary)" fontSize={11} width={56} />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-card)', border: '1px solid rgba(255,255,255,0.1)' }}
                  formatter={(value: number) => [`${value}%`, 'Points won on serve']}
                />
                <Bar dataKey="pct" name="%" radius={[0, 4, 4, 0]} fill="rgb(128,255,0)">
                  {serveChartData.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? 'rgb(128,255,0)' : 'rgb(255,178,0)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <p style={{ marginTop: '1rem' }}>
        <Link to="/simulate" className="nav-link">← Back to Simulate Match</Link>
      </p>
    </div>
  );
}
