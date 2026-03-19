import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCases } from '../services/api';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import Button from '../components/design-system/Button';
import type { TopicCase } from '../types/backend-models';

interface Monitor {
  id: string;
  name: string;
  query: string;
  schedule: string;
  active: boolean;
  lastRun: string | null;
  nextRun: string | null;
  status: 'running' | 'idle' | 'error';
}

interface Alert {
  id: string;
  monitorId: string;
  severity: 'high' | 'medium' | 'low';
  message: string;
  timestamp: string;
  acknowledged: boolean;
}

const MOCK_NOW = Date.parse('2026-03-19T12:00:00.000Z');

export const MonitoringCenter: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'monitors' | 'alerts' | 'performance'>('monitors');
  const [selectedMonitor, setSelectedMonitor] = useState<Monitor | null>(null);

  // Fetch all cases (simulated monitors)
  const { data: cases, isLoading, error } = useQuery({
    queryKey: ['cases'],
    queryFn: () => getCases(),
    refetchInterval: 30000, // 30s polling
  });

  // Simulated monitors data
  const monitors: Monitor[] = cases
    ?.filter((c: TopicCase) => c.status === 'monitoring')
    .map((c: TopicCase) => ({
      id: c.id,
      name: c.query,
      query: c.query,
      schedule: 'Daily',
      active: true,
      lastRun: c.lastUpdated,
      nextRun: new Date(MOCK_NOW + 86400000).toISOString(),
      status: 'idle' as const,
    })) || [];

  // Simulated alerts data
  const alerts: Alert[] = [
    {
      id: '1',
      monitorId: monitors[0]?.id || '',
      severity: 'high',
      message: 'New material detected - 15 new articles found',
      timestamp: new Date(MOCK_NOW - 3600000).toISOString(),
      acknowledged: false,
    },
    {
      id: '2',
      monitorId: monitors[0]?.id || '',
      severity: 'medium',
      message: 'Verification status changed for 3 claims',
      timestamp: new Date(MOCK_NOW - 7200000).toISOString(),
      acknowledged: false,
    },
    {
      id: '3',
      monitorId: monitors[1]?.id || '',
      severity: 'low',
      message: 'Scheduled check completed successfully',
      timestamp: new Date(MOCK_NOW - 10800000).toISOString(),
      acknowledged: true,
    },
  ];

  const activeMonitors = monitors.filter((m) => m.active).length;
  const unacknowledgedAlerts = alerts.filter((a) => !a.acknowledged).length;

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high': return 'text-[#ff4757]';
      case 'medium': return 'text-[#ffb800]';
      default: return 'text-[#00ff9d]';
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'high': return 'danger';
      case 'medium': return 'warning';
      default: return 'success';
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#f0f2f5]">Active Monitoring</h1>
          <p className="text-sm text-[#9aa1b3] mt-1">
            Configure and monitor automated investigation tasks
          </p>
        </div>
        <Button variant="primary" icon={<span>+</span>}>
          New Monitor
        </Button>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card padding="sm">
          <CardBody className="flex items-center justify-between">
            <div>
              <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Active Monitors</div>
              <div className="text-2xl font-bold text-[#00d4ff]">{activeMonitors}</div>
            </div>
            <div className="text-3xl">📡</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="flex items-center justify-between">
            <div>
              <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Pending Alerts</div>
              <div className="text-2xl font-bold text-[#ff4757]">{unacknowledgedAlerts}</div>
            </div>
            <div className="text-3xl">🔔</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="flex items-center justify-between">
            <div>
              <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Total Checks</div>
              <div className="text-2xl font-bold text-[#00ff9d]">
                {monitors.reduce((sum, m) => sum + (m.lastRun ? 1 : 0), 0)}
              </div>
            </div>
            <div className="text-3xl">✓</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="flex items-center justify-between">
            <div>
              <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">System Health</div>
              <div className="text-2xl font-bold text-[#00ff9d]">98%</div>
            </div>
            <div className="text-3xl">💚</div>
          </CardBody>
        </Card>
      </div>

      {/* Tabs */}
      <div className="border-b border-[#2d3340]">
        <div className="flex gap-6">
          <button
            onClick={() => setActiveTab('monitors')}
            className={`pb-3 text-sm font-medium transition-colors ${
              activeTab === 'monitors'
                ? 'text-[#00d4ff] border-b-2 border-[#00d4ff]'
                : 'text-[#9aa1b3] hover:text-[#f0f2f5]'
            }`}
          >
            Monitors ({monitors.length})
          </button>
          <button
            onClick={() => setActiveTab('alerts')}
            className={`pb-3 text-sm font-medium transition-colors ${
              activeTab === 'alerts'
                ? 'text-[#00d4ff] border-b-2 border-[#00d4ff]'
                : 'text-[#9aa1b3] hover:text-[#f0f2f5]'
            }`}
          >
            Alerts ({alerts.length})
          </button>
          <button
            onClick={() => setActiveTab('performance')}
            className={`pb-3 text-sm font-medium transition-colors ${
              activeTab === 'performance'
                ? 'text-[#00d4ff] border-b-2 border-[#00d4ff]'
                : 'text-[#9aa1b3] hover:text-[#f0f2f5]'
            }`}
          >
            Performance
          </button>
        </div>
      </div>

      {isLoading ? (
        <Card>
          <CardBody className="py-16">
            <div className="text-center text-[#9aa1b3]">Loading monitoring data...</div>
          </CardBody>
        </Card>
      ) : error ? (
        <Card>
          <CardBody className="py-16">
            <div className="text-center text-[#ff4757]">Failed to load monitoring data</div>
          </CardBody>
        </Card>
      ) : (
        <>
          {/* Monitors Tab */}
          {activeTab === 'monitors' && (
            <div className="grid grid-cols-3 gap-6">
              <div className="col-span-2 space-y-4">
                {monitors.length === 0 ? (
                  <Card>
                    <CardBody className="py-16">
                      <div className="text-center text-[#6c7385]">
                        <div className="text-4xl mb-3">📡</div>
                        <div className="text-sm">No active monitors configured</div>
                        <Button className="mt-4" variant="primary">
                          Create First Monitor
                        </Button>
                      </div>
                    </CardBody>
                  </Card>
                ) : (
                  monitors.map((monitor) => (
                    <Card
                      key={monitor.id}
                      hover
                      className={selectedMonitor?.id === monitor.id ? 'border-[#00d4ff]' : ''}
                      onClick={() => setSelectedMonitor(monitor)}
                    >
                      <CardBody>
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-3 mb-2">
                              <h3 className="text-base font-semibold text-[#f0f2f5]">{monitor.name}</h3>
                              <Badge variant={monitor.active ? 'success' : 'neutral'} size="sm">
                                {monitor.active ? 'Active' : 'Inactive'}
                              </Badge>
                              <Badge variant={monitor.status === 'running' ? 'info' : 'neutral'} size="sm">
                                {monitor.status}
                              </Badge>
                            </div>
                            <div className="text-sm text-[#9aa1b3] mb-3">{monitor.query}</div>
                            <div className="flex items-center gap-6 text-xs text-[#6c7385]">
                              <span>Schedule: {monitor.schedule}</span>
                              <span>Last Run: {monitor.lastRun ? new Date(monitor.lastRun).toLocaleString() : 'Never'}</span>
                              <span>Next Run: {monitor.nextRun ? new Date(monitor.nextRun).toLocaleString() : 'N/A'}</span>
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <Button variant="ghost" size="sm">
                              Edit
                            </Button>
                            <Button variant="ghost" size="sm">
                              Run Now
                            </Button>
                          </div>
                        </div>
                      </CardBody>
                    </Card>
                  ))
                )}
              </div>

              {/* Monitor Details */}
              <div className="space-y-4">
                {selectedMonitor ? (
                  <>
                    <Card>
                      <CardHeader>
                        <CardTitle>Monitor Configuration</CardTitle>
                      </CardHeader>
                      <CardBody className="space-y-4">
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Query</div>
                          <div className="text-sm text-[#f0f2f5]">{selectedMonitor.query}</div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Schedule</div>
                          <div className="text-sm text-[#f0f2f5]">{selectedMonitor.schedule}</div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Status</div>
                          <Badge variant={selectedMonitor.active ? 'success' : 'neutral'}>
                            {selectedMonitor.active ? 'Active' : 'Inactive'}
                          </Badge>
                        </div>
                        <div className="pt-4 border-t border-[#2d3340] space-y-2">
                          <Button className="w-full" variant="primary">
                            Run Now
                          </Button>
                          <Button className="w-full" variant="secondary">
                            Edit Configuration
                          </Button>
                          <Button className="w-full" variant="danger">
                            Delete Monitor
                          </Button>
                        </div>
                      </CardBody>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardTitle>Recent Alerts</CardTitle>
                      </CardHeader>
                      <CardBody>
                        <div className="space-y-2">
                          {alerts
                            .filter((a) => a.monitorId === selectedMonitor.id)
                            .slice(0, 5)
                            .map((alert) => (
                              <div
                                key={alert.id}
                                className="flex items-start gap-3 p-2 bg-[#0a0a0a] border border-[#1a1a1a] rounded-sm"
                              >
                                <div className={getSeverityColor(alert.severity)}>⚠</div>
                                <div className="flex-1">
                                  <div className="text-sm text-[#f0f2f5]">{alert.message}</div>
                                  <div className="text-xs text-[#6c7385] mt-1">
                                    {new Date(alert.timestamp).toLocaleString()}
                                  </div>
                                </div>
                              </div>
                            ))}
                          {alerts.filter((a) => a.monitorId === selectedMonitor.id).length === 0 && (
                            <div className="text-center text-[#6c7385] py-4">No recent alerts</div>
                          )}
                        </div>
                      </CardBody>
                    </Card>
                  </>
                ) : (
                  <Card>
                    <CardBody className="py-16">
                      <div className="text-center text-[#6c7385]">
                        <div className="text-4xl mb-3">📊</div>
                        <div className="text-sm">Select a monitor to view details</div>
                      </div>
                    </CardBody>
                  </Card>
                )}
              </div>
            </div>
          )}

          {/* Alerts Tab */}
          {activeTab === 'alerts' && (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Recent Alerts</CardTitle>
                  <Button variant="secondary" size="sm">
                    Acknowledge All
                  </Button>
                </div>
              </CardHeader>
              <CardBody>
                <div className="space-y-3">
                  {alerts.map((alert) => (
                    <div
                      key={alert.id}
                      className={`p-4 border rounded-sm ${
                        alert.acknowledged ? 'border-[#1a1a1a] opacity-60' : 'border-[#2d3340]'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-3">
                          <span className={getSeverityColor(alert.severity)}>⚠</span>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-sm font-medium text-[#f0f2f5]">
                                {alerts.find((m) => m.id === alert.monitorId)?.monitorId || 'Unknown Monitor'}
                              </span>
                              <Badge variant={getSeverityBadge(alert.severity)} size="sm">
                                {alert.severity}
                              </Badge>
                              {alert.acknowledged && (
                                <Badge variant="neutral" size="sm">
                                  Acknowledged
                                </Badge>
                              )}
                            </div>
                            <div className="text-sm text-[#f0f2f5]">{alert.message}</div>
                            <div className="text-xs text-[#6c7385] mt-1">
                              {new Date(alert.timestamp).toLocaleString()}
                            </div>
                          </div>
                        </div>
                        {!alert.acknowledged && (
                          <Button variant="ghost" size="sm">
                            Acknowledge
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                  {alerts.length === 0 && (
                    <div className="text-center text-[#00ff9d] py-8">
                      <div className="text-4xl mb-2">✓</div>
                      <div className="text-sm">No alerts</div>
                    </div>
                  )}
                </div>
              </CardBody>
            </Card>
          )}

          {/* Performance Tab */}
          {activeTab === 'performance' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>System Performance</CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="grid grid-cols-3 gap-6">
                    <div>
                      <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-2">Avg Response Time</div>
                      <div className="text-3xl font-bold text-[#00d4ff]">1.2s</div>
                      <div className="text-xs text-[#00ff9d] mt-1">↓ 15% from last week</div>
                    </div>
                    <div>
                      <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-2">Success Rate</div>
                      <div className="text-3xl font-bold text-[#00ff9d]">98.5%</div>
                      <div className="text-xs text-[#00ff9d] mt-1">↑ 2% from last week</div>
                    </div>
                    <div>
                      <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-2">Total Runs</div>
                      <div className="text-3xl font-bold text-[#a55eea]">
                        {monitors.reduce((sum, m) => sum + (m.lastRun ? 1 : 0), 0)}
                      </div>
                      <div className="text-xs text-[#9aa1b3] mt-1">All time</div>
                    </div>
                  </div>
                </CardBody>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Performance History</CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="h-64 flex items-center justify-center text-[#6c7385]">
                    <div className="text-center">
                      <div className="text-4xl mb-2">📈</div>
                      <div className="text-sm">Performance chart would be rendered here</div>
                      <div className="text-xs mt-1">(Requires charting library integration)</div>
                    </div>
                  </div>
                </CardBody>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default MonitoringCenter;
