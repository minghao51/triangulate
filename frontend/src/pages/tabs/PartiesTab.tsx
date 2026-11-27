import React, { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Party } from '../../types/backend-models';
import { getPartiesForCase } from '../../services/api';
import { isNotFound } from '../../services/api-error';
import { buildClaimEvidenceUrl } from '../../services/deep-links';
import ReaderState from '../../components/design-system/ReaderState';
import Badge from '../../components/design-system/Badge';
import { PartyCardAccordion } from '../../components/parties/PartyInvestigationPanel';
import './PartiesTab.css';

interface PartiesTabProps {
  caseId: string;
  refreshToken?: number;
}

/**
 * Recorded basis of a party's stance.
 *
 * `isModelInferred` is the only recorded provenance flag the parties reader has:
 * `true` means the party record was model-inferred, `false` means an
 * ingest/bootstrap-confirmed record. It is NOT a human-review marker, so this
 * helper never labels a stance as human-reviewed or verified, and a payload
 * without the flag keeps its basis unknown ("Origin not recorded") instead of
 * defaulting to one or the other.
 */
interface StanceBasis {
  kind: 'model-derived' | 'recorded' | 'unknown';
  label: string;
  origin: string;
}

const describeStanceBasis = (
  party: Pick<Party, 'isModelInferred'>
): StanceBasis => {
  if (typeof party.isModelInferred !== 'boolean') {
    return {
      kind: 'unknown',
      label: 'Stance basis not recorded',
      origin: 'Origin not recorded',
    };
  }
  return party.isModelInferred
    ? { kind: 'model-derived', label: 'Model-derived stance', origin: 'Origin: model-derived record' }
    : { kind: 'recorded', label: 'Recorded stance', origin: 'Origin: recorded party record' };
};

/** At most this many recorded claim links render per party (bounded rows). */
const MAX_CLAIM_LINKS = 5;

interface RecordedClaimRef {
  claimId: string;
  text: string | null;
}

/**
 * Claim links a party actually records. Only `claim_id` values present in the
 * investigation payload are linkable; a payload with missing IDs produces no
 * links at all, so no linkage is invented.
 */
const recordedClaimRefs = (party: Party): RecordedClaimRef[] => {
  const data = party.investigationData;
  if (!data || typeof data !== 'object') return [];

  const seen = new Set<string>();
  const refs: RecordedClaimRef[] = [];
  const buckets = ['claims_supported', 'claims_contested', 'unique_claims'] as const;

  buckets.forEach((bucket) => {
    const list = (data as Record<string, unknown>)[bucket];
    if (!Array.isArray(list)) return;
    list.forEach((item) => {
      if (!item || typeof item !== 'object') return;
      const entry = item as { claim_id?: unknown; claim_text?: unknown };
      const claimId = typeof entry.claim_id === 'string' ? entry.claim_id.trim() : '';
      if (!claimId || seen.has(claimId)) return;
      seen.add(claimId);
      refs.push({
        claimId,
        text: typeof entry.claim_text === 'string' && entry.claim_text.trim() !== ''
          ? entry.claim_text
          : null,
      });
    });
  });

  return refs;
};

/**
 * Parties reader.
 *
 * Keyed by case (`['parties', caseId]`) so cached parties can never be shown for
 * a different case. Each card keeps its own expansion state, and a background
 * refetch only replaces the data — it never remounts the accordions, so an open
 * card and keyboard focus survive a poll. Selection is by stable party ID only.
 */
const PartiesTab: React.FC<PartiesTabProps> = ({ caseId, refreshToken = 0 }) => {
    const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
        queryKey: ['parties', caseId],
        queryFn: () => getPartiesForCase(caseId),
        enabled: Boolean(caseId),
    });

    const lastRefreshToken = useRef(refreshToken);
    useEffect(() => {
        if (lastRefreshToken.current === refreshToken) return;
        lastRefreshToken.current = refreshToken;
        void refetch();
    }, [refreshToken, refetch]);

    const parties = data ?? [];
    const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

    let stateBody: React.ReactNode;
    if (!caseId) {
        stateBody = (
            <ReaderState
                state="not-found"
                title="No case selected"
                description="Choose a case to view its recorded parties."
            />
        );
    } else if (isLoading) {
        stateBody = <ReaderState state="loading" description="Fetching parties recorded for this case." />;
    } else if (error) {
        stateBody = isNotFound(error) ? (
            <ReaderState state="not-found" description="This case has no party records." />
        ) : (
            <ReaderState
                state="network-error"
                description="The recorded parties could not be loaded."
                detail={error instanceof Error ? error.message : null}
                onRetry={() => {
                    void refetch();
                }}
                lastFetched={lastFetched}
            />
        );
    } else if (parties.length === 0) {
        stateBody = (
            <ReaderState
                state="empty"
                description="No parties have been recorded for this case yet."
                lastFetched={lastFetched}
            />
        );
    } else {
        stateBody = (
            <div className="parties-grid">
                {parties.map(party => {
                    const basis = describeStanceBasis(party);
                    const claimRefs = recordedClaimRefs(party);
                    const visibleLinks = claimRefs.slice(0, MAX_CLAIM_LINKS);
                    return (
                        <div
                            key={party.id}
                            className="party-record"
                            data-party-id={party.id}
                            data-stance-basis={basis.kind}
                        >
                            <div className="party-record-stance">
                                <span className="party-record-stance-value">
                                    Stance: {party.overallStance ?? 'not recorded'}
                                </span>
                                <Badge variant="neutral" size="sm">{basis.label}</Badge>
                                <span className="party-record-stance-origin">{basis.origin}</span>
                            </div>
                            <PartyCardAccordion party={party} />
                            {visibleLinks.length > 0 && (
                                <div className="party-record-links">
                                    <span className="party-record-links-label">Recorded claim links</span>
                                    <ul className="party-record-links-list">
                                        {visibleLinks.map(ref => (
                                            <li key={ref.claimId}>
                                                <Link
                                                    className="party-record-link"
                                                    to={buildClaimEvidenceUrl(caseId, ref.claimId)}
                                                >
                                                    {ref.text ?? `Claim ${ref.claimId}`}
                                                </Link>
                                            </li>
                                        ))}
                                    </ul>
                                    {claimRefs.length > visibleLinks.length && (
                                        <span className="party-record-links-more">
                                            +{claimRefs.length - visibleLinks.length} more recorded claims
                                        </span>
                                    )}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        );
    }

    return (
        <div className="parties-container p-base">
            <div className="parties-header">
                <h3>Confirmed & Inferred Parties</h3>
                <p className="subtitle">Entities and their narrative stances detected across the retrieved sources.</p>
            </div>

            {stateBody}
        </div>
    );
};

export default PartiesTab;
