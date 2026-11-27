export type NodeType = 'claim' | 'evidence' | 'party';

const NODE_TYPES: readonly NodeType[] = ['claim', 'evidence', 'party'];

/**
 * Split a React Flow node id back into its entity type and complete entity id.
 * Only the first delimiter separates the type prefix, so hyphenated, UUID and
 * unicode entity ids survive the click round trip unchanged.
 */
export const parseNodeId = (
  compositeId: string
): { nodeId: string; nodeType: NodeType } | null => {
  const separator = compositeId.indexOf('-');
  if (separator <= 0) return null;
  const nodeType = compositeId.slice(0, separator);
  const nodeId = compositeId.slice(separator + 1);
  if (!nodeId || !NODE_TYPES.includes(nodeType as NodeType)) return null;
  return { nodeId, nodeType: nodeType as NodeType };
};
