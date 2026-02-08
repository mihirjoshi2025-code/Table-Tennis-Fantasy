import { Link } from 'react-router-dom';
import '../App.css';

const HERO_IMAGE = '/hero.png';
const SECOND_IMAGE =
  'https://images.unsplash.com/photo-1609710228159-0fa9bd7c0827?w=800&q=80';

export default function Home() {
  return (
    <main className="home">
      <section className="home-hero">
        <div className="home-hero-content">
          <img
            src={HERO_IMAGE}
            alt="Table Tennis Fantasy hero"
            className="home-hero-image"
          />
          <h1 className="home-hero-title">
            <span className="home-hero-title-inner">Table Tennis Fantasy</span>
          </h1>
        </div>
      </section>

      <section className="home-section">
        <h2>What is this?</h2>
        <p>
          Table Tennis Fantasy lets you draft a fantasy team from real ITTF-style rankings,
          set a budget and pick 7 active players plus 3 bench, choose a captain for bonus scoring,
          and run head-to-head team matches. Each match is simulated point-by-point with
          deterministic replay, so you can analyze outcomes and compare with AI explanations.
        </p>
      </section>

      <section className="home-section home-section-split">
        <div className="home-section-text">
          <h2>Simulate & Analyze</h2>
          <p>
            Run 7v7 team matches with configurable seeds. View scores, highlights per slot,
            and captain bonuses. Every simulated match is stored so you can revisit results
            and dig into the numbers.
          </p>
          <Link to="/simulate" className="home-link">
            Go to Simulate Match →
          </Link>
        </div>
        <div className="home-section-media">
          <img src={SECOND_IMAGE} alt="Table tennis equipment" />
        </div>
      </section>

      <section className="home-section home-llm">
        <h2>LLM-Integrated Explanations</h2>
        <p>
          After a match, use <strong>Explain Match</strong> to get natural-language summaries
          powered by an agentic RAG pipeline. The system retrieves match analytics, player
          context, and rules, then grounds an LLM response in that data—so explanations
          reference actual stats and events, not guesswork. Works with or without an
          API key (stub mode when unset).
        </p>
      </section>

      <section className="home-section home-actions">
        <h2>Get Started</h2>
        <div className="home-action-cards">
          <Link to="/create-phase2" className="home-action-card">
            <span className="home-action-label">Create Team</span>
            <span className="home-action-desc">Draft 10 players, set captain, stay under budget</span>
          </Link>
          <Link to="/leagues" className="home-action-card">
            <span className="home-action-label">Leagues</span>
            <span className="home-action-desc">Create or join a league, compete over weeks</span>
          </Link>
          <Link to="/simulate" className="home-action-card">
            <span className="home-action-label">Simulate Match</span>
            <span className="home-action-desc">Run a team vs team match and see results</span>
          </Link>
        </div>
      </section>
    </main>
  );
}
