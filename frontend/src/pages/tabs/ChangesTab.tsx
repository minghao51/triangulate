import React, { useCallback, useEffect, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  History,
  RefreshCw,
  X,
} from 'lucide-react';

import Badge from '../../components/design-system/Badge';
import Button from '../../components/design-system/Button';
import { formatTimestamp, safeExternalUrl } from '../../components/inspector/inspector-utils';
import {
  getClaimDetail,
  getInvestigationRun,
  getInvestigationRuns,
  getRunChanges,
  getSnapshotComparison,
} from '../../services/api';
import { isNotFound } from '../../services/api-error';
import {
  CHANGES_MODE_AD_HOC,
  buildChangesUrl,
  buildCitationUrl,
  buildInspectorUrl,
  parseAdHocChangesSelection,
  parseChangesSelection,
  toChangesSearchParams,
} from '../../services/deep-links';
import type { AdHocChangesSelection } from '../../services/deep-links';
import type {
  ChangeItem,
  ClaimDetail,
  InvestigationRun,
  RunChanges,
  SnapshotComparison,
  SnapshotComparisonItem,
  SnapshotComparisonRef,
  SnapshotComparisonSide,
  SnapshotComparisonUnavailableReason,
} from '../../types/backend-models';
import './ChangesTab.css';

/** Page size for the typed-change list; the API caps it at 100. */
const PAGE_SIZE = 25;
/** How many recent grouped runs the selector loads. */
const RUN_LIST_LIMIT = 50;

interface ChangesTabProps {
  caseId: string;
}

const CHANGE_TYPE_LABELS: Record<string, string> = {
  article_added: 'Article added',
  capture_changed: 'Capture changed',
  claim_added: 'Claim added',
  claim_no_longer_extracted: 'No longer extracted',
  classification_changed: 'Classification changed',
  relationship_changed: 'Relationship changed',
  review_state_changed: 'Review state changed',
  exception_changed: 'Exception changed',
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  article: 'Article',
  articles: 'Article',
  case: 'Case',
  claim: 'Claim',
  claims: 'Claim',
  evidence: 'Evidence',
  link: 'Claim/evidence link',
  links: 'Claim/evidence link',
  event: 'Event',
  events: 'Event',
  citation: 'Citation',
  citations: 'Citation',
  capture: 'Capture',
  captures: 'Capture',
  party: 'Party',
  parties: 'Party',
  partyInvestigations: 'Party investigation',
  narrative: 'Narrative',
  narratives: 'Narrative',
  review: 'Review',
  reviews: 'Review',
  exception: 'Exception',
  exceptions: 'Exception',
};

const FIELD_LABELS: Record<string, string> = {
  text: 'Text',
  claimSignature: 'Signature',
  verificationStatus: 'Verification',
  factAllegationType: 'Claim type',
  partyPositions: 'Party positions',
  controversyScore: 'Controversy score',
  sourceId: 'Source',
  relation: 'Relation',
  captureId: 'Capture',
  citationId: 'Citation',
  quote: 'Quotation',
  startChar: 'Start',
  endChar: 'End',
  alignmentStatus: 'Alignment',
  assessmentOrigin: 'Assessment origin',
  assessmentVersion: 'Assessment version',
  currentCaptureId: 'Current capture',
  title: 'Title',
  url: 'URL',
  source: 'Source',
  status: 'Status',
  notes: 'Notes',
  analysisHash: 'Analysis hash',
  type: 'Type',
  stage: 'Stage',
  severity: 'Severity',
  message: 'Message',
  resolutionNotes: 'Resolution notes',
  summary: 'Summary',
  sourceCount: 'Source count',
  stanceSummary: 'Stance',
  publisher: 'Publisher',
  publishedAt: 'Published',
  firstSeenAt: 'First seen',
  lastSeenAt: 'Last seen',
  fingerprint: 'Fingerprint',
  relevanceScore: 'Relevance',
  sourceType: 'Source type',
};

const URL_FIELDS = new Set(['url', 'originUrl', 'canonicalUrl', 'archivedUrl', 'sourceUrl']);

function changeTypeLabel(type: string): string {
  return CHANGE_TYPE_LABELS[type] ?? type.replace(/_/g, ' ');
}

function entityTypeLabel(entityType: string): string {
  return ENTITY_TYPE_LABELS[entityType] ?? entityType;
}

function fieldLabel(key: string): string {
  if (FIELD_LABELS[key]) return FIELD_LABELS[key];
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/^./, (character) => character.toUpperCase());
}

function shortenRef(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function statusVariant(status: string): 'success' | 'info' | 'warning' | 'danger' | 'neutral' {
  switch (status) {
    case 'succeeded':
      return 'success';
    case 'running':
      return 'info';
    case 'paused':
      return 'warning';
    case 'failed':
      return 'danger';
    case 'interrupted':
      return 'warning';
    default:
      return 'neutral';
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'running':
      return 'Running';
    case 'succeeded':
      return 'Succeeded';
    case 'paused':
      return 'Paused — manual gate';
    case 'failed':
      return 'Failed';
    case 'interrupted':
      return 'Interrupted';
    default:
      return status;
  }
}

function coverageVariant(
  coverage: string
): 'success' | 'warning' | 'danger' | 'neutral' {
  switch (coverage) {
    case 'complete_requested_scope':
      return 'success';
    case 'partial':
      return 'warning';
    case 'failed':
      return 'danger';
    default:
      return 'neutral';
  }
}

function coverageLabel(coverage: string): string {
  switch (coverage) {
    case 'complete_requested_scope':
      return 'Complete requested scope';
    case 'partial':
      return 'Partial coverage';
    case 'failed':
      return 'Failed coverage';
    case 'not_attempted':
      return 'Not attempted';
    case 'unknown':
      return 'Coverage unknown';
    default:
      return coverage;
  }
}

function triggerLabel(trigger: string): string {
  switch (trigger) {
    case 'initial':
      return 'Initial run';
    case 'rerun':
      return 'Rerun or resume';
    case 'monitor':
      return 'Monitor cycle';
    default:
      return trigger;
  }
}

function renderValue(key: string, value: unknown): React.ReactNode {
  if (value === null || value === undefined || value === '') {
    return <span className="changes-value-empty">Not recorded</span>;
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    const text = String(value);
    if (URL_FIELDS.has(key)) {
      const href = safeExternalUrl(text);
      if (href) {
        return (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {text}
          </a>
        );
      }
    }
    return <span>{text}</span>;
  }
  return <code className="changes-structured-value">{JSON.stringify(value)}</code>;
}

interface ChangeFieldsProps {
  value: Record<string, unknown> | null;
}

const ChangeFields: React.FC<ChangeFieldsProps> = ({ value }) => {
  if (!value) {
    return <p className="changes-value-empty">Not recorded in this observation</p>;
  }
  const entries = Object.entries(value);
  if (entries.length === 0) {
    return <p className="changes-value-empty">No fields recorded</p>;
  }
  return (
    <dl className="changes-fields">
      {entries.map(([key, item]) => (
        <div className="changes-field" key={key}>
          <dt>{fieldLabel(key)}</dt>
          <dd>{renderValue(key, item)}</dd>
        </div>
      ))}
    </dl>
  );
};

interface ChangeLink {
  to: string;
  label: string;
}

/**
 * Historical navigation for one change item.
 *
 * Only entities with a snapshot-aware reader get a link: claims and evidence are
 * resolved from the observation that contains them, never from current rows. A
 * removed claim links to the baseline observation that still holds it. Article
 * links are safe external URLs, and link-level changes have no reader at all.
 */
function changeLink(
  item: ChangeItem,
  changes: RunChanges,
  caseId: string,
  runId: string | null
): ChangeLink | null {
  const target = changes.targetSnapshotId;
  const baseline = changes.baselineSnapshotId;
  switch (item.type) {
    case 'claim_added':
      return target
        ? {
            to: buildChangesUrl(caseId, {
              runId,
              claimId: item.entityId,
              snapshotId: target,
            }),
            label: 'View frozen claim',
          }
        : null;
    case 'claim_no_longer_extracted':
      return baseline
        ? {
            to: buildChangesUrl(caseId, {
              runId,
              claimId: item.entityId,
              snapshotId: baseline,
            }),
            label: 'View frozen claim (before)',
          }
        : null;
    case 'classification_changed':
      return target
        ? {
            to: buildChangesUrl(caseId, {
              runId,
              claimId: item.entityId,
              snapshotId: target,
            }),
            label: 'View claim in this observation',
          }
        : null;
    case 'capture_changed':
      return target
        ? {
            to: buildInspectorUrl(caseId, { evidenceId: item.entityId, snapshotId: target }),
            label: 'Open frozen evidence',
          }
        : null;
    case 'article_added': {
      const rawUrl = item.after?.['url'];
      const href = typeof rawUrl === 'string' ? safeExternalUrl(rawUrl) : null;
      return href ? { to: href, label: 'Open article' } : null;
    }
    default:
      return null;
  }
}

const StatePanel: React.FC<{ title: string; children: React.ReactNode; tone?: 'info' | 'warning' }> = ({
  title,
  children,
  tone = 'info',
}) => (
  <div className={`changes-state changes-state--${tone}`} role="status">
    <h4>{title}</h4>
    <div className="changes-state-body">{children}</div>
  </div>
);

interface ChangeItemRowProps {
  item: ChangeItem;
  changes: RunChanges;
  caseId: string;
  runId: string | null;
}

const ChangeItemRow: React.FC<ChangeItemRowProps> = ({ item, changes, caseId, runId }) => {
  const link = changeLink(item, changes, caseId, runId);
  const internal = link?.to.startsWith('/') ?? false;
  return (
    <li className="changes-item">
      <div className="changes-item-head">
        <Badge variant="info">{changeTypeLabel(item.type)}</Badge>
        <span className="changes-entity">
          {entityTypeLabel(item.entityType)}
          <code title={item.entityId}>{shortenRef(item.entityId)}</code>
        </span>
      </div>
      <div className="changes-item-body">
        <div>
          <h5>Before</h5>
          <ChangeFields value={item.before} />
        </div>
        <div>
          <h5>After</h5>
          <ChangeFields value={item.after} />
        </div>
      </div>
      <div className="changes-item-foot">
        <span>
          Recorded by run{' '}
          {item.originRunId ? (
            <code title={item.originRunId}>{shortenRef(item.originRunId)}</code>
          ) : (
            <span className="changes-unknown-origin">origin not recorded</span>
          )}
        </span>
        <span>
          Observed by run{' '}
          {item.observedByRunId ? (
            <code title={item.observedByRunId}>{shortenRef(item.observedByRunId)}</code>
          ) : (
            <span className="changes-unknown-origin">unknown</span>
          )}
        </span>
        <span className="changes-observed-at">{formatTimestamp(item.observedAt)}</span>
        {link ? (
          internal ? (
            <Link className="changes-link" to={link.to}>
              {link.label}
            </Link>
          ) : (
            <a className="changes-link" href={link.to} target="_blank" rel="noopener noreferrer">
              {link.label}
            </a>
          )
        ) : null}
      </div>
    </li>
  );
};

interface ChangesBodyProps {
  changes: RunChanges;
  run: InvestigationRun;
  caseId: string;
  offset: number;
  pageSize: number;
  onOffsetChange: (offset: number) => void;
}

const ChangesBody: React.FC<ChangesBodyProps> = ({
  changes,
  run,
  caseId,
  offset,
  pageSize,
  onOffsetChange,
}) => {
  const coverageIncomplete = changes.coverage !== 'complete_requested_scope';
  const target = changes.targetSnapshotId ?? run.snapshotId;
  const items = changes.items;
  const first = changes.total === 0 ? 0 : offset + 1;
  const last = offset + items.length;

  return (
    <>
      <div className="changes-snapshots">
        <span>
          Baseline{' '}
          <code title={changes.baselineSnapshotId ?? undefined}>
            {changes.baselineSnapshotId ? shortenRef(changes.baselineSnapshotId) : 'none'}
          </code>
        </span>
        <span aria-hidden="true">→</span>
        <span>
          Target{' '}
          <code title={target ?? undefined}>{target ? shortenRef(target) : 'none'}</code>
        </span>
      </div>

      {coverageIncomplete ? (
        <div className="changes-coverage-warning" role="status">
          <AlertTriangle size={16} aria-hidden="true" />
          <div>
            <strong>Coverage: {coverageLabel(changes.coverage)}</strong>
            <p>
              {changes.coverageNote ??
                'Only part of the requested scope was observed for this run.'}{' '}
              An empty list means no changes in observed data — not that every source was
              unchanged.
            </p>
          </div>
        </div>
      ) : null}

      {changes.availability === 'initial' ? (
        <StatePanel title="First observation">
          <p>
            This is the first published snapshot for the case, so there is no earlier
            successful observation to compare against. It is not a surge of new changes.
          </p>
        </StatePanel>
      ) : null}

      {changes.availability === 'pending' ? (
        <StatePanel title="Run in progress" tone="warning">
          <p>
            Changes are not final until this run finishes. A pending run is not an empty
            delta.
          </p>
        </StatePanel>
      ) : null}

      {changes.availability === 'unavailable' ? (
        <StatePanel title="Historical change data unavailable" tone="warning">
          <p>
            No snapshot was published for this run, so there is no stored change data. This
            is not an empty delta.
          </p>
          {run.status === 'failed' || run.status === 'paused' || run.status === 'interrupted' ? (
            <p>
              A {statusLabel(run.status).toLowerCase()} run never advances the successful
              baseline.
            </p>
          ) : null}
          {run.errorMessage ? <p>Recorded error: {run.errorMessage}</p> : null}
        </StatePanel>
      ) : null}

      {changes.availability === 'ready' && changes.total === 0 ? (
        <StatePanel title="Unchanged">
          <p>No changes in observed data between these two observations.</p>
          {coverageIncomplete ? (
            <p>
              This says nothing about sources outside the observed scope; see the coverage
              warning above.
            </p>
          ) : null}
        </StatePanel>
      ) : null}

      {changes.availability === 'ready' && changes.total > 0 ? (
        <>
          <ul className="changes-list" aria-label="Observed changes">
            {items.map((item) => (
              <ChangeItemRow
                key={`${item.type}:${item.entityType}:${item.entityId}`}
                item={item}
                changes={changes}
                caseId={caseId}
                runId={run.id}
              />
            ))}
          </ul>
          <div className="changes-pager">
            <span data-testid="changes-range">
              Showing {first}–{last} of {changes.total}
            </span>
            <div className="changes-pager-actions">
              <Button
                variant="ghost"
                size="sm"
                disabled={offset <= 0}
                onClick={() => onOffsetChange(Math.max(0, offset - pageSize))}
                icon={<ChevronLeft size={14} />}
              >
                Previous
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={!changes.hasMore}
                onClick={() => onOffsetChange(offset + pageSize)}
                icon={<ChevronRight size={14} />}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      ) : null}

      <p className="changes-caveat">
        These rows are observations of committed data, not verdicts. “No longer extracted”
        is a change in extraction, not a retraction, and neither run reference identifies who
        made a change.
      </p>
    </>
  );
};

interface RunSelectorProps {
  runs: InvestigationRun[];
  total: number;
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
}

const RunSelector: React.FC<RunSelectorProps> = ({
  runs,
  total,
  selectedRunId,
  onSelect,
}) => (
  <aside className="changes-runs" aria-label="Grouped investigation runs">
    <h4>Grouped runs</h4>
    <p className="changes-runs-note">
      One entry per investigation invocation, separate from the stage attempts listed under
      Run History.
    </p>
    <ul className="changes-run-list">
      {runs.map((run) => {
        const selected = run.id === selectedRunId;
        return (
          <li key={run.id}>
            <button
              type="button"
              className={`changes-run${selected ? ' changes-run--selected' : ''}`}
              aria-pressed={selected}
              onClick={() => onSelect(run.id)}
            >
              <span className="changes-run-title">
                <strong>Run #{run.sequence}</strong>
                <span className="changes-run-trigger">{triggerLabel(run.trigger)}</span>
              </span>
              <span className="changes-run-badges">
                <Badge variant={statusVariant(run.status)}>{statusLabel(run.status)}</Badge>
                {run.coverage !== 'complete_requested_scope' ? (
                  <Badge variant={coverageVariant(run.coverage)}>
                    {coverageLabel(run.coverage)}
                  </Badge>
                ) : null}
              </span>
              <span className="changes-run-time">{formatTimestamp(run.startedAt)}</span>
            </button>
          </li>
        );
      })}
    </ul>
    {total > runs.length ? (
      <p className="changes-runs-note">Showing the latest {runs.length} of {total} runs.</p>
    ) : null}
  </aside>
);

interface FrozenClaimPanelProps {
  caseId: string;
  claimId: string;
  snapshotId: string;
  runId: string | null;
  onClose: () => void;
}

/**
 * Frozen claim opened from a change row.
 *
 * Resolved with the snapshot-aware claim reader, so a claim that no longer exists
 * in the live rows is still readable exactly as observed. Passage links open the
 * evidence inspector with the same pinned observation. The panel is read-only:
 * leaving the observation is an explicit "Open current claim" transition that is
 * the only control which removes the historical selector from the URL.
 */
const FrozenClaimPanel: React.FC<FrozenClaimPanelProps> = ({
  caseId,
  claimId,
  snapshotId,
  runId,
  onClose,
}) => {
  const query = useQuery({
    queryKey: ['frozen-claim', caseId, claimId, snapshotId],
    queryFn: () => getClaimDetail(caseId, claimId, snapshotId),
    retry: false,
  });
  const claim: ClaimDetail | null = query.data ?? null;
  const liveState = claim?.liveState ?? null;

  return (
    <section className="changes-frozen-claim" aria-label="Frozen claim">
      <div className="changes-frozen-head">
        <h4>
          Frozen claim <code title={claimId}>{shortenRef(claimId)}</code>
        </h4>
        <div className="changes-frozen-actions">
          <Link
            className="changes-link changes-frozen-current"
            to={buildChangesUrl(caseId, { runId, claimId })}
          >
            Open current claim
          </Link>
          <Button variant="ghost" size="sm" onClick={onClose} icon={<X size={14} />}>
            Close
          </Button>
        </div>
      </div>
      <p className="changes-frozen-snapshot">
        Observation <code title={snapshotId}>{shortenRef(snapshotId)}</code> — read-only,
        frozen as observed.
      </p>

      {query.isLoading ? (
        <div className="changes-state" role="status" aria-busy="true">
          <p>Loading frozen claim…</p>
        </div>
      ) : null}

      {query.isError ? (
        isNotFound(query.error) ? (
          <div className="changes-state changes-state--error" role="alert">
            <h4>Claim not available in this observation</h4>
            <p>{(query.error as Error).message}</p>
            <p className="changes-state-hint">
              A claim that is absent from this snapshot is never replaced by a current row.
            </p>
          </div>
        ) : (
          <div className="changes-state changes-state--error" role="alert">
            <h4>Could not load the frozen claim</h4>
            <p>{(query.error as Error).message}</p>
            <Button variant="secondary" size="sm" onClick={() => void query.refetch()}>
              Retry
            </Button>
          </div>
        )
      ) : null}

      {claim ? (
        <>
          {liveState ? (
            <div className="changes-frozen-live" role="status">
              {liveState.present === false
                ? 'The live case no longer contains this claim; the text below is frozen as observed.'
                : liveState.textMatchesSnapshot === false
                  ? 'The live claim has changed since this observation; the text below is frozen as observed.'
                  : 'The live claim still matches this observation.'}
            </div>
          ) : null}
          <blockquote className="changes-frozen-text">{claim.claimText}</blockquote>
          <dl className="changes-fields">
            <div className="changes-field">
              <dt>Signature</dt>
              <dd>{claim.claimSignature}</dd>
            </div>
            <div className="changes-field">
              <dt>Verification</dt>
              <dd>
                {claim.verificationStatus} (provenance: {claim.verificationProvenance})
              </dd>
            </div>
            <div className="changes-field">
              <dt>Claim type</dt>
              <dd>{claim.type}</dd>
            </div>
            <div className="changes-field">
              <dt>Evidence links</dt>
              <dd>{claim.counts.evidenceCount}</dd>
            </div>
          </dl>

          {claim.passages.length > 0 ? (
            <ul className="changes-frozen-passages" aria-label="Frozen passages">
              {claim.passages.map((passage) => (
                <li key={`${passage.id}:${passage.captureId ?? ''}`}>
                  <p className="changes-frozen-quote">
                    {passage.quote ?? 'No validated quotation recorded.'}
                  </p>
                  <p className="changes-frozen-meta">
                    {passage.effectiveRelation} · {passage.alignmentStatus}
                    {passage.captureId ? ` · capture ${shortenRef(passage.captureId)}` : ''}
                    {' · '}
                    {passage.title ?? 'Unknown source'}
                  </p>
                  <Link
                    className="changes-link"
                    to={buildInspectorUrl(caseId, {
                      evidenceId: passage.id,
                      claimId,
                      captureId: passage.captureId,
                      snapshotId,
                    })}
                  >
                    Open passage in evidence inspector
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="changes-value-empty">
              No evidence passages were recorded for this claim in this observation.
            </p>
          )}
        </>
      ) : null}
    </section>
  );
};

// ---------------------------------------------------------------------------
// X01 ad-hoc snapshot comparison (F18)
//
// This panel is deliberately separate from the recorded-changes view: the delta
// below is computed on request between two explicitly pinned observations and
// was never recorded by a run. It therefore has no `observedByRun`, actor or
// causal field, and "absent from a later observation" is never read as a
// deletion, a retraction or a "no longer extracted" verdict.
// ---------------------------------------------------------------------------

const AD_HOC_CHANGE_KIND_LABELS: Record<string, string> = {
  entity_added: 'Present only in the target observation',
  entity_absent: 'Absent from a later observation',
  field_changed: 'Fields changed between observations',
};

const AD_HOC_REASON_TEXT: Record<SnapshotComparisonUnavailableReason, string> = {
  incompatible_schema:
    'the two observations were saved by schema versions that are not comparable.',
  incompatible_identity:
    'the two observations were saved by identity versions that are not comparable.',
  incompatible_policy:
    'the two observations were recorded under comparison policies that are not comparable.',
  unknown_version:
    'at least one observation records a version this build does not support, or an unreadable version value.',
  payload_unreadable:
    'the stored payload of at least one observation cannot be read.',
};

function adHocChangeKindLabel(kind: string): string {
  return AD_HOC_CHANGE_KIND_LABELS[kind] ?? kind.replace(/_/g, ' ');
}

function adHocChangeKindVariant(kind: string): 'info' | 'warning' | 'neutral' {
  switch (kind) {
    case 'entity_added':
      return 'info';
    case 'entity_absent':
      return 'warning';
    default:
      return 'neutral';
  }
}

function adHocReasonText(reason: string | null): string {
  if (!reason) return 'the pair cannot be compared.';
  return (
    AD_HOC_REASON_TEXT[reason as SnapshotComparisonUnavailableReason] ??
    'the pair cannot be compared.'
  );
}

/**
 * Frozen references for one side of one comparison item.
 *
 * Only ids that side actually recorded become links, and only to the recorded
 * claim/evidence/capture/citation readers. A citation is frozen by its own id
 * and the citation/capture GETs reject a snapshot selector, so no snapshot is
 * forwarded to those two; a capture link needs the evidence id it belongs to.
 */
function adHocRefLinks(
  caseId: string,
  ref: SnapshotComparisonRef,
  side: 'baseline' | 'target'
): ChangeLink[] {
  const links: ChangeLink[] = [];
  const prefix = side === 'baseline' ? 'Baseline' : 'Target';
  if (ref.claimId) {
    links.push({
      to: buildChangesUrl(caseId, {
        claimId: ref.claimId,
        snapshotId: ref.snapshotId,
      }),
      label: `${prefix} frozen claim`,
    });
  }
  if (ref.evidenceId) {
    links.push({
      to: buildInspectorUrl(caseId, {
        evidenceId: ref.evidenceId,
        snapshotId: ref.snapshotId,
      }),
      label: `${prefix} frozen evidence`,
    });
  }
  if (ref.evidenceId && ref.captureId) {
    links.push({
      to: buildInspectorUrl(caseId, {
        evidenceId: ref.evidenceId,
        captureId: ref.captureId,
        snapshotId: ref.snapshotId,
      }),
      label: `${prefix} frozen capture`,
    });
  }
  if (ref.citationId) {
    links.push({
      to: buildCitationUrl(caseId, ref.citationId),
      label: `${prefix} frozen citation`,
    });
  }
  return links;
}

const AdHocFields: React.FC<{
  value: Record<string, unknown> | null;
  side: 'baseline' | 'target';
}> = ({ value, side }) => {
  if (!value) {
    return (
      <p className="changes-value-empty">
        {side === 'target'
          ? 'Absent from a later observation'
          : 'Absent from the baseline observation'}
      </p>
    );
  }
  return <ChangeFields value={value} />;
};

const AdHocItemRow: React.FC<{ item: SnapshotComparisonItem; caseId: string }> = ({
  item,
  caseId,
}) => {
  const links = [
    ...adHocRefLinks(caseId, item.refs.baseline, 'baseline'),
    ...adHocRefLinks(caseId, item.refs.target, 'target'),
  ];
  return (
    <li className="changes-adhoc-item">
      <div className="changes-item-head">
        <Badge variant={adHocChangeKindVariant(item.changeKind)}>
          {adHocChangeKindLabel(item.changeKind)}
        </Badge>
        <span className="changes-entity">
          {entityTypeLabel(item.entityType)}
          <code title={item.entityId}>{shortenRef(item.entityId)}</code>
        </span>
      </div>
      {item.changedFields.length > 0 ? (
        <p className="changes-adhoc-fields">
          <span>Changed fields:</span>{' '}
          {item.changedFields.map((field) => (
            <code className="changes-adhoc-field" key={field}>
              {fieldLabel(field)}
            </code>
          ))}
        </p>
      ) : null}
      <div className="changes-item-body">
        <div>
          <h5>Baseline fields</h5>
          <AdHocFields value={item.before} side="baseline" />
        </div>
        <div>
          <h5>Target fields</h5>
          <AdHocFields value={item.after} side="target" />
        </div>
      </div>
      {links.length > 0 ? (
        <div className="changes-item-foot">
          {links.map((link) => (
            <Link className="changes-link" key={`${link.label}:${link.to}`} to={link.to}>
              {link.label}
            </Link>
          ))}
        </div>
      ) : null}
    </li>
  );
};

interface AdHocObservationProps {
  caseId: string;
  side: 'baseline' | 'target';
  snapshotId: string;
  runId: string;
  coverage: string;
  metadata: SnapshotComparisonSide;
}

/** One explicitly labelled side of the comparison, with its own recorded facts. */
const AdHocObservation: React.FC<AdHocObservationProps> = ({
  caseId,
  side,
  snapshotId,
  runId,
  coverage,
  metadata,
}) => (
  <article className="changes-adhoc-observation" data-observation={side}>
    <h5>
      <Badge variant="neutral">ad-hoc</Badge>
      {side === 'baseline' ? 'Baseline observation' : 'Target observation'}
    </h5>
    <dl className="changes-fields">
      <div className="changes-field">
        <dt>Snapshot ID</dt>
        <dd>
          <code title={snapshotId}>{snapshotId}</code>
        </dd>
      </div>
      <div className="changes-field">
        <dt>Owning run</dt>
        <dd>
          <code title={runId}>{runId}</code>
        </dd>
      </div>
      <div className="changes-field">
        <dt>Snapshot saved at</dt>
        <dd>{formatTimestamp(metadata.createdAt)}</dd>
      </div>
      <div className="changes-field">
        <dt>Run sequence</dt>
        <dd>{metadata.sequence}</dd>
      </div>
      <div className="changes-field">
        <dt>Schema version</dt>
        <dd>
          <code>{metadata.schemaVersion}</code>
        </dd>
      </div>
      <div className="changes-field">
        <dt>Identity version</dt>
        <dd>
          <code>{metadata.identityVersion}</code>
        </dd>
      </div>
      <div className="changes-field">
        <dt>Policy version</dt>
        <dd>
          <code>{metadata.policyVersion}</code>
        </dd>
      </div>
      <div className="changes-field">
        <dt>Coverage</dt>
        <dd>
          <Badge variant={coverageVariant(coverage)}>{coverageLabel(coverage)}</Badge>
        </dd>
      </div>
    </dl>
    <p className="changes-adhoc-links">
      <Link className="changes-link" to={buildInspectorUrl(caseId, { snapshotId })}>
        Open the {side} observation in the evidence view
      </Link>
      <Link className="changes-link" to={buildChangesUrl(caseId, { runId, snapshotId })}>
        Open recorded changes pinned to the {side} observation
      </Link>
    </p>
  </article>
);

interface AdHocComparisonPanelProps {
  caseId: string;
  selection: AdHocChangesSelection;
  offset: number;
}

const AdHocComparisonPanel: React.FC<AdHocComparisonPanelProps> = ({
  caseId,
  selection,
  offset,
}) => {
  const [, setSearchParams] = useSearchParams();
  const baselineSnapshotId = selection.baselineSnapshotId;
  const targetSnapshotId = selection.targetSnapshotId;
  const complete = Boolean(baselineSnapshotId && targetSnapshotId);

  const commit = useCallback(
    (patch: {
      baselineSnapshotId?: string | null;
      targetSnapshotId?: string | null;
      offset?: number | null;
    }) => {
      setSearchParams(
        toChangesSearchParams({
          mode: CHANGES_MODE_AD_HOC,
          baselineSnapshotId:
            patch.baselineSnapshotId !== undefined
              ? patch.baselineSnapshotId
              : baselineSnapshotId,
          targetSnapshotId:
            patch.targetSnapshotId !== undefined
              ? patch.targetSnapshotId
              : targetSnapshotId,
          offset: patch.offset !== undefined ? patch.offset : offset > 0 ? offset : null,
        })
      );
    },
    [baselineSnapshotId, targetSnapshotId, offset, setSearchParams]
  );

  const comparisonQuery = useQuery({
    queryKey: [
      'snapshot-comparison',
      caseId,
      baselineSnapshotId,
      targetSnapshotId,
      offset,
    ],
    queryFn: () =>
      getSnapshotComparison(caseId, {
        baseline: baselineSnapshotId as string,
        target: targetSnapshotId as string,
        limit: PAGE_SIZE,
        offset,
      }),
    // Both selectors are required: an incomplete selection never requests and
    // never falls back to the newest snapshot.
    enabled: Boolean(caseId) && complete,
    retry: false,
  });

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      const read = (name: string): string | null => {
        const value = data.get(name);
        if (typeof value !== 'string') return null;
        const trimmed = value.trim();
        return trimmed === '' ? null : trimmed;
      };
      commit({
        baselineSnapshotId: read('baseline'),
        targetSnapshotId: read('target'),
        offset: null,
      });
    },
    [commit]
  );

  const missing = [
    baselineSnapshotId ? null : 'baseline',
    targetSnapshotId ? null : 'target',
  ].filter((side): side is string => side !== null);

  const changes: SnapshotComparison | null =
    complete && comparisonQuery.isSuccess ? comparisonQuery.data ?? null : null;

  const coverageIncomplete = Boolean(
    changes &&
      (changes.baselineCoverage !== 'complete_requested_scope' ||
        changes.targetCoverage !== 'complete_requested_scope')
  );
  const first = changes && changes.offset > 0 ? changes.offset + 1 : 1;
  const last = changes ? changes.offset + changes.items.length : 0;

  return (
    <section
      className="changes-adhoc"
      data-mode="ad_hoc"
      aria-labelledby="changes-adhoc-heading"
    >
      <header className="changes-adhoc-header">
        <div>
          <h4 id="changes-adhoc-heading">Ad-hoc snapshot comparison</h4>
          <p className="changes-adhoc-intro">
            Two explicitly pinned observations of this case, compared on request. No run
            recorded this delta, so it is not a run change and it identifies no actor or
            cause.
          </p>
        </div>
      </header>

      <form className="changes-adhoc-selectors" onSubmit={handleSubmit}>
        <div className="changes-adhoc-selector">
          <label htmlFor="changes-adhoc-baseline">Baseline snapshot ID</label>
          <input
            id="changes-adhoc-baseline"
            key={`baseline:${baselineSnapshotId ?? ''}`}
            name="baseline"
            defaultValue={baselineSnapshotId ?? ''}
            placeholder="snapshot id"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div className="changes-adhoc-selector">
          <label htmlFor="changes-adhoc-target">Target snapshot ID</label>
          <input
            id="changes-adhoc-target"
            key={`target:${targetSnapshotId ?? ''}`}
            name="target"
            defaultValue={targetSnapshotId ?? ''}
            placeholder="snapshot id"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <Button type="submit" variant="secondary" size="sm">
          Compare these snapshots
        </Button>
      </form>

      {missing.length > 0 ? (
        <StatePanel title="Two snapshots are required" tone="warning">
          <p>
            {missing.length === 2
              ? 'No baseline and no target snapshot is pinned.'
              : `The ${missing[0]} snapshot is not pinned.`}{' '}
            Both selectors must be explicit before this comparison can run: no request is
            sent and the newest snapshot is never substituted.
          </p>
        </StatePanel>
      ) : null}

      {complete && comparisonQuery.isLoading ? (
        <div className="changes-state" role="status" aria-busy="true">
          <p>Comparing the two pinned observations…</p>
        </div>
      ) : null}

      {complete && comparisonQuery.isError ? (
        <div className="changes-state changes-state--error" role="alert">
          <h4>Could not compare these snapshots</h4>
          <p>{(comparisonQuery.error as Error).message}</p>
          <p className="changes-state-hint">
            Both snapshots must belong to this case and the baseline must be the earlier
            observation. An unknown, identical or reversed pair fails explicitly instead of
            returning current rows.
          </p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void comparisonQuery.refetch()}
          >
            Retry
          </Button>
        </div>
      ) : null}

      {changes ? (
        <>
          {coverageIncomplete ? (
            <div className="changes-coverage-warning" role="status">
              <AlertTriangle size={16} aria-hidden="true" />
              <div>
                <strong>Coverage is not complete for this pair</strong>
                <p>
                  Each observation records its own coverage. The rows below describe
                  observed data only and say nothing about sources outside that scope.
                </p>
              </div>
            </div>
          ) : null}

          <div className="changes-adhoc-observations">
            <AdHocObservation
              caseId={caseId}
              side="baseline"
              snapshotId={changes.baselineSnapshotId}
              runId={changes.baselineRunId}
              coverage={changes.baselineCoverage}
              metadata={changes.baselineMetadata}
            />
            <AdHocObservation
              caseId={caseId}
              side="target"
              snapshotId={changes.targetSnapshotId}
              runId={changes.targetRunId}
              coverage={changes.targetCoverage}
              metadata={changes.targetMetadata}
            />
          </div>

          {changes.availability === 'unavailable' ? (
            <StatePanel title="Comparison unavailable" tone="warning">
              <p>
                <code>{changes.unavailableReason}</code> —{' '}
                {adHocReasonText(changes.unavailableReason)}
              </p>
              <p>
                No delta is reported for this pair. An unavailable comparison is not a
                zero-change result and says nothing about the observations being equal.
              </p>
            </StatePanel>
          ) : null}

          {changes.availability === 'ready' && changes.total === 0 ? (
            <StatePanel title="No changes between these observations">
              <p>
                No entity-level differences were reported between these two ad-hoc
                observations.
              </p>
              {coverageIncomplete ? (
                <p>
                  This says nothing about sources outside the observed scope; see the
                  coverage warning above.
                </p>
              ) : null}
            </StatePanel>
          ) : null}

          {changes.availability === 'ready' && (changes.total ?? 0) > 0 ? (
            <>
              <ul className="changes-list" aria-label="Ad-hoc comparison items">
                {changes.items.map((item) => (
                  <AdHocItemRow
                    key={`${item.entityType}:${item.entityId}:${item.changeKind}`}
                    item={item}
                    caseId={caseId}
                  />
                ))}
              </ul>
              <div className="changes-pager">
                <span data-testid="changes-adhoc-range">
                  Showing {first}–{last} of {changes.total}
                </span>
                <div className="changes-pager-actions">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={changes.offset <= 0}
                    onClick={() => commit({ offset: Math.max(0, changes.offset - PAGE_SIZE) })}
                    icon={<ChevronLeft size={14} />}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!changes.hasMore}
                    onClick={() => commit({ offset: changes.offset + PAGE_SIZE })}
                    icon={<ChevronRight size={14} />}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          ) : null}

          <p className="changes-adhoc-policy">
            Comparison policy <code>{changes.comparisonPolicyVersion}</code> · mode{' '}
            <code>{changes.mode}</code>
          </p>
          <p className="changes-caveat">
            These rows compare two stored observations on request; no run recorded this
            delta. “Absent from a later observation” describes that observation only: it is
            not a verdict about the entity, and no actor or cause is identified.
          </p>
        </>
      ) : null}

      <p className="changes-permalink">
        <a
          href={buildChangesUrl(caseId, {
            mode: CHANGES_MODE_AD_HOC,
            baselineSnapshotId,
            targetSnapshotId,
            offset: offset > 0 ? offset : null,
          })}
        >
          Permalink for this comparison
        </a>
      </p>
    </section>
  );
};

export const ChangesTab: React.FC<ChangesTabProps> = ({ caseId }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const selection = useMemo(() => parseChangesSelection(searchParams), [searchParams]);
  // Ad-hoc mode is additive: it is active only when `mode=ad_hoc` is present and
  // it never changes what the recorded view does when the mode is absent.
  const adHoc = useMemo(() => parseAdHocChangesSelection(searchParams), [searchParams]);
  const offset = selection.offset ?? 0;

  const updateSelection = useCallback(
    (
      patch: {
        runId?: string | null;
        claimId?: string | null;
        snapshotId?: string | null;
        offset?: number | null;
      },
      options: { replace?: boolean } = {}
    ) => {
      const next = {
        runId: patch.runId !== undefined ? patch.runId : selection.runId,
        claimId: patch.claimId !== undefined ? patch.claimId : selection.claimId,
        snapshotId:
          patch.snapshotId !== undefined ? patch.snapshotId : selection.snapshotId,
        offset: patch.offset !== undefined ? patch.offset : selection.offset,
      };
      const params = toChangesSearchParams(next);
      setSearchParams(params, { replace: options.replace ?? false });
    },
    [selection.runId, selection.claimId, selection.snapshotId, selection.offset, setSearchParams]
  );

  const runsQuery = useQuery({
    queryKey: ['investigation-runs', caseId],
    queryFn: () => getInvestigationRuns(caseId, { limit: RUN_LIST_LIMIT }),
    // The ad-hoc comparison does not read grouped runs; the recorded view is the
    // only consumer, so switching mode never pins a run into an ad-hoc URL.
    enabled: Boolean(caseId) && !adHoc.active,
    retry: false,
  });

  const runs: InvestigationRun[] = useMemo(
    () => runsQuery.data?.items ?? [],
    [runsQuery.data]
  );
  const total = runsQuery.data?.total ?? runs.length;

  const selectedInList = useMemo(
    () => (selection.runId ? runs.find((run) => run.id === selection.runId) ?? null : null),
    [runs, selection.runId]
  );
  const selectionNeedsLookup = Boolean(
    runsQuery.isSuccess && runs.length > 0 && selection.runId && !selectedInList
  );

  // A URL-selected run outside the latest-50 list is resolved through the
  // single-run reader before the URL is rewritten: only its 404 proves absence,
  // and a network/5xx failure is never evidence that the run does not exist.
  const runLookupQuery = useQuery({
    queryKey: ['investigation-run', caseId, selection.runId],
    queryFn: () => getInvestigationRun(caseId, selection.runId as string),
    enabled: selectionNeedsLookup,
    retry: false,
  });

  const selectedRun = useMemo(() => {
    if (selection.runId) {
      if (selectedInList) return selectedInList;
      if (runLookupQuery.isSuccess && runLookupQuery.data?.id === selection.runId) {
        return runLookupQuery.data;
      }
      return null;
    }
    return runs[0] ?? null;
  }, [runs, selection.runId, selectedInList, runLookupQuery.isSuccess, runLookupQuery.data]);

  // The URL is the selection authority. Pin the newest run once the list is
  // known. A run ID missing from the loaded list is replaced only after the
  // single-run reader answers 404; a lookup failure keeps the selection and
  // surfaces the error state instead of silently switching runs.
  useEffect(() => {
    if (adHoc.active) return;
    if (!runsQuery.isSuccess || runs.length === 0) return;
    if (!selection.runId) {
      updateSelection({ runId: runs[0].id, offset: null }, { replace: true });
      return;
    }
    if (selectedInList) return;
    if (runLookupQuery.isPending) return;
    if (runLookupQuery.isSuccess && runLookupQuery.data?.id === selection.runId) {
      return;
    }
    if (runLookupQuery.isError && !isNotFound(runLookupQuery.error)) return;
    updateSelection({ runId: runs[0].id, offset: null }, { replace: true });
  }, [
    adHoc.active,
    runsQuery.isSuccess,
    runs,
    selection.runId,
    selectedInList,
    runLookupQuery.isPending,
    runLookupQuery.isSuccess,
    runLookupQuery.data,
    runLookupQuery.isError,
    runLookupQuery.error,
    updateSelection,
  ]);

  const changesQuery = useQuery({
    queryKey: ['run-changes', caseId, selectedRun?.id ?? null, offset],
    queryFn: () => getRunChanges(caseId, selectedRun!.id, { limit: PAGE_SIZE, offset }),
    enabled: Boolean(caseId && selectedRun?.id),
    retry: false,
  });

  const handleSelectRun = useCallback(
    (runId: string) => {
      updateSelection({ runId, offset: null, claimId: null, snapshotId: null });
    },
    [updateSelection]
  );

  const lookupFailed =
    runLookupQuery.isError && !isNotFound(runLookupQuery.error);

  const handleRetry = useCallback(() => {
    void runsQuery.refetch();
    if (runLookupQuery.isError) void runLookupQuery.refetch();
    if (selectedRun) void changesQuery.refetch();
  }, [runsQuery, changesQuery, runLookupQuery, selectedRun]);

  const changesUrl = buildChangesUrl(caseId, {
    runId: selectedRun?.id ?? selection.runId,
    claimId: selection.claimId,
    snapshotId: selection.snapshotId,
    offset: offset > 0 ? offset : null,
  });

  return (
    <section className="changes-tab" aria-labelledby="changes-heading">
      <header className="changes-header">
        <div>
          <h3 id="changes-heading">
            <History size={16} aria-hidden="true" /> Changes between observations
          </h3>
          <p className="changes-intro">
            {adHoc.active
              ? 'Two explicitly pinned observations of this case, compared on request. This mode is separate from recorded run changes.'
              : 'What changed between two pinned observations of this case, grouped by investigation run. Every row is a stored observation; nothing is recomputed from current rows.'}
          </p>
        </div>
        <div className="changes-header-actions">
          {adHoc.active ? (
            <Link className="changes-link" to={buildChangesUrl(caseId, {})}>
              Recorded changes
            </Link>
          ) : (
            <Link
              className="changes-link"
              to={buildChangesUrl(caseId, { mode: CHANGES_MODE_AD_HOC })}
            >
              Compare two snapshots
            </Link>
          )}
          {adHoc.active ? null : (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRetry}
              icon={<RefreshCw size={14} />}
            >
              Refresh
            </Button>
          )}
        </div>
      </header>

      {adHoc.active ? (
        <AdHocComparisonPanel caseId={caseId} selection={adHoc} offset={offset} />
      ) : null}

      {!adHoc.active && runsQuery.isLoading ? (
        <div className="changes-state" role="status" aria-busy="true">
          <p>Loading grouped runs…</p>
        </div>
      ) : null}

      {!adHoc.active && runsQuery.isError ? (
        <div className="changes-state changes-state--error" role="alert">
          <h4>Could not load grouped runs</h4>
          <p>{(runsQuery.error as Error).message}</p>
          <Button variant="secondary" size="sm" onClick={handleRetry}>
            Retry
          </Button>
        </div>
      ) : null}

      {!adHoc.active && runsQuery.isSuccess && runs.length === 0 ? (
        <div className="changes-state" role="status">
          <h4>No grouped runs recorded</h4>
          <p>
            This case has no recorded investigation runs yet, so there is nothing to compare.
            This is not an empty change set.
          </p>
        </div>
      ) : null}

      {runs.length > 0 && !adHoc.active ? (
        <div className="changes-layout">
          <RunSelector
            runs={runs}
            total={total}
            selectedRunId={selectedRun?.id ?? null}
            onSelect={handleSelectRun}
          />
          <div className="changes-panel">
            {selectionNeedsLookup && runLookupQuery.isPending ? (
              <div className="changes-state" role="status" aria-busy="true">
                <p>Resolving the selected run…</p>
              </div>
            ) : null}

            {lookupFailed ? (
              <div className="changes-state changes-state--error" role="alert">
                <h4>Could not resolve the selected run</h4>
                <p>{(runLookupQuery.error as Error).message}</p>
                <p className="changes-state-hint">
                  The selected run is not among the latest {runs.length} listed runs,
                  so it was checked against the single-run reader. A temporary failure
                  is not proof that the run does not exist.
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void runLookupQuery.refetch()}
                >
                  Retry
                </Button>
              </div>
            ) : null}

            {selectedRun ? (
              <div className="changes-run-header">
                <h4>
                  Run #{selectedRun.sequence} · {triggerLabel(selectedRun.trigger)}
                </h4>
                <div className="changes-run-meta">
                  <Badge variant={statusVariant(selectedRun.status)}>
                    {statusLabel(selectedRun.status)}
                  </Badge>
                  <Badge variant={coverageVariant(selectedRun.coverage)}>
                    {coverageLabel(selectedRun.coverage)}
                  </Badge>
                  <span>Started {formatTimestamp(selectedRun.startedAt)}</span>
                  {selectedRun.completedAt ? (
                    <span>Finished {formatTimestamp(selectedRun.completedAt)}</span>
                  ) : null}
                </div>
              </div>
            ) : null}

            {changesQuery.isLoading ? (
              <div className="changes-state" role="status" aria-busy="true">
                <p>Loading changes for this run…</p>
              </div>
            ) : null}

            {changesQuery.isError ? (
              <div className="changes-state changes-state--error" role="alert">
                <h4>Could not load changes</h4>
                <p>{(changesQuery.error as Error).message}</p>
                <p className="changes-state-hint">
                  An unknown run ID or a run from another case is rejected, and an
                  unsupported snapshot selector fails explicitly rather than returning
                  current rows.
                </p>
                <Button variant="secondary" size="sm" onClick={handleRetry}>
                  Retry
                </Button>
              </div>
            ) : null}

            {selection.claimId && selection.snapshotId ? (
              <FrozenClaimPanel
                caseId={caseId}
                claimId={selection.claimId}
                snapshotId={selection.snapshotId}
                runId={selectedRun?.id ?? selection.runId}
                onClose={() => updateSelection({ claimId: null, snapshotId: null })}
              />
            ) : null}

            {changesQuery.isSuccess && changesQuery.data ? (
              <ChangesBody
                changes={changesQuery.data}
                run={selectedRun!}
                caseId={caseId}
                offset={offset}
                pageSize={PAGE_SIZE}
                onOffsetChange={(nextOffset) => updateSelection({ offset: nextOffset })}
              />
            ) : null}

            <p className="changes-permalink">
              <a href={changesUrl}>Permalink for this selection</a>
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
};

export default ChangesTab;
