import { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Shell from './components/Layout/Shell';

// Lazy load pages for better performance
const Dashboard = lazy(() => import('./pages/Dashboard'));
const CaseExplorer = lazy(() => import('./pages/CaseExplorer'));
const OperatorLaunchGuide = lazy(() => import('./pages/OperatorLaunchGuide'));
const CaseIntelligenceCenter = lazy(() => import('./pages/CaseIntelligenceCenter'));
const PipelineMonitor = lazy(() => import('./pages/PipelineMonitor'));
const CorroborationNetwork = lazy(() => import('./pages/CorroborationNetwork'));
const SourceAnalysis = lazy(() => import('./pages/SourceAnalysis'));
const NarrativeLandscape = lazy(() => import('./pages/NarrativeLandscape'));
const MonitoringCenter = lazy(() => import('./pages/MonitoringCenter'));

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
        <Suspense fallback={<div className="shell-loading">Loading workspace...</div>}>
          <Routes>
            <Route path="/" element={<Shell />}>
              {/* Default redirect to dashboard */}
              <Route index element={<Navigate to="/dashboard" replace />} />

              {/* New Dashboard */}
              <Route path="dashboard" element={<Dashboard />} />

              {/* Case Explorer (redesigned) */}
              <Route path="cases" element={<CaseExplorer />} />

              {/* Operator Launch Guide */}
              <Route path="cases/new" element={<OperatorLaunchGuide />} />

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
        </Suspense>
      </Router>
    </QueryClientProvider>
  );
}

export default App;
