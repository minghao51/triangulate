import React, { useState } from 'react';
import type { CaseStage, RunHistoryItem } from '../../types/backend-models';
import Card, { CardHeader, CardTitle, CardBody } from '../design-system/Card';
import './PipelineFlow.css';

export interface PipelineFlowProps {
  currentStage: CaseStage;
  runHistory: RunHistoryItem[];
  onStageClick?: (stage: CaseStage) => void;
  className?: string;
}

/**
 * The workflow order below is configuration, not observed telemetry. No stage is
 * inferred as completed/running from its position relative to the case's stage
 * pointer; every execution state comes from saved stage attempts only.
 */
const STAGES: CaseStage[] = [
  'BOOTSTRAP',
  'RETRIEVE',
  'TRIAGE',
  'INVESTIGATE',
  'ARBITRATE',
  'REPORT',
  'REVIEW',
];

export type StageOutcome =
  | 'success'
  | 'error'
  | 'running'
  | 'pending'
  | 'skipped'
  | 'unrecorded';

const parseTimestamp = (value: string | null): number | null => {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const mapStatus = (status: RunHistoryItem['status']): StageOutcome => {
  switch (status) {
    case 'success':
    case 'error':
    case 'running':
    case 'pending':
    case 'skipped':
      return status;
    default:
      return 'unrecorded';
  }
};

/**
 * Outcome of the latest recorded attempt for a stage.
 *
 * - No rows: unrecorded.
 * - One row: that row's own recorded status (its timestamp is irrelevant).
 * - Several rows: the latest attempt is only determinable when *every* row has a
 *   usable timestamp. A missing/invalid timestamp on any row makes the ordering
 *   unknown, so nothing is claimed rather than guessing from array order.
 * - Tied latest timestamps with conflicting statuses: also unknown.
 */
const getStageOutcome = (
  stage: CaseStage,
  runHistory: RunHistoryItem[]
): StageOutcome => {
  const runs = runHistory.filter((run) => run.stage === stage);

  if (runs.length === 0) return 'unrecorded';
  if (runs.length === 1) return mapStatus(runs[0].status);

  const times = runs.map((run) => parseTimestamp(run.timestamp));
  if (times.some((time) => time === null)) return 'unrecorded';

  const numericTimes = times as number[];
  const latestTime = Math.max(...numericTimes);
  const latestRuns = runs.filter((_, index) => numericTimes[index] === latestTime);
  const distinctStatuses = new Set(latestRuns.map((run) => run.status));

  // Conflicting statuses at the same latest timestamp cannot be ordered.
  if (distinctStatuses.size !== 1) return 'unrecorded';

  return mapStatus(latestRuns[0].status);
};

const OUTCOME_LABELS: Record<StageOutcome, string> = {
  success: 'Succeeded',
  error: 'Error',
  running: 'Running',
  pending: 'Pending',
  skipped: 'Skipped',
  unrecorded: 'Unrecorded',
};

const recordedModels = (stage: CaseStage, runHistory: RunHistoryItem[]): string => {
  const models = Array.from(
    new Set(
      runHistory
        .filter((run) => run.stage === stage)
        .map((run) => run.model)
        .filter((model): model is string => Boolean(model))
    )
  );
  return models.length > 0 ? models.join(', ') : 'Not provided';
};

const formatDuration = (durationMs: number | null): string => {
  if (durationMs === null || durationMs === undefined) return 'Not recorded';
  if (!Number.isFinite(durationMs) || durationMs < 0) return 'Invalid duration';
  return `${(durationMs / 1000).toFixed(2)}s`;
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
          <p className="pipeline-flow-note">
            Stage states come from saved stage attempts. The order below is the configured workflow
            order, not evidence that a stage ran.
          </p>

          <div className="pipeline-flow-track">
            <div className="pipeline-flow-line" aria-hidden="true" />

            <ol className="pipeline-flow-stages">
              {STAGES.map((stage, index) => {
                const outcome = getStageOutcome(stage, runHistory);
                const isPointer = stage === currentStage;
                const isSelected = selectedStage === stage;

                return (
                  <li key={stage} className="pipeline-flow-stage">
                    <button
                      type="button"
                      aria-label={`Stage ${stage}: ${OUTCOME_LABELS[outcome]}${isPointer ? ', last recorded case stage' : ''}`}
                      aria-pressed={isSelected}
                      onClick={() => handleStageClick(stage)}
                      className={`pipeline-flow-node pipeline-flow-node--${outcome} ${isSelected ? 'pipeline-flow-node--selected' : ''}`}
                    >
                      <span className="pipeline-flow-node-index" aria-hidden="true">{index + 1}</span>
                      <span className="pipeline-flow-node-state" aria-hidden="true">
                        {outcome === 'success' ? '✓' : outcome === 'error' ? '✕' : outcome === 'running' ? '●' : '–'}
                      </span>
                    </button>

                    <div className="pipeline-flow-stage-label">
                      <div className="pipeline-flow-stage-name">{stage}</div>
                      <div className={`pipeline-flow-stage-outcome pipeline-flow-stage-outcome--${outcome}`}>
                        {OUTCOME_LABELS[outcome]}
                      </div>
                      {isPointer && (
                        <div className="pipeline-flow-stage-pointer">Last recorded case stage</div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>

          {selectedStage ? (
            <div className="pipeline-flow-details">
              <h4 className="pipeline-flow-details-title">{selectedStage} stage attempts</h4>

              <div className="pipeline-flow-detail-grid">
                <div>
                  <div className="pipeline-flow-detail-label">Recorded outcome</div>
                  <div className="pipeline-flow-detail-value">
                    {OUTCOME_LABELS[getStageOutcome(selectedStage, runHistory)]}
                  </div>
                </div>
                <div>
                  <div className="pipeline-flow-detail-label">Recorded models</div>
                  <div className="pipeline-flow-detail-value">{recordedModels(selectedStage, runHistory)}</div>
                </div>
                <div>
                  <div className="pipeline-flow-detail-label">Saved attempts</div>
                  <div className="pipeline-flow-detail-value">
                    {runHistory.filter((run) => run.stage === selectedStage).length}
                  </div>
                </div>
              </div>

              <div className="pipeline-flow-attempts">
                <div className="pipeline-flow-detail-label">Recorded attempts</div>
                {runHistory.filter((run) => run.stage === selectedStage).length === 0 ? (
                  <div className="pipeline-flow-empty">No attempt is recorded for this stage.</div>
                ) : (
                  <ul className="pipeline-flow-attempt-list">
                    {runHistory
                      .filter((run) => run.stage === selectedStage)
                      .map((run) => (
                        <li key={run.id} className="pipeline-flow-attempt">
                          <span className="pipeline-flow-attempt-model">{run.model || 'Model not recorded'}</span>
                          <span className="pipeline-flow-attempt-meta">
                            {formatDuration(run.durationMs)} · {run.status}
                            {run.fallbackCount > 0 ? ` · ${run.fallbackCount} fallback` : ''}
                          </span>
                        </li>
                      ))}
                  </ul>
                )}
              </div>
            </div>
          ) : (
            <div className="pipeline-flow-details">
              <h4 className="pipeline-flow-details-title">
                {currentStage} — last recorded case stage
              </h4>
              <p className="pipeline-flow-note">
                This is the case's recorded stage pointer. It does not prove the stage is running or
                that earlier stages succeeded.
              </p>

              <div className="pipeline-flow-detail-grid">
                <div>
                  <div className="pipeline-flow-detail-label">Recorded attempts for this stage</div>
                  <div className="pipeline-flow-detail-value">
                    {runHistory.filter((run) => run.stage === currentStage).length}
                  </div>
                </div>
                <div>
                  <div className="pipeline-flow-detail-label">Recorded errors</div>
                  <div className="pipeline-flow-detail-value">
                    {runHistory.filter((run) => run.stage === currentStage && run.status === 'error').length}
                  </div>
                </div>
                <div>
                  <div className="pipeline-flow-detail-label">Recorded models</div>
                  <div className="pipeline-flow-detail-value">
                    {recordedModels(currentStage, runHistory)}
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
