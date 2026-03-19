import React, { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { CaseStage } from '../types/backend-models';
import { getCaseDetail, getRunHistoryForCase } from '../services/api';
import { PipelineFlow } from '../components/data-visualization/PipelineFlow';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';

const MOCK_LOG_BASE_TIME = Date.parse('2026-03-19T12:00:00.000Z');

export const PipelineMonitor: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [logFilter, setLogFilter] = useState<'all' | 'errors' | 'warnings'>('all');

  // Fetch case detail
  const { data: caseData, isLoading, error, refetch } = useQuery({
    queryKey: ['case-detail', id],
    queryFn: () => getCaseDetail(id || ''),
    enabled: !!id,
    refetchInterval: autoRefresh ? 5000 : false, // 5s polling when auto-refresh is on
  });

  // Fetch run history
  const { data: runHistory = [] } = useQuery({
    queryKey: ['run-history', id],
    queryFn: () => getRunHistoryForCase(id || ''),
    enabled: !!id,
    refetchInterval: autoRefresh ? 5000 : false,
  });

  const currentStage: CaseStage = caseData?.case?.stage || 'BOOTSTRAP';

  const logs = useMemo<Array<{
    id: string;
    timestamp: Date;
    level: 'info' | 'warning' | 'error';
    stage: string;
    message: string;
  }>>(() => {
    return [
      { id: '1', timestamp: new Date(MOCK_LOG_BASE_TIME - 60000), level: 'info', stage: 'RETRIEVE', message: 'Starting retrieval phase' },
      { id: '2', timestamp: new Date(MOCK_LOG_BASE_TIME - 50000), level: 'info', stage: 'RETRIEVE', message: 'Found 47 articles to process' },
      { id: '3', timestamp: new Date(MOCK_LOG_BASE_TIME - 40000), level: 'warning', stage: 'TRIAGE', message: 'Low confidence score on 3 articles' },
      { id: '4', timestamp: new Date(MOCK_LOG_BASE_TIME - 30000), level: 'info', stage: 'INVESTIGATE', message: 'Analyzing claim relationships' },
      { id: '5', timestamp: new Date(MOCK_LOG_BASE_TIME - 20000), level: 'info', stage: 'INVESTIGATE', message: 'Identified 12 new potential claims' },
      { id: '6', timestamp: new Date(MOCK_LOG_BASE_TIME - 10000), level: 'error', stage: 'ARBITRATE', message: 'Timeout during fact check verification' },
    ];
  }, []);

  const filteredLogs = logs.filter((log) => {
    if (logFilter === 'errors') return log.level === 'error';
    if (logFilter === 'warnings') return log.level === 'warning' || log.level === 'error';
    return true;
  });

  const getLogColor = (level: string) => {
    switch (level) {
      case 'error': return 'text-[#ff4757]';
      case 'warning': return 'text-[#ffb800]';
      default: return 'text-[#00d4ff]';
    }
  };

  const getLogIcon = (level: string) => {
    switch (level) {
      case 'error': return '⚠';
      case 'warning': return '⚡';
      default: return 'ℹ';
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#f0f2f5]">Pipeline Monitor</h1>
          <p className="text-sm text-[#9aa1b3] mt-1">
            Real-time pipeline execution monitoring
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            className="px-4 py-2 text-sm font-medium bg-[#0a0a0a] border border-[#2d3340] text-[#f0f2f5] rounded-sm hover:border-[#3f4758] transition-colors"
          >
            Refresh
          </button>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-4 h-4 rounded-sm"
            />
            <span className="text-[#f0f2f5]">Auto-refresh (5s)</span>
          </label>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="text-[#9aa1b3]">Loading pipeline data...</div>
        </div>
      ) : error ? (
        <Card>
          <CardBody className="py-8">
            <div className="text-center text-[#ff4757]">
              Failed to load pipeline data. Please try again.
            </div>
          </CardBody>
        </Card>
      ) : (
        <>
          {/* Pipeline Flow Visualization */}
          <PipelineFlow
            currentStage={currentStage}
            runHistory={runHistory}
            onStageClick={(stage) => console.log('Stage clicked:', stage)}
          />

          {/* Performance Metrics */}
          <div className="grid grid-cols-4 gap-4">
            <Card padding="sm">
              <CardBody className="space-y-1">
                <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Total Stages</div>
                <div className="text-2xl font-bold text-[#00d4ff]">7</div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody className="space-y-1">
                <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Completed</div>
                <div className="text-2xl font-bold text-[#00ff9d]">
                  {runHistory.filter((r) => r.status === 'success').length}
                </div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody className="space-y-1">
                <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Errors</div>
                <div className="text-2xl font-bold text-[#ff4757]">
                  {runHistory.filter((r) => r.status === 'error').length}
                </div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody className="space-y-1">
                <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Avg Duration</div>
                <div className="text-2xl font-bold text-[#f0f2f5] font-mono">
                  {runHistory.length > 0 && runHistory.every((r) => r.durationMs)
                    ? `${(runHistory.reduce((sum, r) => sum + (r.durationMs || 0), 0) / runHistory.length / 1000).toFixed(1)}s`
                    : 'N/A'}
                </div>
              </CardBody>
            </Card>
          </div>

          {/* Logs and Details */}
          <div className="grid grid-cols-2 gap-6">
            {/* Log Stream */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Log Stream</CardTitle>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setLogFilter('all')}
                      className={`px-3 py-1 text-xs font-medium rounded-sm transition-colors ${
                        logFilter === 'all'
                          ? 'bg-[#00d4ff] text-black'
                          : 'bg-[#0a0a0a] border border-[#2d3340] text-[#9aa1b3] hover:border-[#3f4758]'
                      }`}
                    >
                      All
                    </button>
                    <button
                      onClick={() => setLogFilter('warnings')}
                      className={`px-3 py-1 text-xs font-medium rounded-sm transition-colors ${
                        logFilter === 'warnings'
                          ? 'bg-[#ffb800] text-black'
                          : 'bg-[#0a0a0a] border border-[#2d3340] text-[#9aa1b3] hover:border-[#3f4758]'
                      }`}
                    >
                      Warnings
                    </button>
                    <button
                      onClick={() => setLogFilter('errors')}
                      className={`px-3 py-1 text-xs font-medium rounded-sm transition-colors ${
                        logFilter === 'errors'
                          ? 'bg-[#ff4757] text-black'
                          : 'bg-[#0a0a0a] border border-[#2d3340] text-[#9aa1b3] hover:border-[#3f4758]'
                      }`}
                    >
                      Errors
                    </button>
                  </div>
                </div>
              </CardHeader>
              <CardBody>
                <div className="space-y-2 max-h-96 overflow-y-auto font-mono text-xs">
                  {filteredLogs.length === 0 ? (
                    <div className="text-center text-[#6c7385] py-8">No logs to display</div>
                  ) : (
                    filteredLogs.map((log) => (
                      <div
                        key={log.id}
                        className="flex items-start gap-3 p-2 bg-[#0a0a0a] border border-[#1a1a1a] rounded-sm hover:border-[#2d3340] transition-colors"
                      >
                        <span className={getLogColor(log.level)}>{getLogIcon(log.level)}</span>
                        <span className="text-[#6c7385] flex-shrink-0">
                          {log.timestamp.toLocaleTimeString()}
                        </span>
                        <span className="text-[#00d4ff] flex-shrink-0">[{log.stage}]</span>
                        <span className="text-[#f0f2f5] flex-1">{log.message}</span>
                      </div>
                    ))
                  )}
                </div>
              </CardBody>
            </Card>

            {/* Stage Performance */}
            <Card>
              <CardHeader>
                <CardTitle>Stage Performance</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="space-y-3">
                  {runHistory.slice(0, 10).map((run) => (
                    <div
                      key={run.id}
                      className="flex items-center justify-between p-3 bg-[#0a0a0a] border border-[#1a1a1a] rounded-sm"
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-2 h-2 rounded-sm ${
                            run.status === 'success' ? 'bg-[#00ff9d]' : run.status === 'error' ? 'bg-[#ff4757]' : 'bg-[#6c7385]'
                          }`}
                        />
                        <div>
                          <div className="text-sm text-[#f0f2f5]">{run.stage}</div>
                          <div className="text-xs text-[#9aa1b3]">{run.model || 'Unknown'}</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm text-[#f0f2f5] font-mono">
                          {run.durationMs ? `${(run.durationMs / 1000).toFixed(2)}s` : 'N/A'}
                        </div>
                        <div className="text-xs text-[#9aa1b3] capitalize">{run.status}</div>
                      </div>
                    </div>
                  ))}
                  {runHistory.length === 0 && (
                    <div className="text-center text-[#6c7385] py-8">No performance data available</div>
                  )}
                </div>
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export default PipelineMonitor;
