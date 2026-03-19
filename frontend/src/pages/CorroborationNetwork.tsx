import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Claim, Evidence, Party } from '../types/backend-models';
import { getClaimsForCase, getEvidenceForCase, getPartiesForCase } from '../services/api';
import { NetworkGraph, type NodeType } from '../components/data-visualization/NetworkGraph';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';

export const CorroborationNetwork: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodeType, setSelectedNodeType] = useState<NodeType | null>(null);

  // Fetch case data
  const { data: claims = [], isLoading: claimsLoading } = useQuery({
    queryKey: ['claims', id],
    queryFn: () => getClaimsForCase(id || ''),
    enabled: !!id,
    refetchInterval: 15000, // 15s polling
  });

  const { data: evidence = [], isLoading: evidenceLoading } = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => getEvidenceForCase(id || ''),
    enabled: !!id,
    refetchInterval: 15000,
  });

  const { data: parties = [], isLoading: partiesLoading } = useQuery({
    queryKey: ['parties', id],
    queryFn: () => getPartiesForCase(id || ''),
    enabled: !!id,
    refetchInterval: 15000,
  });

  const isLoading = claimsLoading || evidenceLoading || partiesLoading;
  const error = null; // Simplified error handling

  // Find selected node data
  const selectedNodeData = React.useMemo(() => {
    if (!selectedNodeId) return null;

    switch (selectedNodeType) {
      case 'claim':
        return claims.find((c) => c.id === selectedNodeId);
      case 'evidence':
        return evidence.find((e) => e.id === selectedNodeId);
      case 'party':
        return parties.find((p) => p.id === selectedNodeId);
      default:
        return null;
    }
  }, [selectedNodeId, selectedNodeType, claims, evidence, parties]);

  const handleNodeClick = (nodeId: string, nodeType: NodeType) => {
    setSelectedNodeId(nodeId);
    setSelectedNodeType(nodeType);
  };

  const handleExportImage = () => {
    // In production, would use html-to-image or similar library
    const graphElement = document.querySelector('.react-flow');
    if (!graphElement) return;

    alert('Export functionality - would save graph as PNG in production');
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#f0f2f5]">Corroboration Network</h1>
          <p className="text-sm text-[#9aa1b3] mt-1">
            Interactive visualization of claim-evidence-party relationships
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExportImage}
            className="px-4 py-2 text-sm font-medium bg-[#0a0a0a] border border-[#2d3340] text-[#f0f2f5] rounded-sm hover:border-[#3f4758] transition-colors"
          >
            Export Image
          </button>
        </div>
      </div>

      {/* Statistics Bar */}
      <div className="grid grid-cols-4 gap-4">
        <Card padding="sm">
          <CardBody className="flex items-center justify-between">
            <div>
              <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Claims</div>
              <div className="text-2xl font-bold text-[#00d4ff]">{claims.length}</div>
            </div>
            <div className="text-3xl">📊</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="flex items-center justify-between">
            <div>
              <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Evidence</div>
              <div className="text-2xl font-bold text-[#00ff9d]">{evidence.length}</div>
            </div>
            <div className="text-3xl">🔗</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="flex items-center justify-between">
            <div>
              <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Parties</div>
              <div className="text-2xl font-bold text-[#a55eea]">{parties.length}</div>
            </div>
            <div className="text-3xl">👥</div>
          </CardBody>
        </Card>
        <Card padding="sm">
          <CardBody className="flex items-center justify-between">
            <div>
              <div className="text-xs text-[#9aa1b3] uppercase tracking-wider">Connections</div>
              <div className="text-2xl font-bold text-[#ffb800]">
                {claims.reduce((sum, c) => sum + c.evidence.length, 0)}
              </div>
            </div>
            <div className="text-3xl">🔀</div>
          </CardBody>
        </Card>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-3 gap-6">
        {/* Network Graph */}
        <div className="col-span-2">
          {isLoading ? (
            <Card>
              <CardBody className="py-16">
                <div className="text-center text-[#9aa1b3]">Loading network data...</div>
              </CardBody>
            </Card>
          ) : error ? (
            <Card>
              <CardBody className="py-16">
                <div className="text-center text-[#ff4757]">Failed to load network data</div>
              </CardBody>
            </Card>
          ) : (
            <NetworkGraph
              claims={claims}
              evidence={evidence}
              parties={parties}
              onNodeClick={handleNodeClick}
              height="700px"
            />
          )}
        </div>

        {/* Inspector Panel */}
        <div className="space-y-4">
          {selectedNodeData ? (
            <>
              {/* Node Details */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="capitalize">{selectedNodeType}</span>
                    <Badge variant={selectedNodeType === 'claim' || selectedNodeType === 'evidence' ? 'confirmed' : 'neutral'}>
                      {selectedNodeType === 'claim' && (selectedNodeData as Claim).verificationStatus}
                      {selectedNodeType === 'evidence' && (selectedNodeData as Evidence).verificationStatus}
                      {selectedNodeType === 'party' && 'Party'}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardBody className="space-y-4">
                  {selectedNodeType === 'claim' && (
                    <>
                      <div>
                        <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Claim</div>
                        <div className="text-sm text-[#f0f2f5]">{(selectedNodeData as Claim).text}</div>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Support</div>
                          <div className="text-sm text-[#00ff9d] font-mono">{(selectedNodeData as Claim).supportCount}</div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Oppose</div>
                          <div className="text-sm text-[#ff4757] font-mono">{(selectedNodeData as Claim).opposeCount}</div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Controversy</div>
                          <div className="text-sm text-[#ffb800] font-mono">
                            {((selectedNodeData as Claim).controversyScore || 0).toFixed(2)}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Diversity</div>
                          <div className="text-sm text-[#00d4ff] font-mono">
                            {(selectedNodeData as Claim).sourceDiversityCount}
                          </div>
                        </div>
                      </div>
                    </>
                  )}

                  {selectedNodeType === 'evidence' && (
                    <>
                      <div>
                        <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Title</div>
                        <div className="text-sm text-[#f0f2f5]">
                          {(selectedNodeData as Evidence).title || 'Untitled'}
                        </div>
                      </div>
                      {(selectedNodeData as Evidence).publisher && (
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Publisher</div>
                          <div className="text-sm text-[#f0f2f5]">{(selectedNodeData as Evidence).publisher}</div>
                        </div>
                      )}
                      {(selectedNodeData as Evidence).originUrl && (
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Source</div>
                          <a
                            href={(selectedNodeData as Evidence).originUrl || undefined}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-[#00d4ff] hover:underline break-all"
                          >
                            {(selectedNodeData as Evidence).originUrl}
                          </a>
                        </div>
                      )}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Source Type</div>
                          <div className="text-sm text-[#f0f2f5] capitalize">
                            {(selectedNodeData as Evidence).sourceType}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Linked Claims</div>
                          <div className="text-sm text-[#00d4ff] font-mono">
                            {(selectedNodeData as Evidence).linkedClaims.length}
                          </div>
                        </div>
                      </div>
                    </>
                  )}

                  {selectedNodeType === 'party' && (
                    <>
                      <div>
                        <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Name</div>
                        <div className="text-sm text-[#f0f2f5]">{(selectedNodeData as Party).name}</div>
                      </div>
                      {(selectedNodeData as Party).description && (
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Description</div>
                          <div className="text-sm text-[#f0f2f5]">{(selectedNodeData as Party).description}</div>
                        </div>
                      )}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Stance</div>
                          <div className="text-sm text-[#f0f2f5] capitalize">
                            {(selectedNodeData as Party).overallStance}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Claims</div>
                          <div className="text-sm text-[#00d4ff] font-mono">
                            {(selectedNodeData as Party).associatedClaimsCount}
                          </div>
                        </div>
                      </div>
                      {(selectedNodeData as Party).aliases.length > 0 && (
                        <div>
                          <div className="text-xs text-[#9aa1b3] uppercase tracking-wider mb-1">Aliases</div>
                          <div className="flex flex-wrap gap-1">
                            {(selectedNodeData as Party).aliases.map((alias, i) => (
                              <Badge key={i} variant="neutral" size="sm">
                                {alias}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </CardBody>
              </Card>

              {/* Actions */}
              <Card>
                <CardBody className="space-y-2">
                  <button className="w-full px-4 py-2 text-sm font-medium bg-[#00d4ff] text-black rounded-sm hover:bg-[#00b8e6] transition-colors">
                    View Full Details
                  </button>
                  <button className="w-full px-4 py-2 text-sm font-medium bg-[#0a0a0a] border border-[#2d3340] text-[#f0f2f5] rounded-sm hover:border-[#3f4758] transition-colors">
                    Find Related
                  </button>
                </CardBody>
              </Card>
            </>
          ) : (
            <Card>
              <CardBody className="py-16">
                <div className="text-center text-[#6c7385]">
                  <div className="text-4xl mb-3">🔍</div>
                  <div className="text-sm">Select a node to view details</div>
                </div>
              </CardBody>
            </Card>
          )}

          {/* Legend */}
          <Card>
            <CardHeader>
              <CardTitle>Legend</CardTitle>
            </CardHeader>
            <CardBody className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm bg-[#00d4ff]" />
                <span className="text-[#f0f2f5]">Claim</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm bg-[#00ff9d]" />
                <span className="text-[#f0f2f5]">Evidence</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm bg-[#a55eea]" />
                <span className="text-[#f0f2f5]">Party</span>
              </div>
              <hr className="border-[#2d3340] my-2" />
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-[#00ff9d]" />
                <span className="text-[#f0f2f5]">Supports</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-[#ff4757]" />
                <span className="text-[#f0f2f5]">Opposes</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-[#6c7385] border-dashed" style={{ borderStyle: 'dashed' }} />
                <span className="text-[#f0f2f5]">Links</span>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default CorroborationNetwork;
