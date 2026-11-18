import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  GitCompare,
  RefreshCw,
  X,
} from 'lucide-react';
import type {
  Comparison,
  ComparisonClaimSide,
  ComparisonPassage,
  ComparisonRow,
  ComparisonSide,
  Evidence,
  EvidenceDetail,
} from '../../types/backend-models';
import {
  getComparison,
  getEvidenceDetail,
  getEvidenceForCase,
} from '../../services/api';
import { isNotFound } from '../../services/api-error';
import {
  buildInspectorUrl,
  parseComparisonSelection,
  toComparisonSearchParams,
  type ComparisonSelection,
} from '../../services/deep-links';
import {
  alignmentLabel,
  formatTimestamp,
  knownOrUnknown,
  relationLabel,
  safeExternalUrl,
} from '../../components/inspector/inspector-utils';
import './CompareTab.css';

const PAGE_SIZE = 25;
const CONTEXT_BEFORE = 200;
const RELATIONSHIP_WARNING =
  'Reported-by relationships describe what a source says. They are not corroboration.';

const STATUS_LABELS: Record<ComparisonRow['status'], string> = {
  shared: 'Reported in both extractions',
  left_only: 'Extracted only on the left',
  right_only: 'Extracted only on the right',
};

const LINKAGE_LABELS: Record<string, string> = {
  available: 'Capture-linked claims available',
  historical_unavailable: 'Historical claim alignment unavailable',
  unattributed_legacy: 'Legacy links without a capture',
  empty: 'No claims linked to this capture',
};

const DEPENDENCY_REASON_LABELS: Record<string, string> = {
  same_source_url: 'same normalized source URL',
  same_publisher: 'same publisher key',
  identical_normalized_capture: 'identical long captured text',
  same_case_article: 'same case article',
  documented_common_origin: 'documented common origin',
};

function dependencyReasonLabel(reason: string): string {
  return DEPENDENCY_REASON_LABELS[reason] ?? reason;
}

interface CompareTabProps {
  caseId: string;
}

function shortId(value: string | null | undefined): string {
  if (!value) return 'unknown';
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function evidenceLabel(evidence: Evidence): string {
  const title = evidence.title?.trim() || `Evidence ${shortId(evidence.id)}`;
  return evidence.publisher ? `${title} — ${evidence.publisher}` : title;
}

function captureOptions(
  detail: EvidenceDetail | undefined,
  side: ComparisonSide | undefined,
  selectedId: string | null
): Array<{ id: string; label: string }> {
  if (detail?.captures.length) {
    return detail.captures.map((capture) => ({
      id: capture.id,
      label: `${capture.isCurrent ? 'Current' : 'Older'} · ${shortId(capture.id)} · ${capture.charLength} cp`,
    }));
  }
  if (side) {
    return [
      {
        id: side.captureId,
        label: `Resolved · ${shortId(side.captureId)} · ${side.charLength} cp`,
      },
    ];
  }
  if (selectedId) {
    return [{ id: selectedId, label: `Selected · ${shortId(selectedId)}` }];
  }
  return [];
}

const ExternalSourceLink: React.FC<{
  url: string | null | undefined;
  label: string;
}> = ({ url, label }) => {
  const safeUrl = safeExternalUrl(url);
  if (!safeUrl) {
    return (
      <span className="compare-link-unavailable">
        {label}: {url ? 'not a safe external URL' : 'Unknown'}
      </span>
    );
  }
  return (
    <a
      className="compare-source-link"
      href={safeUrl}
      target="_blank"
      rel="noopener noreferrer"
    >
      <ExternalLink size={14} /> {label}
    </a>
  );
};

const SourcePanel: React.FC<{ side: ComparisonSide; label: string }> = ({
  side,
  label,
}) => {
  const scope = side.analysisScope;
  const scopeText = scope
    ? [
        scope.status ? `status ${scope.status}` : null,
        scope.startChar !== null && scope.endChar !== null
          ? `code points ${scope.startChar}–${scope.endChar}`
          : null,
        scope.bodyCharCount !== null
          ? `of ${scope.bodyCharCount} body code points`
          : null,
        scope.inputLimit !== null ? `input limit ${scope.inputLimit}` : null,
      ]
        .filter(Boolean)
        .join(' · ')
    : 'Unknown';
  const linkage = LINKAGE_LABELS[side.coverage.claimLinkageStatus] ?? side.coverage.claimLinkageStatus;

  return (
    <section className="compare-panel glass-panel" aria-labelledby={`compare-${label}-heading`}>
      <div className="compare-panel-heading">
        <span className="compare-side-label">{label}</span>
        <h4 id={`compare-${label}-heading`}>
          {side.title?.trim() || `Evidence ${shortId(side.evidenceId)}`}
        </h4>
        <p className="compare-panel-publisher">
          {knownOrUnknown(side.publisher)} · {knownOrUnknown(side.sourceType)}
        </p>
      </div>

      <div className="compare-panel-links">
        <ExternalSourceLink url={side.originUrl} label="Original" />
        <ExternalSourceLink url={side.canonicalUrl} label="Canonical" />
      </div>

      <dl className="compare-facts">
        <div>
          <dt>Published</dt>
          <dd>{side.publishedAt ? formatTimestamp(side.publishedAt) : 'Unknown'}</dd>
        </div>
        <div>
          <dt>Capture</dt>
          <dd>
            <code title={side.captureId}>{shortId(side.captureId)}</code> ·{' '}
            {knownOrUnknown(side.captureKind)}
          </dd>
        </div>
        <div>
          <dt>Recorded</dt>
          <dd>{side.recordedAt ? formatTimestamp(side.recordedAt) : 'Unknown'}</dd>
        </div>
        <div>
          <dt>Observed</dt>
          <dd>
            {side.observedAt
              ? formatTimestamp(side.observedAt)
              : 'Unknown (not recorded)'}
          </dd>
        </div>
        <div>
          <dt>Length</dt>
          <dd>{side.charLength} code points</dd>
        </div>
        <div>
          <dt>Content SHA-256</dt>
          <dd>
            <code title={side.textSha256 ?? undefined}>
              {side.textSha256 ? shortId(side.textSha256) : 'Unknown'}
            </code>
          </dd>
        </div>
        <div className="compare-fact-wide">
          <dt>Analysis scope</dt>
          <dd>
            {scopeText}
            {scope?.reason ? ` · ${scope.reason}` : ''}
          </dd>
        </div>
        <div>
          <dt>Publisher key</dt>
          <dd>
            {knownOrUnknown(side.publisherKey)}
            {side.publisherKeyProvisional && (
              <span className="compare-provisional"> provisional host</span>
            )}
          </dd>
        </div>
      </dl>

      {scope?.sourceAvailable === false && (
        <p className="compare-warning-text">
          Source text was unavailable to the extractor for this capture.
        </p>
      )}

      <div className={`compare-coverage compare-coverage--${side.coverage.claimLinkageStatus}`}>
        <strong>{linkage}</strong>
        <span>
          {side.coverage.attributedClaimCount} attributed claim
          {side.coverage.attributedClaimCount === 1 ? '' : 's'} ·{' '}
          {side.coverage.linkedClaimCount} linked overall
        </span>
        {side.coverage.caveat && <p>{side.coverage.caveat}</p>}
        {!side.coverage.historicalAnalysisAvailable && (
          <p className="compare-warning-text">
            This capture's historical claim alignment is not available. The current
            claim links are not substituted.
          </p>
        )}
      </div>
    </section>
  );
};

const PassageView: React.FC<{
  passage: ComparisonPassage;
  caseId: string;
  evidenceId: string;
  fallbackCaptureId: string;
  onOpen: (url: string) => void;
}> = ({ passage, caseId, evidenceId, fallbackCaptureId, onOpen }) => {
  const target = buildInspectorUrl(caseId, {
    claimId: passage.claimId,
    evidenceId,
    captureId: passage.captureId ?? fallbackCaptureId,
    citationId: passage.citationId,
    start:
      passage.startChar !== null
        ? Math.max(0, passage.startChar - CONTEXT_BEFORE)
        : null,
  });
  return (
    <div className="compare-passage">
      <div className="compare-passage-meta">
        <span>{relationLabel(passage.relationship)}</span>
        <span>{alignmentLabel(passage.alignmentStatus)}</span>
      </div>
      {passage.rawRelation && passage.rawRelation !== passage.relationship && (
        <p className="compare-diagnostic">
          Raw stored relationship (diagnostic): {passage.rawRelation}
        </p>
      )}
      {passage.quote ? (
        <blockquote>{passage.quote}</blockquote>
      ) : (
        <p className="compare-no-quote">No validated quotation is stored for this passage.</p>
      )}
      <div className="compare-passage-actions">
        {(passage.startChar !== null || passage.endChar !== null) && (
          <span className="compare-range">
            code points {knownOrUnknown(passage.startChar)}–{knownOrUnknown(passage.endChar)}
          </span>
        )}
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => onOpen(target)}
        >
          <ExternalLink size={14} /> Open captured passage
        </button>
      </div>
      {(passage.assessmentOrigin || passage.assessmentVersion) && (
        <p className="compare-diagnostic">
          Assessment: {passage.assessmentOrigin ?? 'unknown origin'}
          {passage.assessmentVersion ? ` · ${passage.assessmentVersion}` : ''}
        </p>
      )}
    </div>
  );
};

const ClaimSideView: React.FC<{
  side: ComparisonClaimSide | null;
  label: string;
  caseId: string;
  evidenceId: string;
  captureId: string;
  onOpen: (url: string) => void;
}> = ({ side, label, caseId, evidenceId, captureId, onOpen }) => {
  if (!side) {
    return (
      <div className="compare-not-extracted">
        <strong>Not extracted on this side</strong>
        <p>This is extraction coverage, not evidence that the source omitted or disagreed.</p>
      </div>
    );
  }
  if (side.passages.length === 0) {
    return <p className="compare-no-quote">No persisted passage is recorded for this claim.</p>;
  }
  return (
    <div className="compare-claim-side" aria-label={label}>
      {side.passages.map((passage, index) => (
        <PassageView
          key={passage.linkId ?? passage.citationId ?? `${side.claimSignature}-${index}`}
          passage={passage}
          caseId={caseId}
          evidenceId={evidenceId}
          fallbackCaptureId={captureId}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
};

const ComparisonRowView: React.FC<{
  row: ComparisonRow;
  comparison: Comparison;
  caseId: string;
  onOpen: (url: string) => void;
}> = ({ row, comparison, caseId, onOpen }) => {
  return (
    <tr className={`compare-row compare-row--${row.status}`}>
      <td data-label="Assertion">
        <p className="compare-claim-text">{row.claimText || 'Claim text unavailable.'}</p>
        <code className="compare-signature" title={row.claimSignature}>
          {shortId(row.claimSignature)}
        </code>
        <span className={`compare-status compare-status--${row.status}`}>
          {STATUS_LABELS[row.status]}
        </span>
      </td>
      <td data-label="Left extraction">
        <ClaimSideView
          side={row.left}
          label="Left extraction"
          caseId={caseId}
          evidenceId={comparison.left.evidenceId}
          captureId={comparison.left.captureId}
          onOpen={onOpen}
        />
      </td>
      <td data-label="Right extraction">
        <ClaimSideView
          side={row.right}
          label="Right extraction"
          caseId={caseId}
          evidenceId={comparison.right.evidenceId}
          captureId={comparison.right.captureId}
          onOpen={onOpen}
        />
      </td>
      <td data-label="Assessment">
        {row.contradiction.conflict ? (
          <div className="compare-contradiction">
            <strong>Explicitly assessed contradiction</strong>
            <p>{row.contradiction.reason}</p>
          </div>
        ) : row.contradiction.explicit ? (
          <p className="compare-diagnostic">{row.contradiction.reason}</p>
        ) : (
          <p className="compare-diagnostic">No assessed contradiction.</p>
        )}
        {row.caveat && <p className="compare-caveat">{row.caveat}</p>}
      </td>
    </tr>
  );
};

const DependencyBanner: React.FC<{ dependency: Comparison['dependency'] }> = ({
  dependency,
}) => (
  <div className={`compare-dependency ${dependency.detected ? 'is-warning' : ''}`}>
    <Copy size={16} />
    <div>
      <strong>
        {dependency.detected ? 'Dependency detected' : 'No dependency detected'}
      </strong>
      <p>{dependency.message}</p>
      {dependency.reasons.length > 0 && (
        <p className="compare-diagnostic">
          Reasons: {dependency.reasons.map(dependencyReasonLabel).join(', ')}
        </p>
      )}
      {dependency.copyDetected && (
        <p>
          Identical long captured text was detected. Repeated wire copy remains
          separately inspectable but does not add independent corroboration.
        </p>
      )}
      {!dependency.detected && (
        <p className="compare-diagnostic">
          Absence of a detected dependency does not prove independence.
        </p>
      )}
    </div>
  </div>
);

const CompareTab: React.FC<CompareTabProps> = ({ caseId }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const selection = useMemo(
    () => parseComparisonSelection(searchParams),
    [searchParams]
  );
  const resultsRef = useRef<HTMLHeadingElement>(null);

  const evidenceQuery = useQuery({
    queryKey: ['compare-evidence', caseId],
    queryFn: () => getEvidenceForCase(caseId),
    enabled: Boolean(caseId),
    retry: false,
  });
  const leftDetailQuery = useQuery({
    queryKey: ['compare-evidence-detail', caseId, selection.leftId],
    queryFn: () => getEvidenceDetail(caseId, selection.leftId!),
    enabled: Boolean(caseId && selection.leftId),
    retry: false,
  });
  const rightDetailQuery = useQuery({
    queryKey: ['compare-evidence-detail', caseId, selection.rightId],
    queryFn: () => getEvidenceDetail(caseId, selection.rightId!),
    enabled: Boolean(caseId && selection.rightId),
    retry: false,
  });

  const pageSize = selection.limit ?? PAGE_SIZE;
  const offset = selection.offset ?? 0;
  const bothSelected = Boolean(selection.leftId && selection.rightId);
  const sameSelection =
    Boolean(selection.leftId) && selection.leftId === selection.rightId;

  const comparisonQuery = useQuery({
    queryKey: [
      'comparison',
      caseId,
      selection.leftId,
      selection.rightId,
      selection.leftCaptureId,
      selection.rightCaptureId,
      offset,
      pageSize,
    ],
    queryFn: () =>
      getComparison(caseId, {
        left: selection.leftId!,
        right: selection.rightId!,
        leftCapture: selection.leftCaptureId,
        rightCapture: selection.rightCaptureId,
        limit: pageSize,
        offset,
      }),
    enabled: Boolean(caseId && bothSelected && !sameSelection),
    retry: false,
    // Keep the current panels/rows mounted while a pinned-capture URL change
    // refetches, so focus and passage links never flicker away.
    placeholderData: (previousData) => previousData,
  });

  const updateSelection = useCallback(
    (patch: Partial<ComparisonSelection>, replace = false) => {
      setSearchParams(
        toComparisonSearchParams({
          ...parseComparisonSelection(searchParams),
          ...patch,
        }),
        { replace }
      );
    },
    [searchParams, setSearchParams]
  );

  // Pin the API-resolved default captures in the URL for reload/back/forward.
  useEffect(() => {
    const data = comparisonQuery.data;
    if (!data) return;
    const patch: Partial<ComparisonSelection> = {};
    if (!selection.leftCaptureId && data.leftCaptureId) {
      patch.leftCaptureId = data.leftCaptureId;
    }
    if (!selection.rightCaptureId && data.rightCaptureId) {
      patch.rightCaptureId = data.rightCaptureId;
    }
    if (Object.keys(patch).length > 0) {
      updateSelection(patch, true);
    }
  }, [
    comparisonQuery.data,
    selection.leftCaptureId,
    selection.rightCaptureId,
    updateSelection,
  ]);

  const resultKey = [
    selection.leftId,
    selection.rightId,
    selection.leftCaptureId,
    selection.rightCaptureId,
  ].join('|');
  const lastFocusedKey = useRef<string | null>(null);
  useEffect(() => {
    if (!comparisonQuery.data) return;
    if (lastFocusedKey.current === resultKey) return;
    lastFocusedKey.current = resultKey;
    resultsRef.current?.focus();
  }, [comparisonQuery.data, resultKey]);

  if (!caseId) {
    return (
      <div className="compare-tab p-base">
        <div role="alert">No case selected for comparison.</div>
      </div>
    );
  }

  const evidence = evidenceQuery.data ?? [];
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const leftEvidence = selection.leftId
    ? evidenceById.get(selection.leftId)
    : undefined;
  const rightEvidence = selection.rightId
    ? evidenceById.get(selection.rightId)
    : undefined;
  const leftSide = comparisonQuery.data?.left;
  const rightSide = comparisonQuery.data?.right;
  const leftCaptureValue =
    selection.leftCaptureId ??
    leftSide?.captureId ??
    leftDetailQuery.data?.currentCaptureId ??
    leftEvidence?.currentCaptureId ??
    '';
  const rightCaptureValue =
    selection.rightCaptureId ??
    rightSide?.captureId ??
    rightDetailQuery.data?.currentCaptureId ??
    rightEvidence?.currentCaptureId ??
    '';
  const leftCaptures = captureOptions(
    leftDetailQuery.data,
    leftSide,
    leftCaptureValue
  );
  const rightCaptures = captureOptions(
    rightDetailQuery.data,
    rightSide,
    rightCaptureValue
  );
  if (leftCaptureValue && !leftCaptures.some((item) => item.id === leftCaptureValue)) {
    leftCaptures.unshift({
      id: leftCaptureValue,
      label: `Selected · ${shortId(leftCaptureValue)}`,
    });
  }
  if (rightCaptureValue && !rightCaptures.some((item) => item.id === rightCaptureValue)) {
    rightCaptures.unshift({
      id: rightCaptureValue,
      label: `Selected · ${shortId(rightCaptureValue)}`,
    });
  }

  const changeEvidence = (side: 'left' | 'right', value: string) => {
    const patch: Partial<ComparisonSelection> = {
      offset: 0,
    };
    if (side === 'left') {
      patch.leftId = value || null;
      patch.leftCaptureId = null;
      if (value && value === selection.rightId) {
        patch.rightId = null;
        patch.rightCaptureId = null;
      }
    } else {
      patch.rightId = value || null;
      patch.rightCaptureId = null;
      if (value && value === selection.leftId) {
        patch.leftId = null;
        patch.leftCaptureId = null;
      }
    }
    updateSelection(patch);
  };

  const openPassage = (url: string) => navigate(url);

  const clearComparison = () =>
    updateSelection({
      leftId: null,
      rightId: null,
      leftCaptureId: null,
      rightCaptureId: null,
      offset: null,
    });

  const swapSides = () =>
    updateSelection({
      leftId: selection.rightId,
      rightId: selection.leftId,
      leftCaptureId: selection.rightCaptureId,
      rightCaptureId: selection.leftCaptureId,
      offset: 0,
    });

  return (
    <div className="compare-tab p-base">
      <div className="compare-header">
        <div>
          <h3>
            <GitCompare size={18} /> Compare sources
          </h3>
          <p className="subtitle">
            Pair two case sources by exact claim signature and inspect each side's
            captured passage. No model or source fetch runs when this view opens.
          </p>
        </div>
        {evidence.length > 0 && (
          <span className="compare-evidence-count">
            {evidence.length} source{evidence.length === 1 ? '' : 's'} in this case
          </span>
        )}
      </div>

      {evidenceQuery.isLoading && (
        <div className="compare-state" role="status">
          Loading evidence sources…
        </div>
      )}
      {evidenceQuery.error != null && (
        <div className="compare-state compare-state--error" role="alert">
          <AlertTriangle size={16} />
          <div>
            <strong>
              Failed to load evidence sources
              {evidenceQuery.error instanceof Error && evidenceQuery.error.message
                ? `: ${evidenceQuery.error.message}`
                : '.'}
            </strong>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void evidenceQuery.refetch()}
            >
              <RefreshCw size={14} /> Retry
            </button>
          </div>
        </div>
      )}

      {!evidenceQuery.isLoading && !evidenceQuery.error && evidence.length === 0 && (
        <div className="compare-state" role="status">
          No evidence is recorded for this case yet, so there is nothing to compare.
        </div>
      )}

      <div className="compare-controls glass-panel">
        <div className="compare-selector">
          <label htmlFor="compare-left-source">Left source</label>
          <select
            id="compare-left-source"
            value={selection.leftId ?? ''}
            onChange={(event) => changeEvidence('left', event.target.value)}
          >
            <option value="">Select a source</option>
            {evidence.map((item) => (
              <option
                key={item.id}
                value={item.id}
                disabled={item.id === selection.rightId}
              >
                {evidenceLabel(item)}
              </option>
            ))}
            {selection.leftId && !evidenceById.has(selection.leftId) && (
              <option value={selection.leftId}>
                {shortId(selection.leftId)} (not in the current list)
              </option>
            )}
          </select>
          <label htmlFor="compare-left-capture">Left capture</label>
          <select
            id="compare-left-capture"
            value={leftCaptureValue}
            disabled={leftCaptures.length === 0}
            onChange={(event) =>
              updateSelection({
                leftCaptureId: event.target.value || null,
                offset: 0,
              })
            }
          >
            {leftCaptures.length === 0 && <option value="">No capture</option>}
            {leftCaptures.map((capture) => (
              <option key={capture.id} value={capture.id}>
                {capture.label}
              </option>
            ))}
          </select>
          {leftDetailQuery.error != null && (
            <span className="compare-inline-note">
              Capture versions unavailable; using the resolved capture.
            </span>
          )}
        </div>

        <div className="compare-versus" aria-hidden="true">
          vs
        </div>

        <div className="compare-selector">
          <label htmlFor="compare-right-source">Right source</label>
          <select
            id="compare-right-source"
            value={selection.rightId ?? ''}
            onChange={(event) => changeEvidence('right', event.target.value)}
          >
            <option value="">Select a source</option>
            {evidence.map((item) => (
              <option
                key={item.id}
                value={item.id}
                disabled={item.id === selection.leftId}
              >
                {evidenceLabel(item)}
              </option>
            ))}
            {selection.rightId && !evidenceById.has(selection.rightId) && (
              <option value={selection.rightId}>
                {shortId(selection.rightId)} (not in the current list)
              </option>
            )}
          </select>
          <label htmlFor="compare-right-capture">Right capture</label>
          <select
            id="compare-right-capture"
            value={rightCaptureValue}
            disabled={rightCaptures.length === 0}
            onChange={(event) =>
              updateSelection({
                rightCaptureId: event.target.value || null,
                offset: 0,
              })
            }
          >
            {rightCaptures.length === 0 && <option value="">No capture</option>}
            {rightCaptures.map((capture) => (
              <option key={capture.id} value={capture.id}>
                {capture.label}
              </option>
            ))}
          </select>
          {rightDetailQuery.error != null && (
            <span className="compare-inline-note">
              Capture versions unavailable; using the resolved capture.
            </span>
          )}
        </div>

        <div className="compare-control-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              void comparisonQuery.refetch();
              resultsRef.current?.focus();
            }}
            disabled={!bothSelected || sameSelection}
          >
            <GitCompare size={14} /> Compare selected
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={swapSides}
            disabled={!bothSelected}
          >
            <GitCompare size={14} /> Swap sides
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={clearComparison}
            disabled={!bothSelected && !selection.leftCaptureId && !selection.rightCaptureId}
          >
            <X size={14} /> Clear
          </button>
        </div>
      </div>

      {sameSelection && (
        <div className="compare-state compare-state--error" role="alert">
          <AlertTriangle size={16} />
          <div>
            <strong>Choose two different sources.</strong>
            <p>The same evidence record cannot be compared with itself.</p>
          </div>
        </div>
      )}

      {!bothSelected && !sameSelection && (
        <div className="compare-state" role="status">
          Choose a left and a right source to compare their capture-linked claims.
        </div>
      )}

      {comparisonQuery.isLoading && (
        <div className="compare-state" role="status">
          Loading comparison…
        </div>
      )}

      {comparisonQuery.error != null &&
        (isNotFound(comparisonQuery.error) ? (
          <div className="compare-state compare-state--error" role="alert">
            <AlertTriangle size={16} />
            <div>
              <strong>Comparison unavailable.</strong>
              <p>
                One of the selected sources or captures is not available for this
                case. No other case's records are substituted.
              </p>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={clearComparison}
              >
                Clear selection
              </button>
            </div>
          </div>
        ) : (
          <div className="compare-state compare-state--error" role="alert">
            <AlertTriangle size={16} />
            <div>
              <strong>
                Failed to load the comparison
                {comparisonQuery.error instanceof Error &&
                comparisonQuery.error.message
                  ? `: ${comparisonQuery.error.message}`
                  : '.'}
              </strong>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void comparisonQuery.refetch()}
              >
                <RefreshCw size={14} /> Retry
              </button>
            </div>
          </div>
        ))}

      {comparisonQuery.data && (
        <div className="compare-results">
          <h3 ref={resultsRef} tabIndex={-1} className="compare-results-heading">
            Comparison results
          </h3>

          <div className="compare-panels">
            <SourcePanel side={comparisonQuery.data.left} label="Left" />
            <SourcePanel side={comparisonQuery.data.right} label="Right" />
          </div>

          <DependencyBanner dependency={comparisonQuery.data.dependency} />

          {comparisonQuery.data.claims.rows.length === 0 ? (
            <div className="compare-state" role="status">
              No claims share an exact signature across these capture versions.
            </div>
          ) : (
            <div className="compare-table-wrap">
              <table className="compare-table" aria-label="Claim alignment">
                <thead>
                  <tr>
                    <th scope="col">Assertion</th>
                    <th scope="col">Left extraction</th>
                    <th scope="col">Right extraction</th>
                    <th scope="col">Assessment</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisonQuery.data.claims.rows.map((row) => (
                    <ComparisonRowView
                      key={row.claimSignature}
                      row={row}
                      comparison={comparisonQuery.data!}
                      caseId={caseId}
                      onOpen={openPassage}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="compare-pagination">
            <span>
              Showing{' '}
              {comparisonQuery.data.claims.total === 0
                ? 0
                : comparisonQuery.data.claims.offset + 1}
              –{comparisonQuery.data.claims.offset + comparisonQuery.data.claims.rows.length}{' '}
              of {comparisonQuery.data.claims.total}
            </span>
            <div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={comparisonQuery.data.claims.offset <= 0}
                onClick={() =>
                  updateSelection({
                    offset: Math.max(
                      0,
                      comparisonQuery.data!.claims.offset -
                        comparisonQuery.data!.claims.limit
                    ),
                  })
                }
              >
                <ChevronLeft size={14} /> Previous
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={!comparisonQuery.data.claims.hasMore}
                onClick={() =>
                  updateSelection({
                    offset:
                      comparisonQuery.data!.claims.offset +
                      comparisonQuery.data!.claims.limit,
                  })
                }
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>

          <p className="compare-relationship-note">{RELATIONSHIP_WARNING}</p>

          <div className="compare-caveats">
            <h4>Method and limitations</h4>
            <ul>
              {comparisonQuery.data.caveats.map((caveat) => (
                <li key={caveat}>{caveat}</li>
              ))}
              {comparisonQuery.data.policy.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
            <details>
              <summary>Comparison policy</summary>
              <p>
                <strong>Claim identity:</strong>{' '}
                {comparisonQuery.data.policy.claimIdentity}
              </p>
              <p>
                <strong>Alignment:</strong> {comparisonQuery.data.policy.alignment}
              </p>
              <p>
                <strong>Dependency policy:</strong>{' '}
                {comparisonQuery.data.policy.dependencyPolicy}
              </p>
              <p className="compare-diagnostic">
                Policy version: {comparisonQuery.data.policy.version}
              </p>
            </details>
          </div>
        </div>
      )}
    </div>
  );
};

export default CompareTab;
