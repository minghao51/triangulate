import { describe, expect, it } from 'vitest';

import { parseNodeId } from './node-id';

describe('parseNodeId click contract', () => {
  it('keeps the complete entity id when it contains hyphens', () => {
    expect(parseNodeId('claim-abc-def-123')).toEqual({
      nodeId: 'abc-def-123',
      nodeType: 'claim',
    });
  });

  it('keeps UUID entity ids intact for every node type', () => {
    const uuid = '3f2c9a7e-1b4d-4c8a-9e6f-0a1b2c3d4e5f';

    expect(parseNodeId(`evidence-${uuid}`)).toEqual({ nodeId: uuid, nodeType: 'evidence' });
    expect(parseNodeId(`party-${uuid}`)).toEqual({ nodeId: uuid, nodeType: 'party' });
  });

  it('keeps unicode entity ids intact', () => {
    expect(parseNodeId('party-组织-α')).toEqual({ nodeId: '组织-α', nodeType: 'party' });
  });

  it('still parses non-hyphenated ids', () => {
    expect(parseNodeId('claim-1')).toEqual({ nodeId: '1', nodeType: 'claim' });
    expect(parseNodeId('evidence-e2')).toEqual({ nodeId: 'e2', nodeType: 'evidence' });
    expect(parseNodeId('party-p3')).toEqual({ nodeId: 'p3', nodeType: 'party' });
  });

  it('rejects an unknown type prefix or a missing entity id', () => {
    expect(parseNodeId('article-abc-def')).toBeNull();
    expect(parseNodeId('claim-')).toBeNull();
    expect(parseNodeId('-abc-def')).toBeNull();
    expect(parseNodeId('no-delimiter')).toBeNull();
  });
});
