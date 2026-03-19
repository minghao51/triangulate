import { Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Shell from './components/Layout/Shell';
import { appRoutes } from './app/routes';

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

              {appRoutes.map((route) => (
                <Route key={route.path} path={route.path} element={route.element} />
              ))}

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
