import React, { useState } from 'react';
import type { CaseStage, RunHistoryItem } from '../../types/backend-models';
import Card, { CardHeader, CardTitle, CardBody } from '../design-system/Card';

export interface PipelineFlowProps {
  currentStage: CaseStage;
  runHistory: RunHistoryItem[];
  onStageClick?: (stage: CaseStage) => void;
  className?: string;
}

const STAGES: CaseStage[] = [
  'BOOTSTRAP',
  'RETRIEVE',
  'TRIAGE',
  'INVESTIGATE',
  'ARBITRATE',
  'REPORT',
  'REVIEW',
];

const AGENT_NAMES: Record<CaseStage, string[]> = {
  BOOTSTRAP: ['Orchestrator'],
  RETRIEVE: ['Collector', 'Searcher'],
  TRIAGE: ['Classifier', 'Filter'],
  INVESTIGATE: ['Investigator', 'Analyst'],
  ARBITRATE: ['Arbiter', 'Judge'],
  REPORT: ['Narrator', 'Summarizer'],
  REVIEW: ['Reviewer', 'Validator'],
};

const STAGE_COLORS: Record<CaseStage, string> = {
  BOOTSTRAP: '#6c5ce7',
  RETRIEVE: '#00d4ff',
  TRIAGE: '#00ff9d',
  INVESTIGATE: '#ffb800',
  ARBITRATE: '#ff6b00',
  REPORT: '#a55eea',
  REVIEW: '#ff4757',
};

const getStageStatus = (
  stage: CaseStage,
  currentStage: CaseStage,
  runHistory: RunHistoryItem[]
): 'completed' | 'active' | 'pending' | 'error' => {
  const currentIndex = STAGES.indexOf(currentStage);
  const stageIndex = STAGES.indexOf(stage);

  if (stageIndex > currentIndex) return 'pending';
  if (stageIndex === currentIndex) return 'active';

  // Check for errors in this stage
  const stageRuns = runHistory.filter((r) => r.stage === stage);
  const hasError = stageRuns.some((r) => r.status === 'error');
  if (hasError) return 'error';

  return 'completed';
};

export const PipelineFlow: React.FC<PipelineFlowProps> = ({
  currentStage,
  runHistory,
  onStageClick,
  className = '',
}) => {
  const [selectedStage, setSelectedStage] = useState<CaseStage | null>(null);

  const handleStageClick = (stage: CaseStage) => {
    setSelectedStage(stage);
    if (onStageClick) onStageClick(stage);
  };

  return (
    <div className={className}>
      <Card>
        <CardHeader>
          <CardTitle>Pipeline Progress</CardTitle>
        </CardHeader>

        <CardBody>
          {/* Pipeline Flow */}
          <div className="relative mb-8">
            {/* Progress Line */}
            <div className="absolute top-8 left-0 right-0 h-0.5 bg-[#2d3340]" />

            <div className="flex justify-between relative">
              {STAGES.map((stage, index) => {
                const status = getStageStatus(stage, currentStage, runHistory);
                const isActive = status === 'active';
                const isCompleted = status === 'completed';
                const hasError = status === 'error';
                const isSelected = selectedStage === stage;

                return (
                  <div key={stage} className="flex flex-col items-center gap-3 relative z-10">
                    {/* Stage Node */}
                    <button
                      onClick={() => handleStageClick(stage)}
                      className={`
                        relative w-16 h-16 rounded-sm border-2 transition-all duration-200
                        ${isActive ? 'animate-pulse' : ''}
                        ${hasError ? 'border-[#ff4757]' : isCompleted ? 'border-[#00ff9d]' : 'border-[#2d3340]'}
                        ${isSelected ? 'ring-2 ring-[#00d4ff] ring-offset-2 ring-offset-[#0a0a0a]' : ''}
                        hover:scale-105
                      `}
                      style={{
                        backgroundColor: hasError ? 'rgba(255, 71, 87, 0.1)' :
                          isCompleted ? 'rgba(0, 255, 157, 0.1)' :
                          isActive ? 'rgba(0, 212, 255, 0.1)' : '#0a0a0a',
                      }}
                    >
                      {/* Status Icon */}
                      <div className="absolute inset-0 flex items-center justify-center">
                        {hasError ? (
                          <svg className="w-6 h-6 text-[#ff4757]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        ) : isCompleted ? (
                          <svg className="w-6 h-6 text-[#00ff9d]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        ) : isActive ? (
                          <div className="w-4 h-4 bg-[#00d4ff] rounded-full animate-ping" />
                        ) : (
                          <div className="w-4 h-4 border-2 border-[#6c7385] rounded-full" />
                        )}
                      </div>

                      {/* Stage Number */}
                      <div className="absolute -top-2 -right-2 w-5 h-5 bg-[#0a0a0a] border border-[#2d3340] rounded-sm flex items-center justify-center">
                        <span className="text-xs font-mono text-[#9aa1b3]">{index + 1}</span>
                      </div>
                    </button>

                    {/* Stage Label */}
                    <div className="text-center">
                      <div
                        className={`
                          text-xs font-semibold uppercase tracking-wider mb-1
                          ${isActive ? 'text-[#00d4ff]' : hasError ? 'text-[#ff4757]' : 'text-[#9aa1b3]'}
                        `}
                      >
                        {stage}
                      </div>
                      <div className="text-[10px] text-[#6c7385]">
                        {AGENT_NAMES[stage].join(', ')}
                      </div>
                    </div>

                    {/* Connecting Line to Next Stage */}
                    {index < STAGES.length - 1 && (
                      <div
                        className={`
                          absolute top-8 left-16 w-full h-0.5 -z-10 transition-all duration-300
                          ${isCompleted ? 'bg-[#00ff9d]' : 'bg-[#2d3340]'}
                        `}
                        style={{
                          width: 'calc(100% - 4rem)',
                        }}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Stage Details */}
          {selectedStage && (
            <div className="border-t border-[#2d3340] pt-4">
              <h4 className="text-sm font-semibold text-[#00d4ff] uppercase tracking-wider mb-3">
                {selectedStage} Stage Details
              </h4>

              <div className="grid grid-cols-3 gap-4 mb-4">
                <div>
                  <div className="text-xs text-[#9aa1b3] mb-1">Agents</div>
                  <div className="text-sm text-[#f0f2f5]">{AGENT_NAMES[selectedStage].join(', ')}</div>
                </div>

                <div>
                  <div className="text-xs text-[#9aa1b3] mb-1">Status</div>
                  <div className="text-sm text-[#f0f2f5] capitalize">
                    {getStageStatus(selectedStage, currentStage, runHistory)}
                  </div>
                </div>

                <div>
                  <div className="text-xs text-[#9aa1b3] mb-1">Color</div>
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-sm"
                      style={{ backgroundColor: STAGE_COLORS[selectedStage] }}
                    />
                    <span className="text-sm text-[#f0f2f5] font-mono">{STAGE_COLORS[selectedStage]}</span>
                  </div>
                </div>
              </div>

              {/* Stage Runs */}
              <div>
                <div className="text-xs text-[#9aa1b3] mb-2">Execution History</div>
                <div className="space-y-2 max-h-40 overflow-y-auto">
                  {runHistory
                    .filter((r) => r.stage === selectedStage)
                    .map((run) => (
                      <div
                        key={run.id}
                        className="flex items-center justify-between p-2 bg-[#0a0a0a] border border-[#2d3340] rounded-sm text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <div
                            className={`
                              w-2 h-2 rounded-sm
                              ${run.status === 'success' ? 'bg-[#00ff9d]' : ''}
                              ${run.status === 'error' ? 'bg-[#ff4757]' : ''}
                              ${run.status === 'running' ? 'bg-[#00d4ff] animate-pulse' : ''}
                              ${run.status === 'pending' ? 'bg-[#6c7385]' : ''}
                            `}
                          />
                          <span className="text-[#f0f2f5]">{run.model || 'Unknown'}</span>
                        </div>
                        <div className="flex items-center gap-4">
                          {run.durationMs && (
                            <span className="text-[#9aa1b3] font-mono">
                              {(run.durationMs / 1000).toFixed(1)}s
                            </span>
                          )}
                          <span className="text-[#9aa1b3] capitalize">{run.status}</span>
                        </div>
                      </div>
                    ))}
                  {runHistory.filter((r) => r.stage === selectedStage).length === 0 && (
                    <div className="text-xs text-[#6c7385]">No execution history for this stage</div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Current Stage Summary */}
          {!selectedStage && (
            <div className="border-t border-[#2d3340] pt-4">
              <h4 className="text-sm font-semibold text-[#00d4ff] uppercase tracking-wider mb-3">
                Current Stage: {currentStage}
              </h4>

              <div className="grid grid-cols-4 gap-4">
                <div>
                  <div className="text-xs text-[#9aa1b3] mb-1">Active Agents</div>
                  <div className="text-sm text-[#f0f2f5]">{AGENT_NAMES[currentStage].length}</div>
                </div>

                <div>
                  <div className="text-xs text-[#9aa1b3] mb-1">Total Runs</div>
                  <div className="text-sm text-[#f0f2f5]">
                    {runHistory.filter((r) => r.stage === currentStage).length}
                  </div>
                </div>

                <div>
                  <div className="text-xs text-[#9aa1b3] mb-1">Errors</div>
                  <div className="text-sm text-[#f0f2f5]">
                    {runHistory.filter((r) => r.stage === currentStage && r.status === 'error').length}
                  </div>
                </div>

                <div>
                  <div className="text-xs text-[#9aa1b3] mb-1">Avg Duration</div>
                  <div className="text-sm text-[#f0f2f5] font-mono">
                    {(() => {
                      const stageRuns = runHistory.filter((r) => r.stage === currentStage && r.durationMs);
                      if (stageRuns.length === 0) return 'N/A';
                      const avg = stageRuns.reduce((sum, r) => sum + (r.durationMs || 0), 0) / stageRuns.length;
                      return `${(avg / 1000).toFixed(1)}s`;
                    })()}
                  </div>
                </div>
              </div>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
};

export default PipelineFlow;
