import React, { useCallback, useMemo, useState } from 'react';
import ReactFlow, {
  type Node,
  type Edge,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type NodeTypes,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import type { Claim, Evidence, Party, VerificationStatus } from '../../types/backend-models';
import Card, { CardHeader, CardTitle, CardBody } from '../design-system/Card';

export type NodeType = 'claim' | 'evidence' | 'party';
export type EdgeType = 'supports' | 'opposes' | 'links' | 'mentions';

export interface NetworkGraphProps {
  claims: Claim[];
  evidence: Evidence[];
  parties: Party[];
  onNodeClick?: (nodeId: string, nodeType: NodeType) => void;
  height?: string | number;
  showControls?: boolean;
  className?: string;
}

export interface NetworkGraphFilters {
  nodeTypes: NodeType[];
  verificationStatuses: VerificationStatus[];
  edgeTypes: EdgeType[];
  minConnections?: number;
}

interface CustomNodeData {
  label: string;
  type: NodeType;
  status: VerificationStatus | null;
  count?: number;
  originalData: Claim | Evidence | Party;
}

const getStatusColor = (status: VerificationStatus): string => {
  const colors = {
    confirmed: '#00d4ff',
    probable: '#00ff9d',
    alleged: '#ffb800',
    contested: '#ff6b00',
    debunked: '#ff4757',
    unknown: '#6c7385',
  };
  return colors[status] || colors.unknown;
};

const getNodeTypeColor = (type: NodeType): string => {
  const colors = {
    claim: '#00d4ff',
    evidence: '#00ff9d',
    party: '#a55eea',
  };
  return colors[type];
};

// Custom Node Component
const CustomNode: React.FC<{ data: CustomNodeData }> = ({ data }) => {
  const { label, type, status, count } = data;

  const bgColor = getNodeTypeColor(type);
  const statusColor = status ? getStatusColor(status) : bgColor;

  return (
    <div
      style={{
        background: '#0a0a0a',
        border: `1px solid ${statusColor}`,
        borderRadius: '2px',
        padding: '8px 12px',
        minWidth: '120px',
        maxWidth: '180px',
        boxShadow: `0 0 10px ${statusColor}20`,
      }}
      className="network-node"
    >
      <div className="flex items-center gap-2 mb-1">
        <div
          style={{
            width: '8px',
            height: '8px',
            backgroundColor: statusColor,
            borderRadius: '1px',
          }}
        />
        <span
          style={{
            color: statusColor,
            fontSize: '10px',
            textTransform: 'uppercase',
            fontWeight: 600,
            letterSpacing: '0.5px',
          }}
        >
          {type}
        </span>
      </div>
      <div
        style={{
          color: '#f0f2f5',
          fontSize: '12px',
          fontWeight: 500,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </div>
      {count !== undefined && (
        <div
          style={{
            color: '#9aa1b3',
            fontSize: '10px',
            marginTop: '4px',
          }}
        >
          {count} {count === 1 ? 'connection' : 'connections'}
        </div>
      )}
    </div>
  );
};

const nodeTypes: NodeTypes = {
  custom: CustomNode,
};

const createGridPosition = (
  index: number,
  columnOffset: number,
  columns: number = 2
): { x: number; y: number } => ({
  x: columnOffset + (index % columns) * 220,
  y: Math.floor(index / columns) * 140,
});

export const NetworkGraph: React.FC<NetworkGraphProps> = ({
  claims,
  evidence,
  parties,
  onNodeClick,
  height = '600px',
  showControls = true,
  className = '',
}) => {
  const [filters, setFilters] = useState<NetworkGraphFilters>({
    nodeTypes: ['claim', 'evidence', 'party'],
    verificationStatuses: ['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'],
    edgeTypes: ['supports', 'opposes', 'links', 'mentions'],
    minConnections: 0,
  });

  // Transform data to React Flow format
  const { initialNodes, initialEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    // Create claim nodes
    claims.forEach((claim, index) => {
      if (!filters.nodeTypes.includes('claim')) return;
      if (!filters.verificationStatuses.includes(claim.verificationStatus)) return;
      if (claim.supportCount + claim.opposeCount < (filters.minConnections || 0)) return;

      nodes.push({
        id: `claim-${claim.id}`,
        type: 'custom',
        position: createGridPosition(index, 40),
        data: {
          label: claim.text.substring(0, 50) + (claim.text.length > 50 ? '...' : ''),
          type: 'claim',
          status: claim.verificationStatus,
          count: claim.supportCount + claim.opposeCount,
          originalData: claim,
        },
      });
    });

    // Create evidence nodes
    evidence.forEach((ev, index) => {
      if (!filters.nodeTypes.includes('evidence')) return;
      if (!filters.verificationStatuses.includes(ev.verificationStatus)) return;
      if (ev.linkedClaims.length < (filters.minConnections || 0)) return;

      nodes.push({
        id: `evidence-${ev.id}`,
        type: 'custom',
        position: createGridPosition(index, 520),
        data: {
          label: ev.title || ev.originUrl || 'Unknown',
          type: 'evidence',
          status: ev.verificationStatus,
          count: ev.linkedClaims.length,
          originalData: ev,
        },
      });
    });

    // Create party nodes
    parties.forEach((party, index) => {
      if (!filters.nodeTypes.includes('party')) return;
      if (party.associatedClaimsCount < (filters.minConnections || 0)) return;

      nodes.push({
        id: `party-${party.id}`,
        type: 'custom',
        position: createGridPosition(index, 280),
        data: {
          label: party.name,
          type: 'party',
          status: null,
          count: party.associatedClaimsCount,
          originalData: party,
        },
      });
    });

    // Create edges from claim-evidence links
    claims.forEach((claim) => {
      if (!filters.nodeTypes.includes('claim')) return;
      if (!filters.verificationStatuses.includes(claim.verificationStatus)) return;

      claim.evidence.forEach((evLink) => {
        const evidenceId = `evidence-${evLink.id}`;
        const claimId = `claim-${claim.id}`;

        // Check if both nodes exist
        if (nodes.find((n) => n.id === evidenceId) && nodes.find((n) => n.id === claimId)) {
          const relation = evLink.relation.toLowerCase();
          let edgeType: EdgeType = 'links';

          if (relation.includes('support') || relation.includes('confirm')) {
            edgeType = 'supports';
          } else if (relation.includes('oppose') || relation.includes('contradict')) {
            edgeType = 'opposes';
          }

          if (!filters.edgeTypes.includes(edgeType)) return;

          edges.push({
            id: `${claimId}-${evidenceId}`,
            source: claimId,
            target: evidenceId,
            type: 'smoothstep',
            animated: edgeType === 'supports',
            style: {
              stroke: edgeType === 'supports' ? '#00ff9d' : edgeType === 'opposes' ? '#ff4757' : '#6c7385',
              strokeWidth: 1,
            },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: edgeType === 'supports' ? '#00ff9d' : edgeType === 'opposes' ? '#ff4757' : '#6c7385',
            },
            data: { type: edgeType },
          });
        }
      });
    });

    // Create edges from party-claim associations
    parties.forEach((party) => {
      if (!filters.nodeTypes.includes('party')) return;

      const partyId = `party-${party.id}`;
      const partyNode = nodes.find((n) => n.id === partyId);
      if (!partyNode) return;

      // Find claims associated with this party (simplified - in real app, this would come from backend)
      claims.forEach((claim) => {
        if (!filters.nodeTypes.includes('claim')) return;
        if (!filters.verificationStatuses.includes(claim.verificationStatus)) return;

        const claimId = `claim-${claim.id}`;
        const claimNode = nodes.find((n) => n.id === claimId);
        if (!claimNode) return;

        // Simple heuristic: if party name appears in claim text
        if (claim.text.toLowerCase().includes(party.name.toLowerCase())) {
          if (!filters.edgeTypes.includes('mentions')) return;

          edges.push({
            id: `${partyId}-${claimId}`,
            source: partyId,
            target: claimId,
            type: 'smoothstep',
            animated: false,
            style: {
              stroke: '#a55eea',
              strokeWidth: 1,
              strokeDasharray: '5,5',
            },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: '#a55eea',
            },
            data: { type: 'mentions' },
          });
        }
      });
    });

    return { initialNodes: nodes, initialEdges: edges };
  }, [claims, evidence, parties, filters]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (params: Edge | Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const onNodeClickHandler = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const [nodeType, nodeId] = node.id.split('-');
      if (onNodeClick) {
        onNodeClick(nodeId, nodeType as NodeType);
      }
    },
    [onNodeClick]
  );

  const toggleNodeType = (type: NodeType) => {
    setFilters((prev) => ({
      ...prev,
      nodeTypes: prev.nodeTypes.includes(type)
        ? prev.nodeTypes.filter((t) => t !== type)
        : [...prev.nodeTypes, type],
    }));
  };

  const toggleVerificationStatus = (status: VerificationStatus) => {
    setFilters((prev) => ({
      ...prev,
      verificationStatuses: prev.verificationStatuses.includes(status)
        ? prev.verificationStatuses.filter((s) => s !== status)
        : [...prev.verificationStatuses, status],
    }));
  };

  const toggleEdgeType = (type: EdgeType) => {
    setFilters((prev) => ({
      ...prev,
      edgeTypes: prev.edgeTypes.includes(type)
        ? prev.edgeTypes.filter((t) => t !== type)
        : [...prev.edgeTypes, type],
    }));
  };

  const handleExport = useCallback(() => {
    // Export as image
    const element = document.querySelector('.react-flow');
    if (!element) return;

    // Simple export - in production, would use html-to-image or similar
    const dataStr = JSON.stringify({ nodes, edges }, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `network-graph-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }, [nodes, edges]);

  return (
    <div className={className} style={{ height }}>
      <Card className="h-full flex flex-col">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Corroboration Network</CardTitle>
            <button
              onClick={handleExport}
              className="px-3 py-1.5 text-xs font-medium bg-[#00d4ff] text-black rounded-sm hover:bg-[#00b8e6] transition-colors"
            >
              Export Data
            </button>
          </div>
        </CardHeader>

        <CardBody className="flex-1 flex gap-4 overflow-hidden">
          {/* Filters Panel */}
          <div className="w-48 flex-shrink-0 space-y-4 overflow-y-auto">
            <div>
              <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                Node Types
              </h4>
              <div className="space-y-1">
                {(['claim', 'evidence', 'party'] as NodeType[]).map((type) => (
                  <label key={type} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={filters.nodeTypes.includes(type)}
                      onChange={() => toggleNodeType(type)}
                      className="w-3 h-3 rounded-sm"
                    />
                    <span className="capitalize text-[#f0f2f5]">{type}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                Verification Status
              </h4>
              <div className="space-y-1">
                {(['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'] as VerificationStatus[]).map(
                  (status) => (
                    <label key={status} className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={filters.verificationStatuses.includes(status)}
                        onChange={() => toggleVerificationStatus(status)}
                        className="w-3 h-3 rounded-sm"
                      />
                      <div className="flex items-center gap-1.5">
                        <div
                          className="w-2 h-2 rounded-sm"
                          style={{ backgroundColor: getStatusColor(status) }}
                        />
                        <span className="text-[#f0f2f5] capitalize">{status}</span>
                      </div>
                    </label>
                  )
                )}
              </div>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                Edge Types
              </h4>
              <div className="space-y-1">
                {(['supports', 'opposes', 'links', 'mentions'] as EdgeType[]).map((type) => (
                  <label key={type} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={filters.edgeTypes.includes(type)}
                      onChange={() => toggleEdgeType(type)}
                      className="w-3 h-3 rounded-sm"
                    />
                    <span className="capitalize text-[#f0f2f5]">{type}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                Min Connections
              </h4>
              <input
                type="range"
                min="0"
                max="10"
                value={filters.minConnections || 0}
                onChange={(e) =>
                  setFilters((prev) => ({ ...prev, minConnections: parseInt(e.target.value) }))
                }
                className="w-full"
              />
              <div className="text-xs text-[#9aa1b3] mt-1">{filters.minConnections || 0}+</div>
            </div>
          </div>

          {/* Graph Area */}
          <div className="flex-1 border border-[#2d3340] rounded-sm overflow-hidden">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={onNodeClickHandler}
              nodeTypes={nodeTypes}
              fitView
              attributionPosition="bottom-left"
              style={{
                backgroundColor: '#0a0a0a',
              }}
            >
              <Background
                variant={BackgroundVariant.Dots}
                gap={16}
                size={1}
                color="#2d3340"
              />
              {showControls && (
                <Controls />
              )}
            </ReactFlow>
          </div>
        </CardBody>
      </Card>
    </div>
  );
};

export default NetworkGraph;
