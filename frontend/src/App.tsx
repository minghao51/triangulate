import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Shell from './components/Layout/Shell';

// Lazy load pages for better performance
import Dashboard from './pages/Dashboard';
import CaseExplorer from './pages/CaseExplorer';
import InvestigationComposer from './pages/InvestigationComposer';
import CaseIntelligenceCenter from './pages/CaseIntelligenceCenter';
import PipelineMonitor from './pages/PipelineMonitor';
import CorroborationNetwork from './pages/CorroborationNetwork';
import SourceAnalysis from './pages/SourceAnalysis';
import NarrativeLandscape from './pages/NarrativeLandscape';
import MonitoringCenter from './pages/MonitoringCenter';

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Routes>
          <Route path="/" element={<Shell />}>
            {/* Default redirect to dashboard */}
            <Route index element={<Navigate to="/dashboard" replace />} />

            {/* New Dashboard */}
            <Route path="dashboard" element={<Dashboard />} />

            {/* Case Explorer (redesigned) */}
            <Route path="cases" element={<CaseExplorer />} />

            {/* Investigation Composer (redesigned) */}
            <Route path="cases/new" element={<InvestigationComposer />} />

            {/* Case Intelligence Center (redesigned) */}
            <Route path="cases/:id/*" element={<CaseIntelligenceCenter />} />

            {/* Pipeline Monitor */}
            <Route path="cases/:id/pipeline" element={<PipelineMonitor />} />

            {/* Corroboration Network */}
            <Route path="cases/:id/network" element={<CorroborationNetwork />} />

            {/* Source Analysis */}
            <Route path="cases/:id/sources" element={<SourceAnalysis />} />

            {/* Narrative Landscape */}
            <Route path="cases/:id/narratives" element={<NarrativeLandscape />} />

            {/* Monitoring Center */}
            <Route path="monitoring" element={<MonitoringCenter />} />

            {/* Catch all - redirect to dashboard */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </Router>
    </QueryClientProvider>
  );
}

export default App;
