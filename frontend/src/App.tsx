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
import { getAuth, clearAuth } from './api';
import './App.css';

function Nav() {
  const auth = getAuth();
  const navigate = useNavigate();
  return (
    <nav className="app-nav">
      <Link to="/">Home</Link>
      <Link to="/create-phase2">Create Team</Link>
      <Link to="/teams">View Team</Link>
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
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
