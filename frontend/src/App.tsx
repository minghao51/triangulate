import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Shell from './components/Layout/Shell';
import CaseIndex from './pages/CaseIndex';
import NewInvestigation from './pages/NewInvestigation';
import CaseDetail from './pages/CaseDetail';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Shell />}>
          <Route index element={<CaseIndex />} />
          <Route path="cases/new" element={<NewInvestigation />} />
          <Route path="cases/:id/*" element={<CaseDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
