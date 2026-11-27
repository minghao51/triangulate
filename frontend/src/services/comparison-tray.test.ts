import { beforeEach, describe, expect, it } from 'vitest';
import {
  COMPARISON_TRAY_CAP,
  TRAY_CASE_MISMATCH_MESSAGE,
  TRAY_CASE_NOTICE,
  TRAY_CONTEXT_NOTICE,
  TRAY_DUPLICATE_MESSAGE,
  TRAY_FULL_MESSAGE,
  addToComparisonTray,
  clearComparisonTray,
  comparisonContextFromSearchParams,
  getComparisonTray,
  peekComparisonTray,
  reconcileComparisonTrayContext,
  removeFromComparisonTray,
  resetComparisonTray,
  subscribeComparisonTray,
} from './comparison-tray';

const CURRENT = 'current';

beforeEach(() => {
  resetComparisonTray();
});

describe('comparison tray cap and refusals', () => {
  it('holds at most two distinct evidence sources', () => {
    expect(COMPARISON_TRAY_CAP).toBe(2);
    expect(addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' }).ok).toBe(true);
    expect(addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-2' }).ok).toBe(true);

    const entries = getComparisonTray('case-1', CURRENT).entries;
    expect(entries.map((entry) => entry.evidenceId)).toEqual(['ev-1', 'ev-2']);
  });

  it('refuses a third distinct selection visibly and keeps the original two', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-2' });

    const result = addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-3' });

    expect(result.ok).toBe(false);
    expect(result.reason).toBe('tray-full');
    expect(result.message).toBe(TRAY_FULL_MESSAGE);
    // Never a silent replacement: the two original entries are untouched.
    expect(getComparisonTray('case-1', CURRENT).entries.map((e) => e.evidenceId)).toEqual([
      'ev-1',
      'ev-2',
    ]);
    expect(getComparisonTray('case-1', CURRENT).rejection).toBe(TRAY_FULL_MESSAGE);
  });

  it('refuses the same evidence item even when a different capture is pinned', () => {
    addToComparisonTray('case-1', CURRENT, {
      evidenceId: 'ev-1',
      captureId: 'cap-old',
    });

    const result = addToComparisonTray('case-1', CURRENT, {
      evidenceId: 'ev-1',
      captureId: 'cap-new',
    });

    expect(result.ok).toBe(false);
    expect(result.reason).toBe('duplicate-evidence');
    expect(result.message).toBe(TRAY_DUPLICATE_MESSAGE);
    expect(result.message).toMatch(/capture history/);
    const entries = getComparisonTray('case-1', CURRENT).entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].captureId).toBe('cap-old');
  });

  it('refuses an empty selection without touching the draft', () => {
    const result = addToComparisonTray('case-1', CURRENT, { evidenceId: '   ' });
    expect(result.ok).toBe(false);
    expect(result.reason).toBe('invalid-selection');
    expect(getComparisonTray('case-1', CURRENT).entries).toHaveLength(0);
  });
});

describe('comparison tray pins and removal', () => {
  it('carries stable evidence ids and pinned capture ids', () => {
    addToComparisonTray('case-1', CURRENT, {
      evidenceId: 'ev-1',
      captureId: 'cap-1',
      title: 'Left source',
      publisher: 'Meridian Wire',
    });
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-2' });

    const [left, right] = getComparisonTray('case-1', CURRENT).entries;
    expect(left).toEqual({
      evidenceId: 'ev-1',
      captureId: 'cap-1',
      title: 'Left source',
      publisher: 'Meridian Wire',
    });
    // No capture chosen: Compare resolves the default and pins it in the URL.
    expect(right.captureId).toBeNull();
  });

  it('removes one entry by evidence id and leaves the other in place', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-2' });

    removeFromComparisonTray('case-1', CURRENT, 'ev-1');

    expect(getComparisonTray('case-1', CURRENT).entries.map((e) => e.evidenceId)).toEqual([
      'ev-2',
    ]);
    // A freed slot can be filled again, and the refusal clears.
    const readded = addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-3' });
    expect(readded.ok).toBe(true);
    expect(getComparisonTray('case-1', CURRENT).rejection).toBeNull();
  });
});

describe('comparison tray case and context scoping', () => {
  it('clears the draft on a case switch after the explicit notice', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-2' });

    expect(reconcileComparisonTrayContext('case-2', CURRENT)).toBe('case');

    const inCaseTwo = getComparisonTray('case-2', CURRENT);
    expect(inCaseTwo.entries).toHaveLength(0);
    expect(inCaseTwo.notice).toBe(TRAY_CASE_NOTICE);
    // Nothing survives for the original case either: no cross-case mixing.
    expect(getComparisonTray('case-1', CURRENT).entries).toHaveLength(0);
  });

  it('is empty when inspected from another case, without leakage or notice', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });

    const otherCase = getComparisonTray('case-2', CURRENT);
    expect(otherCase.entries).toHaveLength(0);
    expect(otherCase.notice).toBeNull();
    expect(otherCase.rejection).toBeNull();
    // The stored draft itself is still the case-1 one.
    expect(peekComparisonTray()?.caseId).toBe('case-1');
  });

  it('refuses to extend a draft owned by another case instead of replacing it', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });

    const result = addToComparisonTray('case-2', CURRENT, { evidenceId: 'ev-9' });

    expect(result.ok).toBe(false);
    expect(result.reason).toBe('context-mismatch');
    expect(result.message).toBe(TRAY_CASE_MISMATCH_MESSAGE);
    expect(getComparisonTray('case-1', CURRENT).entries.map((e) => e.evidenceId)).toEqual([
      'ev-1',
    ]);
  });

  it('clears the draft on a historical-context change after a separate notice', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });
    const historical = comparisonContextFromSearchParams(
      new URLSearchParams('snapshot=snap-1')
    );

    expect(reconcileComparisonTrayContext('case-1', historical)).toBe('context');

    const snapshotTray = getComparisonTray('case-1', historical);
    expect(snapshotTray.entries).toHaveLength(0);
    expect(snapshotTray.notice).toBe(TRAY_CONTEXT_NOTICE);
  });

  it('keeps the same draft when the case and context still match', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });

    expect(reconcileComparisonTrayContext('case-1', CURRENT)).toBeNull();
    expect(getComparisonTray('case-1', CURRENT).entries).toHaveLength(1);
    expect(getComparisonTray('case-1', CURRENT).notice).toBeNull();
  });

  it('adopts an empty draft quietly, with no notice to explain', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });
    removeFromComparisonTray('case-1', CURRENT, 'ev-1');

    expect(reconcileComparisonTrayContext('case-2', CURRENT)).toBeNull();
    expect(getComparisonTray('case-2', CURRENT).notice).toBeNull();
  });

  it('clears only on an explicit request or a scope change', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });
    clearComparisonTray('case-1', CURRENT, 'Cleared by the operator.');
    expect(getComparisonTray('case-1', CURRENT).entries).toHaveLength(0);
    expect(getComparisonTray('case-1', CURRENT).notice).toBe('Cleared by the operator.');
  });
});

describe('comparison tray session memory', () => {
  it('survives repeated reads (re-render) without rebuilding the draft', () => {
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-2' });

    const first = getComparisonTray('case-1', CURRENT);
    const second = getComparisonTray('case-1', CURRENT);
    expect(second).toBe(first);
    expect(second.entries.map((entry) => entry.evidenceId)).toEqual(['ev-1', 'ev-2']);
  });

  it('notifies subscribers on every change and stops after unsubscribe', () => {
    let calls = 0;
    const unsubscribe = subscribeComparisonTray(() => {
      calls += 1;
    });

    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });
    expect(calls).toBe(1);
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-1' });
    expect(calls).toBe(2);

    unsubscribe();
    addToComparisonTray('case-1', CURRENT, { evidenceId: 'ev-2' });
    expect(calls).toBe(2);
  });

  it('returns an empty, stable snapshot when no draft exists', () => {
    const empty = getComparisonTray('case-1', CURRENT);
    expect(empty.entries).toHaveLength(0);
    expect(getComparisonTray('case-1', CURRENT)).toBe(empty);
  });

  it('derives the historical context from the snapshot selector only', () => {
    expect(comparisonContextFromSearchParams(new URLSearchParams(''))).toBe('current');
    expect(comparisonContextFromSearchParams(new URLSearchParams('snapshot=%20'))).toBe(
      'current'
    );
    expect(comparisonContextFromSearchParams(new URLSearchParams('snapshot=snap-1'))).toBe(
      'snapshot:snap-1'
    );
  });
});
