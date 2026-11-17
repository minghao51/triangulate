import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { PipelineFlow } from './PipelineFlow';
import type { RunHistoryItem } from '../../types/backend-models';

const run = (overrides: Partial<RunHistoryItem>): RunHistoryItem => ({
  id: 'run-1',
  stage: 'RETRIEVE',
  model: 'model-a',
  durationMs: 1000,
  status: 'success',
  fallbackCount: 0,
  parseFailureCount: 0,
  timestamp: '2026-03-19T10:00:00Z',
  message: null,
  ...overrides,
});

const stageLabel = (stage: string) =>
  screen.getByRole('button', { name: new RegExp(`^Stage ${stage}:`) });

describe('PipelineFlow stage outcomes', () => {
  it('claims no completion or running state for an empty history at REVIEW', () => {
    render(<PipelineFlow currentStage="REVIEW" runHistory={[]} />);

    expect(screen.queryByText('Succeeded')).toBeNull();
    expect(screen.queryByText('Running')).toBeNull();
    expect(screen.getAllByText('Unrecorded').length).toBeGreaterThan(0);

    // The pointer is labelled as recorded state only.
    expect(stageLabel('REVIEW').getAttribute('aria-label')).toBe(
      'Stage REVIEW: Unrecorded, last recorded case stage'
    );
    expect(stageLabel('RETRIEVE').getAttribute('aria-label')).toBe('Stage RETRIEVE: Unrecorded');
  });

  it('uses the latest recorded attempt when an older attempt errored', () => {
    render(
      <PipelineFlow
        currentStage="TRIAGE"
        runHistory={[
          run({ id: 'old', stage: 'RETRIEVE', status: 'error', timestamp: '2026-03-19T09:00:00Z' }),
          run({ id: 'new', stage: 'RETRIEVE', status: 'success', timestamp: '2026-03-19T11:00:00Z' }),
        ]}
      />
    );

    expect(stageLabel('RETRIEVE').getAttribute('aria-label')).toBe('Stage RETRIEVE: Succeeded');
  });

  it('does not mark the current pointer as running when its latest attempt errored', () => {
    render(
      <PipelineFlow
        currentStage="INVESTIGATE"
        runHistory={[run({ stage: 'INVESTIGATE', status: 'error' })]}
      />
    );

    expect(stageLabel('INVESTIGATE').getAttribute('aria-label')).toBe(
      'Stage INVESTIGATE: Error, last recorded case stage'
    );
    expect(screen.queryByText('Running')).toBeNull();
  });

  it('claims nothing when several attempts have no usable timestamps', () => {
    render(
      <PipelineFlow
        currentStage="TRIAGE"
        runHistory={[
          run({ id: 'a', stage: 'RETRIEVE', status: 'success', timestamp: null }),
          run({ id: 'b', stage: 'RETRIEVE', status: 'error', timestamp: 'not-a-date' }),
        ]}
      />
    );

    expect(stageLabel('RETRIEVE').getAttribute('aria-label')).toBe('Stage RETRIEVE: Unrecorded');
  });

  it('does not claim success when a dated success is mixed with an undated error', () => {
    render(
      <PipelineFlow
        currentStage="TRIAGE"
        runHistory={[
          run({ id: 'dated', stage: 'RETRIEVE', status: 'success', timestamp: '2026-03-19T10:00:00Z' }),
          run({ id: 'undated', stage: 'RETRIEVE', status: 'error', timestamp: null }),
        ]}
      />
    );

    // Ordering is unknowable, so no outcome may be claimed.
    expect(stageLabel('RETRIEVE').getAttribute('aria-label')).toBe('Stage RETRIEVE: Unrecorded');
  });

  it('does not claim success when tied latest timestamps conflict', () => {
    render(
      <PipelineFlow
        currentStage="TRIAGE"
        runHistory={[
          run({ id: 'a', stage: 'RETRIEVE', status: 'success', timestamp: '2026-03-19T10:00:00Z' }),
          run({ id: 'b', stage: 'RETRIEVE', status: 'error', timestamp: '2026-03-19T10:00:00Z' }),
        ]}
      />
    );

    expect(stageLabel('RETRIEVE').getAttribute('aria-label')).toBe('Stage RETRIEVE: Unrecorded');
  });

  it('still uses a tied latest timestamp when the statuses agree', () => {
    render(
      <PipelineFlow
        currentStage="TRIAGE"
        runHistory={[
          run({ id: 'a', stage: 'RETRIEVE', status: 'success', timestamp: '2026-03-19T10:00:00Z' }),
          run({ id: 'b', stage: 'RETRIEVE', status: 'success', timestamp: '2026-03-19T10:00:00Z' }),
        ]}
      />
    );

    expect(stageLabel('RETRIEVE').getAttribute('aria-label')).toBe('Stage RETRIEVE: Succeeded');
  });

  it('shows recorded models and never invented agent roles', () => {
    render(
      <PipelineFlow
        currentStage="RETRIEVE"
        runHistory={[run({ stage: 'RETRIEVE', model: 'gpt-recorded', status: 'running' })]}
      />
    );

    fireEvent.click(stageLabel('RETRIEVE'));

    expect(screen.getAllByText('gpt-recorded').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Running').length).toBeGreaterThan(0);
    expect(screen.queryByText('Collector')).toBeNull();
    expect(screen.queryByText('Judge')).toBeNull();
    expect(screen.queryByText('Stage Agents')).toBeNull();
  });

  it('labels a null duration row as not recorded and a negative one as invalid', () => {
    render(
      <PipelineFlow
        currentStage="RETRIEVE"
        runHistory={[
          run({ id: 'a', stage: 'RETRIEVE', durationMs: null, model: 'no-duration' }),
          run({ id: 'b', stage: 'RETRIEVE', durationMs: -5, model: 'bad-duration' }),
          run({ id: 'c', stage: 'RETRIEVE', durationMs: Number.POSITIVE_INFINITY, model: 'inf-duration' }),
        ]}
      />
    );

    fireEvent.click(stageLabel('RETRIEVE'));

    expect(screen.getByText(/Not recorded · success/)).toBeDefined();
    expect(screen.getAllByText(/Invalid duration/).length).toBe(2);
    expect(screen.queryByText(/NaN|Infinity/)).toBeNull();
  });

  it('exposes selection through aria-pressed and accessible stage names', () => {
    render(<PipelineFlow currentStage="REVIEW" runHistory={[]} />);

    const node = stageLabel('TRIAGE');
    expect(node.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(node);
    expect(node.getAttribute('aria-pressed')).toBe('true');
  });
});
