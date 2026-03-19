import { create } from 'zustand';

interface LogEntry {
  id: string;
  timestamp: string;
  level: 'info' | 'warning' | 'error' | 'debug';
  source: string;
  message: string;
  metadata?: Record<string, unknown>;
}

interface Monitor {
  id: string;
  name: string;
  query: string;
  schedule: string;
  active: boolean;
  lastRun?: string;
  nextRun?: string;
  status: 'running' | 'idle' | 'error';
  triggerCount: number;
}

interface MonitoringState {
  // Monitors
  monitors: Monitor[];
  setMonitors: (monitors: Monitor[]) => void;
  addMonitor: (monitor: Monitor) => void;
  updateMonitor: (id: string, updates: Partial<Monitor>) => void;
  removeMonitor: (id: string) => void;

  // Logs
  logs: LogEntry[];
  addLog: (log: Omit<LogEntry, 'id'>) => void;
  clearLogs: () => void;
  logsFilter: 'all' | 'info' | 'warning' | 'error' | 'debug';
  setLogsFilter: (filter: MonitoringState['logsFilter']) => void;

  // System health
  systemHealth: {
    cpu: number;
    memory: number;
    disk: number;
    uptime: number;
  };
  setSystemHealth: (health: MonitoringState['systemHealth']) => void;

  // Alerts
  alerts: Array<{
    id: string;
    severity: 'high' | 'medium' | 'low';
    message: string;
    timestamp: string;
    acknowledged: boolean;
  }>;
  addAlert: (alert: Omit<MonitoringState['alerts'][0], 'id' | 'timestamp' | 'acknowledged'>) => void;
  acknowledgeAlert: (id: string) => void;
}

export const useMonitoringStore = create<MonitoringState>((set) => ({
  // Initial state
  monitors: [],
  logs: [],
  logsFilter: 'all',
  systemHealth: {
    cpu: 0,
    memory: 0,
    disk: 0,
    uptime: 0,
  },
  alerts: [],

  // Monitor actions
  setMonitors: (monitors) => set({ monitors }),
  addMonitor: (monitor) =>
    set((state) => ({ monitors: [...state.monitors, monitor] })),
  updateMonitor: (id, updates) =>
    set((state) => ({
      monitors: state.monitors.map((m) =>
        m.id === id ? { ...m, ...updates } : m
      ),
    })),
  removeMonitor: (id) =>
    set((state) => ({
      monitors: state.monitors.filter((m) => m.id !== id),
    })),

  // Log actions
  addLog: (log) =>
    set((state) => ({
      logs: [
        {
          ...log,
          id: Math.random().toString(36).substring(7),
        },
        ...state.logs,
      ].slice(0, 1000), // Keep only last 1000 logs
    })),
  clearLogs: () => set({ logs: [] }),
  setLogsFilter: (filter) => set({ logsFilter: filter }),

  // System health actions
  setSystemHealth: (health) => set({ systemHealth: health }),

  // Alert actions
  addAlert: (alert) =>
    set((state) => ({
      alerts: [
        {
          ...alert,
          id: Math.random().toString(36).substring(7),
          timestamp: new Date().toISOString(),
          acknowledged: false,
        },
        ...state.alerts,
      ],
    })),
  acknowledgeAlert: (id) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.id === id ? { ...a, acknowledged: true } : a
      ),
    })),
}));
