import { describe, expect, it } from 'vitest';

import {
  codePointLength,
  codePointSlice,
  resolveInspectorDiagnostic,
  splitHighlight,
} from './inspector-utils';

/**
 * Offsets on the wire are Unicode **code points** (Python slice semantics),
 * while JavaScript string indices are UTF-16 code units. These tests pin the
 * code-point behaviour for astral characters and combining marks so a window
 * can never be off by the number of surrogate pairs it contains.
 */
describe('codePointSlice', () => {
  it('slices a BMP window by code points', () => {
    expect(codePointSlice('abcdefgh', 2, 3)).toBe('cde');
  });

  it('slices astral characters as single code points', () => {
    // 😀 is one code point but two UTF-16 code units.
    const text = 'a😀b🧪c';
    expect(codePointLength(text)).toBe(5);
    expect(codePointSlice(text, 1, 1)).toBe('😀');
    expect(codePointSlice(text, 1, 3)).toBe('😀b🧪');
    // A UTF-16 slice with the same indexes would split the surrogate pair.
    expect(text.slice(1, 2)).not.toBe('😀');
  });

  it('slices Deseret letters (surrogate pairs) without splitting them', () => {
    // U+10400 and U+10401 are astral letters, one code point each.
    const text = 'x\u{10400}\u{10401}y';
    expect(codePointLength(text)).toBe(4);
    expect(codePointSlice(text, 1, 2)).toBe('\u{10400}\u{10401}');
    expect(Array.from(codePointSlice(text, 1, 2))).toHaveLength(2);
  });

  it('counts a combining mark as its own code point, like Python', () => {
    // "e" + U+0301 COMBINING ACUTE ACCENT = two code points, one grapheme.
    const text = 'e\u0301te\u0301';
    expect(text).toHaveLength(5); // five UTF-16 units here…
    expect(codePointLength(text)).toBe(5); // …and five code points.
    expect(codePointSlice(text, 0, 2)).toBe('e\u0301');
    expect(Array.from(codePointSlice(text, 0, 2))).toHaveLength(2);
    expect(codePointSlice(text, 3, 2)).toBe('e\u0301');
    // A grapheme-cluster slice would have returned one "character" instead.
    expect(codePointSlice(text, 0, 1)).toBe('e');
    expect(codePointSlice(text, 1, 1)).toBe('\u0301');
  });

  it('returns a slice whose code-point length equals the requested length', () => {
    // Five code points; a three-code-point window from index 1 leaves four.
    const text = '😀😀😀東😀';
    for (const length of [1, 2, 3, 4]) {
      const window = codePointSlice(text, 1, length);
      expect(Array.from(window)).toHaveLength(length);
    }
  });

  it('clamps at the end of the text and rejects non-positive lengths', () => {
    expect(codePointSlice('abc', 2, 5)).toBe('c');
    expect(codePointSlice('abc', 5, 2)).toBe('');
    expect(codePointSlice('abc', 0, 0)).toBe('');
    expect(codePointSlice('abc', 0, -1)).toBe('');
    expect(codePointSlice('abc', -3, 2)).toBe('ab');
  });

  it('never normalises: NFKC- and case-different text does not match offsets', () => {
    // U+FB01 LATIN SMALL LIGATURE FI is not "fi"; offsets stay exact.
    expect(codePointSlice('\uFB01x', 0, 1)).toBe('\uFB01');
    expect(codePointSlice('\uFB01x', 0, 1)).not.toBe('fi');
    expect(codePointSlice('ABC', 0, 3)).toBe('ABC');
  });
});

describe('splitHighlight', () => {
  it('highlights exactly the requested astral window', () => {
    const text = 'abc😀😀😀def';
    const start = 3;
    const length = 3;
    const quote = '😀😀😀';

    const parts = splitHighlight(text, 0, quote, start, start + length);

    expect(parts).not.toBeNull();
    expect(parts?.match).toBe(quote);
    expect(Array.from(parts?.match ?? '')).toHaveLength(length);
    expect(parts?.before).toBe('abc');
    expect(parts?.after).toBe('def');
  });

  it('respects a non-zero window start and keeps combining marks intact', () => {
    const text = 'e\u0301xyz';
    const quote = 'e\u0301';
    const parts = splitHighlight(text, 0, quote, 0, 2);

    expect(parts?.match).toBe('e\u0301');
    expect(Array.from(parts?.match ?? '')).toHaveLength(2);
    expect(parts?.after).toBe('xyz');
  });

  it('returns null instead of a fuzzy match when the slice differs', () => {
    expect(splitHighlight('abcdef', 0, 'bcd', 1, 4)).not.toBeNull();
    expect(splitHighlight('abcdef', 0, 'ABCD', 1, 4)).toBeNull();
    expect(splitHighlight('aeiou', 0, 'ei', 0, 2)).toBeNull();
    expect(splitHighlight('abcdef', 0, 'bcd', 4, 7)).toBeNull();
    expect(splitHighlight('abcdef', 0, null, 1, 4)).toBeNull();
    expect(splitHighlight('abcdef', 0, 'bcd', null, 4)).toBeNull();
  });
});

describe('resolveInspectorDiagnostic', () => {
  it('maps each recorded status to its own stable attribute', () => {
    expect(resolveInspectorDiagnostic('exact', 'quote').attribute).toBe(
      'inspector-exact'
    );
    expect(resolveInspectorDiagnostic('not_provided', null).attribute).toBe(
      'inspector-missing-quotation'
    );
    expect(resolveInspectorDiagnostic('source_unavailable', 'q').attribute).toBe(
      'inspector-source-unavailable'
    );
    expect(resolveInspectorDiagnostic('ambiguous', 'q').attribute).toBe(
      'inspector-ambiguous'
    );
    expect(resolveInspectorDiagnostic('no_match', 'q').attribute).toBe(
      'inspector-no-match'
    );
    expect(resolveInspectorDiagnostic('legacy_unknown', 'q').attribute).toBe(
      'inspector-legacy'
    );
  });

  it('treats missing or unrecognised statuses as legacy, never as a match', () => {
    for (const status of [undefined, null, '', 'something_else']) {
      const diagnostic = resolveInspectorDiagnostic(status, 'quote');
      expect(diagnostic.state).toBe('legacy');
      expect(diagnostic.attribute).toBe('inspector-legacy');
    }
  });

  it('does not claim an exact match without a recorded quotation', () => {
    expect(resolveInspectorDiagnostic('exact', null).state).toBe('legacy');
    expect(resolveInspectorDiagnostic('exact', '').state).toBe('legacy');
  });

  it('gives every state distinct, non-empty text', () => {
    const diagnostics = [
      resolveInspectorDiagnostic('exact', 'q'),
      resolveInspectorDiagnostic('not_provided', null),
      resolveInspectorDiagnostic('source_unavailable', 'q'),
      resolveInspectorDiagnostic('ambiguous', 'q'),
      resolveInspectorDiagnostic('no_match', 'q'),
      resolveInspectorDiagnostic(undefined, null),
    ];

    expect(new Set(diagnostics.map((item) => item.attribute)).size).toBe(6);
    expect(new Set(diagnostics.map((item) => item.label)).size).toBe(6);
    expect(new Set(diagnostics.map((item) => item.message)).size).toBe(6);
    for (const diagnostic of diagnostics) {
      expect(diagnostic.label.trim()).not.toBe('');
      expect(diagnostic.message.trim()).not.toBe('');
    }
  });
});
