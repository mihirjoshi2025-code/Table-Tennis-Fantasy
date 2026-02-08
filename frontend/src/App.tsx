import { useState, useRef, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router-dom';
import Home from './pages/Home';
import CreateTeam from './pages/CreateTeam';
import CreateTeamPhase2 from './pages/CreateTeamPhase2';
import TeamSummary from './pages/TeamSummary';
import Login from './pages/Login';
import Signup from './pages/Signup';
import SimulateMatch from './pages/SimulateMatch';
import MatchDetail from './pages/MatchDetail';
import MyTeams from './pages/MyTeams';
import Leagues from './pages/Leagues';
import LeagueMatchLive from './pages/LeagueMatchLive';
import LeagueMatchLiveDetail from './pages/LeagueMatchLiveDetail';
import LeagueMatchSummary from './pages/LeagueMatchSummary';
import LeagueMatchGamePage from './pages/LeagueMatchGamePage';
import { getAuth, clearAuth } from './api';
import './App.css';

function Nav() {
  const auth = getAuth();
  const navigate = useNavigate();
  const [leaguesOpen, setLeaguesOpen] = useState(false);
  const leaguesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (leaguesRef.current && !leaguesRef.current.contains(e.target as Node)) {
        setLeaguesOpen(false);
      }
    };
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, []);

  return (
    <nav className="app-nav">
      <Link to="/">Home</Link>
      <Link to="/create-phase2">Create Team</Link>
      <Link to="/teams">View Team</Link>
      <div className="nav-dropdown" ref={leaguesRef}>
        <button
          type="button"
          className="nav-dropdown-toggle"
          onClick={() => setLeaguesOpen((o) => !o)}
          aria-expanded={leaguesOpen}
          aria-haspopup="true"
        >
          Leagues ▾
        </button>
        {leaguesOpen && (
          <div className="nav-dropdown-menu">
            <Link to="/leagues#create" onClick={() => setLeaguesOpen(false)}>Create League</Link>
            <Link to="/leagues#join" onClick={() => setLeaguesOpen(false)}>Join League</Link>
            <Link to="/leagues" onClick={() => setLeaguesOpen(false)}>My Leagues</Link>
          </div>
        )}
      </div>
      <Link to="/simulate">Simulate Match</Link>
      {auth ? (
        <>
          <span className="nav-user">{auth.username}</span>
          <button
            type="button"
            className="btn-secondary"
            style={{ padding: '0.35rem 0.75rem', fontSize: '0.9rem' }}
            onClick={() => {
              clearAuth();
              navigate('/');
            }}
          >
            Log out
          </button>
        </>
      ) : (
        <>
          <Link to="/login">Log in</Link>
          <Link to="/signup">Sign up</Link>
        </>
      )}
    </nav>
  );
}

function App() {
  return (
    <div className="app">
      <BrowserRouter>
        <Nav />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/create" element={<CreateTeam />} />
          <Route path="/create-phase2" element={<CreateTeamPhase2 />} />
          <Route path="/teams" element={<MyTeams />} />
          <Route path="/team/:teamId" element={<TeamSummary />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/simulate" element={<SimulateMatch />} />
          <Route path="/match/:matchId" element={<MatchDetail />} />
          <Route path="/leagues" element={<Leagues />} />
          <Route path="/leagues/:leagueId" element={<Leagues />} />
          <Route path="/league-match/:matchId" element={<LeagueMatchLive />} />
          <Route path="/league-match/:matchId/live" element={<LeagueMatchLiveDetail />} />
          <Route path="/league-match/:matchId/summary" element={<LeagueMatchSummary />} />
          <Route path="/league-match/:matchId/live/game/:slot" element={<LeagueMatchGamePage />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
