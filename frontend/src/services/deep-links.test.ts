import { describe, expect, it } from 'vitest';
import {
  buildCaseTabUrl,
  buildCitationUrl,
  buildChangesUrl,
  buildComparisonUrl,
  buildClaimEvidenceUrl,
  buildInspectorUrl,
  parseChangesSelection,
  parseComparisonSelection,
  parseInspectorSelection,
  toChangesSearchParams,
  toComparisonSearchParams,
  toInspectorSearchParams,
} from './deep-links';

describe('deep-link helpers', () => {
  it('URI-encodes every selector exactly once and preserves stable ordering', () => {
    const url = buildInspectorUrl('case/one & two', {
      claimId: 'claim/with space&x',
      evidenceId: 'ev 1',
      captureId: 'cap#2',
      citationId: 'citation?3',
      start: 40,
      length: 20000,
    });

    expect(url).toBe(
      '/cases/case%2Fone%20%26%20two/evidence?claim=claim%2Fwith%20space%26x&evidence=ev%201&capture=cap%232&citation=citation%3F3&start=40&length=20000'
    );
    expect(parseInspectorSelection(new URL(url, 'https://example.test').searchParams)).toEqual({
      claimId: 'claim/with space&x',
      evidenceId: 'ev 1',
      captureId: 'cap#2',
      citationId: 'citation?3',
      start: 40,
      length: 20000,
      snapshotId: null,
    });
  });

  it('carries a pinned snapshot selector only when one is supplied', () => {
    const url = buildInspectorUrl('case-1', {
      claimId: 'claim-1',
      snapshotId: 'snap/1',
    });
    expect(url).toBe(
      '/cases/case-1/evidence?claim=claim-1&snapshot=snap%2F1'
    );
    const parsed = parseInspectorSelection(
      new URL(url, 'https://example.test').searchParams
    );
    expect(parsed.claimId).toBe('claim-1');
    expect(parsed.snapshotId).toBe('snap/1');

    expect(toInspectorSearchParams({ snapshotId: '  ' }).toString()).toBe('');
  });

  it('keeps the legacy claim evidence link byte-identical', () => {
    expect(buildClaimEvidenceUrl('case-1', 'claim/with space&x')).toBe(
      '/cases/case-1/evidence?claim=claim%2Fwith%20space%26x'
    );
  });

  it('builds frozen citation links without requiring an evidence id', () => {
    expect(buildCitationUrl('case-1', 'cit-1')).toBe(
      '/cases/case-1/evidence?citation=cit-1'
    );
    expect(buildCaseTabUrl('case-1', 'claims')).toBe('/cases/case-1/claims');
  });

  it('parses and rejects malformed window offsets without throwing', () => {
    const parsed = parseInspectorSelection(
      new URLSearchParams('claim=%20%20&start=-1&length=0')
    );
    expect(parsed.claimId).toBeNull();
    expect(parsed.start).toBeNull();
    expect(parsed.length).toBeNull();

    const nonInteger = parseInspectorSelection(
      new URLSearchParams('start=1.5&length=abc')
    );
    expect(nonInteger.start).toBeNull();
    expect(nonInteger.length).toBeNull();
  });

  it('serialises start=0 explicitly, distinct from an absent start', () => {
    expect(toInspectorSearchParams({ start: 0 }).toString()).toBe('start=0');
    expect(toInspectorSearchParams({ start: null }).toString()).toBe('');
    expect(toInspectorSearchParams({ start: -5, length: 0 }).toString()).toBe('');
  });
});

describe('comparison deep links', () => {
  it('encodes evidence/capture selectors and the page offset', () => {
    const url = buildComparisonUrl('case/one', {
      leftId: 'ev left',
      rightId: 'ev/right',
      leftCaptureId: 'cap 1',
      rightCaptureId: 'cap#2',
      offset: 25,
    });
    expect(url).toBe(
      '/cases/case%2Fone/compare?left=ev%20left&right=ev%2Fright&leftCapture=cap%201&rightCapture=cap%232&offset=25'
    );
    const parsed = parseComparisonSelection(
      new URL(url, 'https://example.test').searchParams
    );
    expect(parsed).toEqual({
      leftId: 'ev left',
      rightId: 'ev/right',
      leftCaptureId: 'cap 1',
      rightCaptureId: 'cap#2',
      offset: 25,
      limit: null,
    });
  });

  it('rejects malformed offsets but keeps the evidence selectors', () => {
    const parsed = parseComparisonSelection(
      new URLSearchParams('left=ev-a&right=ev-b&offset=-2&limit=abc')
    );
    expect(parsed.leftId).toBe('ev-a');
    expect(parsed.rightId).toBe('ev-b');
    expect(parsed.offset).toBeNull();
    expect(parsed.limit).toBeNull();
  });

  it('serialises offset=0 explicitly and omits absent selectors', () => {
    expect(toComparisonSearchParams({ offset: 0 }).toString()).toBe('offset=0');
    expect(toComparisonSearchParams({ leftId: null, offset: null }).toString()).toBe('');
  });
});

describe('changes deep links', () => {
  it('encodes the run, frozen claim, snapshot and page offset', () => {
    const url = buildChangesUrl('case/one', {
      runId: 'run 1',
      claimId: 'claim/2',
      snapshotId: 'snap 3',
      offset: 25,
    });
    expect(url).toBe(
      '/cases/case%2Fone/changes?run=run%201&claim=claim%2F2&snapshot=snap%203&offset=25'
    );
    expect(
      parseChangesSelection(new URL(url, 'https://example.test').searchParams)
    ).toEqual({
      runId: 'run 1',
      claimId: 'claim/2',
      snapshotId: 'snap 3',
      offset: 25,
      limit: null,
    });
  });

  it('omits absent selectors and rejects malformed offsets', () => {
    expect(toChangesSearchParams({ runId: 'run-1', offset: null }).toString()).toBe(
      'run=run-1'
    );
    const parsed = parseChangesSelection(
      new URLSearchParams('run=run-1&offset=-1&limit=abc')
    );
    expect(parsed.runId).toBe('run-1');
    expect(parsed.offset).toBeNull();
    expect(parsed.limit).toBeNull();
  });
});
