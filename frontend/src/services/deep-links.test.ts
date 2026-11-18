import { describe, expect, it } from 'vitest';
import {
  buildCaseTabUrl,
  buildCitationUrl,
  buildClaimEvidenceUrl,
  buildInspectorUrl,
  parseInspectorSelection,
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
    });
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
