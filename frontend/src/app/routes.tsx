import { lazy } from 'react';

const Dashboard = lazy(() => import('../pages/Dashboard'));
const CaseExplorer = lazy(() => import('../pages/CaseExplorer'));
const OperatorLaunchGuide = lazy(() => import('../pages/OperatorLaunchGuide'));
const CaseIntelligenceCenter = lazy(() => import('../pages/CaseIntelligenceCenter'));
const PipelineMonitor = lazy(() => import('../pages/PipelineMonitor'));
const CorroborationNetwork = lazy(() => import('../pages/CorroborationNetwork'));
const SourceAnalysis = lazy(() => import('../pages/SourceAnalysis'));
const NarrativeLandscape = lazy(() => import('../pages/NarrativeLandscape'));
const MonitoringCenter = lazy(() => import('../pages/MonitoringCenter'));

// Top-level pages live in this registry so new routes default to lazy loading.
export const appRoutes = [
  { path: 'dashboard', element: <Dashboard /> },
  { path: 'cases', element: <CaseExplorer /> },
  { path: 'cases/new', element: <OperatorLaunchGuide /> },
  { path: 'cases/:id/*', element: <CaseIntelligenceCenter /> },
  { path: 'cases/:id/pipeline', element: <PipelineMonitor /> },
  { path: 'cases/:id/network', element: <CorroborationNetwork /> },
  { path: 'cases/:id/sources', element: <SourceAnalysis /> },
  { path: 'cases/:id/narratives', element: <NarrativeLandscape /> },
  { path: 'monitoring', element: <MonitoringCenter /> },
] as const;
