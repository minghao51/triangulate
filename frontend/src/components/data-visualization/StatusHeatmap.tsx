import React, { useState, useMemo } from 'react';
import type { Claim, Evidence, VerificationStatus } from '../../types/backend-models';
import Card, { CardHeader, CardTitle, CardBody } from '../design-system/Card';

export interface StatusHeatmapProps {
  claims: Claim[];
  evidence: Evidence[];
  onCellClick?: (claimId: string, evidenceId: string) => void;
  className?: string;
}

const getStatusColor = (status: VerificationStatus): string => {
  const colors = {
    confirmed: 'rgba(0, 212, 255, 0.8)',
    probable: 'rgba(0, 255, 157, 0.8)',
    alleged: 'rgba(255, 184, 0, 0.8)',
    contested: 'rgba(255, 107, 0, 0.8)',
    debunked: 'rgba(255, 71, 87, 0.8)',
    unknown: 'rgba(108, 115, 133, 0.8)',
  };
  return colors[status] || colors.unknown;
};

const getStatusBorder = (status: VerificationStatus): string => {
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

interface HeatmapCell {
  claimId: string;
  evidenceId: string;
  status: VerificationStatus;
  hasLink: boolean;
}

export const StatusHeatmap: React.FC<StatusHeatmapProps> = ({
  claims,
  evidence,
  onCellClick,
  className = '',
}) => {
  const [filters, setFilters] = useState({
    claimStatuses: ['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'] as VerificationStatus[],
    evidenceStatuses: ['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'] as VerificationStatus[],
  });

  const [selectedCell, setSelectedCell] = useState<{ claimId: string; evidenceId: string } | null>(null);
  const [hoveredCell, setHoveredCell] = useState<{ claimId: string; evidenceId: string } | null>(null);

  // Build heatmap matrix
  const { filteredClaims, filteredEvidence, cells } = useMemo(() => {
    const filteredClaims = claims.filter((c) => filters.claimStatuses.includes(c.verificationStatus));
    const filteredEvidence = evidence.filter((e) => filters.evidenceStatuses.includes(e.verificationStatus));

    // Build evidence lookup map
    const evidenceMap = new Map<string, Evidence>();
    filteredEvidence.forEach((ev) => evidenceMap.set(ev.id, ev));

    // Create cell matrix
    const cells: HeatmapCell[] = [];

    filteredClaims.forEach((claim) => {
      filteredEvidence.forEach((ev) => {
        // Check if this evidence is linked to this claim
        const linkedEvidence = claim.evidence.find((e) => e.id === ev.id);
        const hasLink = !!linkedEvidence;

        // Determine cell status based on link and verification
        let status: VerificationStatus = 'unknown';

        if (hasLink) {
          // Use the verification status of the claim or evidence, whichever is more certain
          const statusPriority = ['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'];
          const claimStatusIndex = statusPriority.indexOf(claim.verificationStatus);
          const evidenceStatusIndex = statusPriority.indexOf(ev.verificationStatus);

          status = claimStatusIndex <= evidenceStatusIndex ? claim.verificationStatus : ev.verificationStatus;
        }

        cells.push({
          claimId: claim.id,
          evidenceId: ev.id,
          status,
          hasLink,
        });
      });
    });

    return { filteredClaims, filteredEvidence, cells };
  }, [claims, evidence, filters]);

  const handleCellClick = (claimId: string, evidenceId: string) => {
    setSelectedCell({ claimId, evidenceId });
    if (onCellClick) onCellClick(claimId, evidenceId);
  };

  const toggleClaimStatus = (status: VerificationStatus) => {
    setFilters((prev) => ({
      ...prev,
      claimStatuses: prev.claimStatuses.includes(status)
        ? prev.claimStatuses.filter((s) => s !== status)
        : [...prev.claimStatuses, status],
    }));
  };

  const toggleEvidenceStatus = (status: VerificationStatus) => {
    setFilters((prev) => ({
      ...prev,
      evidenceStatuses: prev.evidenceStatuses.includes(status)
        ? prev.evidenceStatuses.filter((s) => s !== status)
        : [...prev.evidenceStatuses, status],
    }));
  };

  const getCellData = (claimId: string, evidenceId: string) => {
    return cells.find((c) => c.claimId === claimId && c.evidenceId === evidenceId);
  };

  const stats = useMemo(() => {
    const linkedCells = cells.filter((c) => c.hasLink);
    return {
      total: cells.length,
      linked: linkedCells.length,
      byStatus: linkedCells.reduce((acc, cell) => {
        acc[cell.status] = (acc[cell.status] || 0) + 1;
        return acc;
      }, {} as Record<VerificationStatus, number>),
    };
  }, [cells]);

  return (
    <div className={className}>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Claim-Evidence Verification Matrix</CardTitle>
            <div className="text-sm text-[#9aa1b3]">
              {stats.linked} / {stats.total} connections
            </div>
          </div>
        </CardHeader>

        <CardBody>
          <div className="flex gap-4">
            {/* Filters Panel */}
            <div className="w-48 flex-shrink-0 space-y-4">
              <div>
                <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                  Claim Status
                </h4>
                <div className="space-y-1">
                  {(['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'] as VerificationStatus[]).map(
                    (status) => (
                      <label key={status} className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={filters.claimStatuses.includes(status)}
                          onChange={() => toggleClaimStatus(status)}
                          className="w-3 h-3 rounded-sm"
                        />
                        <div className="flex items-center gap-1.5">
                          <div
                            className="w-2 h-2 rounded-sm"
                            style={{ backgroundColor: getStatusBorder(status) }}
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
                  Evidence Status
                </h4>
                <div className="space-y-1">
                  {(['confirmed', 'probable', 'alleged', 'contested', 'debunked', 'unknown'] as VerificationStatus[]).map(
                    (status) => (
                      <label key={status} className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={filters.evidenceStatuses.includes(status)}
                          onChange={() => toggleEvidenceStatus(status)}
                          className="w-3 h-3 rounded-sm"
                        />
                        <div className="flex items-center gap-1.5">
                          <div
                            className="w-2 h-2 rounded-sm"
                            style={{ backgroundColor: getStatusBorder(status) }}
                          />
                          <span className="text-[#f0f2f5] capitalize">{status}</span>
                        </div>
                      </label>
                    )
                  )}
                </div>
              </div>

              <div className="pt-4 border-t border-[#2d3340]">
                <h4 className="text-xs font-semibold text-[#9aa1b3] uppercase tracking-wider mb-2">
                  Link Statistics
                </h4>
                <div className="space-y-2 text-sm">
                  {Object.entries(stats.byStatus).map(([status, count]) => (
                    <div key={status} className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <div
                          className="w-2 h-2 rounded-sm"
                          style={{ backgroundColor: getStatusBorder(status as VerificationStatus) }}
                        />
                        <span className="text-[#f0f2f5] capitalize">{status}</span>
                      </div>
                      <span className="text-[#00d4ff] font-mono">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Heatmap Grid */}
            <div className="flex-1 overflow-auto">
              {filteredClaims.length === 0 || filteredEvidence.length === 0 ? (
                <div className="flex items-center justify-center h-64 text-[#6c7385]">
                  No data to display with current filters
                </div>
              ) : (
                <div className="inline-block min-w-full">
                  {/* Header row - Evidence */}
                  <div className="flex border-b border-[#2d3340]">
                    <div className="w-32 flex-shrink-0 p-2 text-xs font-semibold text-[#9aa1b3] bg-[#0a0a0a] sticky left-0 z-10">
                      Claims \ Evidence
                    </div>
                    {filteredEvidence.map((ev) => (
                      <div
                        key={ev.id}
                        className="w-8 flex-shrink-0 p-1 text-center"
                        style={{
                          backgroundColor: selectedCell?.evidenceId === ev.id ? '#1a1a1a' : '#0a0a0a',
                        }}
                      >
                        <div
                          className="w-2 h-2 mx-auto rounded-sm"
                          style={{ backgroundColor: getStatusBorder(ev.verificationStatus) }}
                          title={`${ev.title || ev.originUrl} (${ev.verificationStatus})`}
                        />
                      </div>
                    ))}
                  </div>

                  {/* Data rows */}
                  <div>
                    {filteredClaims.map((claim) => (
                      <div key={claim.id} className="flex border-b border-[#1a1a1a]">
                        {/* Claim label */}
                        <div
                          className="w-32 flex-shrink-0 p-2 text-xs truncate bg-[#0a0a0a] sticky left-0 z-10"
                          style={{
                            backgroundColor: selectedCell?.claimId === claim.id ? '#1a1a1a' : '#0a0a0a',
                          }}
                          title={claim.text}
                        >
                          <div className="flex items-center gap-2">
                            <div
                              className="w-2 h-2 rounded-sm flex-shrink-0"
                              style={{ backgroundColor: getStatusBorder(claim.verificationStatus) }}
                            />
                            <span className="truncate">{claim.text.substring(0, 20)}...</span>
                          </div>
                        </div>

                        {/* Cells */}
                        {filteredEvidence.map((ev) => {
                          const cell = getCellData(claim.id, ev.id);
                          if (!cell) return null;

                          const isSelected =
                            selectedCell?.claimId === claim.id && selectedCell?.evidenceId === ev.id;
                          const isHovered =
                            hoveredCell?.claimId === claim.id && hoveredCell?.evidenceId === ev.id;

                          return (
                            <div
                              key={ev.id}
                              className={`
                                w-8 h-8 flex-shrink-0 cursor-pointer transition-all duration-150
                                ${cell.hasLink ? 'hover:scale-110' : ''}
                              `}
                              onClick={() => handleCellClick(claim.id, ev.id)}
                              onMouseEnter={() => setHoveredCell({ claimId: claim.id, evidenceId: ev.id })}
                              onMouseLeave={() => setHoveredCell(null)}
                              style={{
                                backgroundColor: cell.hasLink ? getStatusColor(cell.status) : '#0a0a0a',
                                border: isSelected ? '2px solid #00d4ff' : isHovered ? '1px solid #3f4758' : '1px solid #1a1a1a',
                              }}
                              title={
                                cell.hasLink
                                  ? `${claim.text.substring(0, 30)}... ↔ ${ev.title || ev.originUrl}\nStatus: ${cell.status}`
                                  : 'No link'
                              }
                            />
                          );
                        })}
                      </div>
                    ))}
                  </div>

                  {/* Legend */}
                  <div className="flex gap-4 pt-4 border-t border-[#2d3340] mt-4">
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 border border-[#2d3340] bg-[#0a0a0a]" />
                      <span className="text-xs text-[#9aa1b3]">No Link</span>
                    </div>
                    {(['confirmed', 'probable', 'alleged', 'contested', 'debunked'] as VerificationStatus[]).map(
                      (status) => (
                        <div key={status} className="flex items-center gap-2">
                          <div
                            className="w-4 h-4"
                            style={{ backgroundColor: getStatusColor(status) }}
                          />
                          <span className="text-xs text-[#9aa1b3] capitalize">{status}</span>
                        </div>
                      )
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
};

export default StatusHeatmap;
