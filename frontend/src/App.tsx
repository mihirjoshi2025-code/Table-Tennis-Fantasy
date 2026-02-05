import { BrowserRouter, Routes, Route } from 'react-router-dom';
import CreateTeam from './pages/CreateTeam';
import TeamSummary from './pages/TeamSummary';
import './App.css';

function App() {
  return (
    <div className="app">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<CreateTeam />} />
          <Route path="/team/:teamId" element={<TeamSummary />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
