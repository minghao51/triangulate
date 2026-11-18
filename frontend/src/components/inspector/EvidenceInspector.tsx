import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileSearch,
  RefreshCw,
  X,
} from 'lucide-react';
import type {
  CaptureSummary,
  CitationDetail,
  ClaimDetail,
  ClaimEvidenceLink,
  EvidenceClaimReference,
  EvidenceDetail,
  EvidenceSource,
} from '../../types/backend-models';
import {
  getCaptureWindow,
  getCitationDetail,
  getClaimDetail,
  getEvidenceDetail,
} from '../../services/api';
import { isNotFound, isUnprocessable } from '../../services/api-error';
import {
  parseInspectorSelection,
  toInspectorSearchParams,
  type InspectorSelection,
} from '../../services/deep-links';
import {
  alignmentLabel,
  codePointLength,
  extractionScope,
  formatTimestamp,
  isExactAlignment,
  knownOrUnknown,
  relationLabel,
  safeExternalUrl,
  splitHighlight,
  summariseProvenance,
} from './inspector-utils';
import './EvidenceInspector.css';

/** Large enough for a full article in one request, still within the API cap. */
const WINDOW_LENGTH = 20000;
/** Keep some readable context before the quotation when auto-positioning. */
const CONTEXT_BEFORE = 200;

interface InspectedPassage {
  claimId: string | null;
  claimText: string;
  claimSignature: string | null;
  effectiveRelation: string;
  rawRelation: string | null;
  alignmentStatus: string;
  quote: string | null;
  startChar: number | null;
  endChar: number | null;
  citationId: string | null;
  captureId: string | null;
  diagnosticReason: string | null;
  assessmentOrigin: string | null;
  assessmentVersion: string | null;
}

function shortId(value: string | null | undefined): string {
  if (!value) return 'unknown';
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function citationPassage(citation: CitationDetail): InspectedPassage {
  return {
    claimId: citation.originalClaimId,
    claimText: citation.claimText,
    claimSignature: citation.claimSignature,
    effectiveRelation: citation.relationship,
    rawRelation: null,
    alignmentStatus: citation.alignmentStatus,
    quote: citation.quote,
    startChar: citation.startChar,
    endChar: citation.endChar,
    citationId: citation.id,
    captureId: citation.captureId,
    diagnosticReason: null,
    assessmentOrigin: citation.assessmentOrigin,
    assessmentVersion: citation.assessmentVersion,
  };
}

function findClaimLink(
  claimDetail: ClaimDetail | null,
  reference: EvidenceClaimReference | null,
  captureId: string | null
): ClaimEvidenceLink | null {
  const passages = claimDetail?.passages ?? [];
  if (reference?.citationId) {
    const byCitation = passages.find((item) => item.citationId === reference.citationId);
    if (byCitation) return byCitation;
  }
  if (reference?.captureId) {
    const byCapture = passages.find((item) => item.captureId === reference.captureId);
    if (byCapture) return byCapture;
  }
  if (captureId) {
    const bySelectedCapture = passages.find((item) => item.captureId === captureId);
    if (bySelectedCapture) return bySelectedCapture;
  }
  return passages.length === 1 ? passages[0] : null;
}

function evidencePassage(
  evidenceDetail: EvidenceDetail | null,
  claimDetail: ClaimDetail | null,
  claimId: string | null,
  captureId: string | null
): InspectedPassage | null {
  if (!evidenceDetail || !claimId) return null;
  const reference =
    evidenceDetail.relatedClaims.find((item) => item.claimId === claimId) ?? null;
  const link = findClaimLink(claimDetail, reference, captureId);
  if (!reference && !link) return null;

  return {
    claimId,
    claimText: reference?.claimText || claimDetail?.claimText || '',
    claimSignature: reference?.claimSignature ?? claimDetail?.claimSignature ?? null,
    effectiveRelation: reference?.effectiveRelation ?? link?.effectiveRelation ?? 'uncertain',
    rawRelation: reference?.relation ?? link?.relation ?? null,
    alignmentStatus: reference?.alignmentStatus ?? link?.alignmentStatus ?? 'not_provided',
    quote: reference?.quote ?? link?.quote ?? null,
    startChar: reference?.startChar ?? link?.startChar ?? null,
    endChar: reference?.endChar ?? link?.endChar ?? null,
    citationId: reference?.citationId ?? link?.citationId ?? null,
    captureId: reference?.captureId ?? link?.captureId ?? null,
    diagnosticReason: reference?.diagnosticReason ?? link?.diagnosticReason ?? null,
    assessmentOrigin: link?.assessmentOrigin ?? null,
    assessmentVersion: link?.assessmentVersion ?? null,
  };
}

const Field: React.FC<{ label: string; children?: React.ReactNode }> = ({
  label,
  children,
}) => (
  <div className="inspector-field">
    <span className="inspector-field-label">{label}</span>
    <span className="inspector-field-value">{children ?? 'Unknown'}</span>
  </div>
);

const ExternalUrlField: React.FC<{ label: string; url: string | null | undefined }> = ({
  label,
  url,
}) => {
  const safeUrl = safeExternalUrl(url);
  return (
    <Field label={label}>
      {safeUrl ? (
        <a href={safeUrl} target="_blank" rel="noopener noreferrer">
          {safeUrl}
        </a>
      ) : url ? (
        'Not a safe external URL'
      ) : (
        'Unknown'
      )}
    </Field>
  );
};

interface EvidenceInspectorProps {
  caseId: string;
}

/**
 * Claim/evidence inspector hosted inside the existing evidence tab.
 *
 * The URL query is the single selection authority: reload, back/forward and
 * case changes all re-derive the inspector from `?citation`, `?evidence`,
 * `?capture`, `?claim` and `?start`. Every request is a GET.
 */
export const EvidenceInspector: React.FC<EvidenceInspectorProps> = ({ caseId }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const selection = useMemo(() => parseInspectorSelection(searchParams), [searchParams]);
  const { claimId, evidenceId, captureId, citationId, start } = selection;

  const headingRef = useRef<HTMLHeadingElement>(null);

  const citationQuery = useQuery({
    queryKey: ['citation-inspector', caseId, citationId],
    queryFn: () => getCitationDetail(caseId, citationId!),
    enabled: Boolean(caseId && citationId),
    retry: false,
  });
  const evidenceQuery = useQuery({
    queryKey: ['evidence-inspector', caseId, evidenceId],
    queryFn: () => getEvidenceDetail(caseId, evidenceId!),
    enabled: Boolean(caseId && evidenceId && !citationId),
    retry: false,
  });
  // Claim detail enriches assessment provenance but never blocks the passage view.
  const claimQuery = useQuery({
    queryKey: ['claim-inspector', caseId, claimId],
    queryFn: () => getClaimDetail(caseId, claimId!),
    enabled: Boolean(caseId && claimId && !citationId),
    retry: false,
  });

  const citation = citationQuery.data ?? null;
  const evidenceDetail = evidenceQuery.data ?? null;
  const claimDetail = claimQuery.data ?? null;
  const activeEvidence: EvidenceSource | null = citation?.evidence ?? evidenceDetail ?? null;
  const captures: CaptureSummary[] = useMemo(
    () => (citation?.capture ? [citation.capture] : evidenceDetail?.captures ?? []),
    [citation, evidenceDetail]
  );
  const effectiveCaptureId = citation
    ? citation.captureId ?? citation.capture?.id ?? null
    : captureId ?? evidenceDetail?.currentCaptureId ?? captures[0]?.id ?? null;
  const captureSummary =
    captures.find((item) => item.id === effectiveCaptureId) ?? citation?.capture ?? null;
  // A requested older version must exist in the reported capture list.
  const captureSelectionKnown =
    !evidenceDetail || !captureId || captures.some((item) => item.id === captureId);

  const passage = useMemo<InspectedPassage | null>(() => {
    if (citation) return citationPassage(citation);
    return evidencePassage(evidenceDetail, claimDetail, claimId, effectiveCaptureId);
  }, [citation, evidenceDetail, claimDetail, claimId, effectiveCaptureId]);

  const passageMatchesCapture =
    !passage?.captureId || passage.captureId === effectiveCaptureId;

  const windowQuery = useQuery({
    queryKey: [
      'capture-window',
      caseId,
      activeEvidence?.id ?? null,
      effectiveCaptureId,
      start ?? 0,
      WINDOW_LENGTH,
    ],
    queryFn: () =>
      getCaptureWindow(caseId, activeEvidence!.id, effectiveCaptureId!, {
        start: start ?? 0,
        length: WINDOW_LENGTH,
      }),
    enabled: Boolean(
      caseId && activeEvidence?.id && effectiveCaptureId && captureSelectionKnown
    ),
    retry: false,
  });

  const updateSelection = useCallback(
    (patch: Partial<InspectorSelection>, options: { replace?: boolean } = {}) => {
      setSearchParams(
        toInspectorSearchParams({ ...parseInspectorSelection(searchParams), ...patch }),
        { replace: options.replace ?? false }
      );
    },
    [searchParams, setSearchParams]
  );

  // Position the first window around the validated quotation, once it is known.
  useEffect(() => {
    if (!passage || !passageMatchesCapture || start !== null) return;
    if (passage.startChar === null) return;
    const desiredStart = Math.max(0, passage.startChar - CONTEXT_BEFORE);
    if (desiredStart === 0) return;
    updateSelection({ start: desiredStart }, { replace: true });
  }, [passage, passageMatchesCapture, start, updateSelection]);

  // Move focus to the selected inspector heading (keyboard + deep-link parity).
  const focusKey = `${citationId ?? ''}|${evidenceId ?? ''}|${effectiveCaptureId ?? ''}|${claimId ?? ''}`;
  useEffect(() => {
    if (!citationId && !evidenceId) return;
    headingRef.current?.focus();
  }, [focusKey, citationId, evidenceId]);

  if (!citationId && !evidenceId) return null;

  const closeInspector = () => {
    updateSelection({
      citationId: null,
      evidenceId: null,
      captureId: null,
      start: null,
      length: null,
    });
  };

  const primaryQuery = citationId ? citationQuery : evidenceQuery;
  const heading = citationId
    ? `Frozen citation ${shortId(citation?.id ?? citationId)}`
    : activeEvidence?.title
      ? `Evidence inspector: ${activeEvidence.title}`
      : `Evidence inspector ${shortId(evidenceId)}`;

  const renderQueryError = (
    error: unknown,
    label: string,
    retry: () => void
  ) => {
    if (isNotFound(error)) {
      return (
        <div className="inspector-state inspector-state--error" role="alert">
          <AlertTriangle size={16} />
          <div>
            <strong>{label} not found for this case.</strong>
            <p>
              It may belong to another case, or the record may no longer exist. The
              workspace never substitutes another case&apos;s data.
            </p>
            <button type="button" className="btn btn-secondary" onClick={closeInspector}>
              Close inspector
            </button>
          </div>
        </div>
      );
    }
    return (
      <div className="inspector-state inspector-state--error" role="alert">
        <AlertTriangle size={16} />
        <div>
          <strong>
            Failed to load {label.toLowerCase()}
            {error instanceof Error && error.message ? `: ${error.message}` : '.'}
          </strong>
          <div className="inspector-state-actions">
            <button type="button" className="btn btn-secondary" onClick={retry}>
              <RefreshCw size={14} /> Retry
            </button>
            <button type="button" className="btn btn-ghost" onClick={closeInspector}>
              Close inspector
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <section className="evidence-inspector glass-panel" aria-label="Evidence inspector">
      <div className="inspector-header">
        <h3 ref={headingRef} tabIndex={-1} className="inspector-heading">
          {heading}
        </h3>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={closeInspector}
          aria-label="Close inspector"
        >
          <X size={14} /> Close
        </button>
      </div>

      {primaryQuery.isLoading && (
        <div className="inspector-state" role="status">
          Loading {citationId ? 'frozen citation' : 'evidence source'}…
        </div>
      )}

      {primaryQuery.error != null &&
        renderQueryError(
          primaryQuery.error,
          citationId ? 'Citation' : 'Evidence',
          () => {
            void primaryQuery.refetch();
          }
        )}

      {!primaryQuery.isLoading && !primaryQuery.error && !activeEvidence && (
        <div className="inspector-state" role="status">
          No evidence source is available for this selection.
        </div>
      )}

      {citation && (
        <>
          {!citation.liveClaimPresent && (
            <div className="inspector-banner" role="status">
              <strong>The current claim is no longer present.</strong> This frozen
              citation still records the claim text, relationship and passage exactly
              as they were assessed.
            </div>
          )}
          <section className="inspector-section" aria-labelledby="frozen-claim-heading">
            <h4 id="frozen-claim-heading">Frozen claim text</h4>
            <blockquote className="inspector-claim-text">{citation.claimText}</blockquote>
            <div className="inspector-fields">
              <Field label="Claim signature">
                {knownOrUnknown(citation.claimSignature)}
              </Field>
              <Field label="Original claim ID">
                {knownOrUnknown(citation.originalClaimId)}
              </Field>
              {citation.liveClaimPresent && citation.liveClaimId && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm inspector-inline-action"
                  onClick={() =>
                    updateSelection({
                      citationId: null,
                      claimId: citation.liveClaimId,
                      evidenceId: citation.evidenceId,
                      captureId: citation.captureId,
                      start: null,
                    })
                  }
                >
                  Open current claim
                </button>
              )}
            </div>
          </section>
        </>
      )}

      {!citation && passage && (
        <section className="inspector-section" aria-labelledby="claim-passage-heading">
          <h4 id="claim-passage-heading">Claim being inspected</h4>
          <p className="inspector-claim-text">{passage.claimText || 'Claim text unavailable.'}</p>
          <div className="inspector-fields">
            <Field label="Claim signature">
              {knownOrUnknown(passage.claimSignature)}
            </Field>
            {claimDetail && (
              <Field label="Verification status">
                {claimDetail.verificationStatus} (provenance:{' '}
                {knownOrUnknown(claimDetail.verificationProvenance)}; not a reviewer
                confirmation)
              </Field>
            )}
          </div>
        </section>
      )}

      {!citation && evidenceDetail && !claimId && (
        <div className="inspector-state" role="status">
          No claim passage is selected. Pick a linked claim below to show its
          validated quotation.
        </div>
      )}

      {passage && (
        <section className="inspector-section" aria-labelledby="passage-heading">
          <h4 id="passage-heading">Validated passage</h4>
          <div className={`inspector-relation inspector-relation--${passage.effectiveRelation}`}>
            <span className="inspector-relation-label">Relationship</span>
            <strong>{relationLabel(passage.effectiveRelation)}</strong>
            {passage.rawRelation && passage.rawRelation !== passage.effectiveRelation && (
              <span className="inspector-diagnostic">
                Raw stored value (diagnostic): {passage.rawRelation}
              </span>
            )}
          </div>
          <div className="inspector-alignment">
            <strong>{alignmentLabel(passage.alignmentStatus)}</strong>
            {passage.diagnosticReason && (
              <p className="inspector-diagnostic">{passage.diagnosticReason}</p>
            )}
            <p className="inspector-note">
              Exact alignment means the quotation matches the captured text. It does
              not confirm the claim or turn reporting into corroboration.
            </p>
          </div>
          {!passageMatchesCapture && (
            <div className="inspector-state" role="status">
              This passage was validated against a different capture version (
              {shortId(passage.captureId)}), so it is not highlighted in{' '}
              {shortId(effectiveCaptureId)}. Open the matching capture version.
            </div>
          )}
          {passage.quote && (
            <div className="inspector-quote">
              <span className="inspector-field-label">Quotation</span>
              <blockquote>{passage.quote}</blockquote>
            </div>
          )}
          <div className="inspector-fields">
            <Field label="Alignment status">{passage.alignmentStatus}</Field>
            <Field label="Code-point range">
              {passage.startChar !== null && passage.endChar !== null
                ? `${passage.startChar}–${passage.endChar}`
                : 'Unknown'}
            </Field>
            <Field label="Assessment origin">
              {passage.assessmentOrigin ?? 'Unknown (not reviewer-confirmed)'}
            </Field>
            <Field label="Assessment version">
              {knownOrUnknown(passage.assessmentVersion)}
            </Field>
            <Field label="Citation ID">{knownOrUnknown(passage.citationId)}</Field>
            <Field label="Capture ID">{knownOrUnknown(passage.captureId ?? effectiveCaptureId)}</Field>
          </div>
        </section>
      )}

      {!citation && evidenceDetail && evidenceDetail.relatedClaims.length > 0 && (
        <section className="inspector-section" aria-labelledby="related-claims-heading">
          <h4 id="related-claims-heading">Claims linked to this source</h4>
          <ul className="inspector-related-list">
            {evidenceDetail.relatedClaims.map((reference) => {
              const isCurrent = reference.claimId === claimId;
              return (
                <li key={reference.claimId} className="inspector-related-item">
                  <div className="inspector-related-buttons">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      aria-current={isCurrent ? 'true' : undefined}
                      onClick={() =>
                        updateSelection({
                          claimId: reference.claimId,
                          captureId: reference.captureId,
                          start: null,
                        })
                      }
                    >
                      <FileSearch size={14} /> Show passage
                    </button>
                    {reference.citationId && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => updateSelection({ citationId: reference.citationId })}
                      >
                        Open frozen citation
                      </button>
                    )}
                  </div>
                  <p className="inspector-claim-text">{reference.claimText}</p>
                  <p className="inspector-diagnostic">
                    {relationLabel(reference.effectiveRelation)} ·{' '}
                    {alignmentLabel(reference.alignmentStatus)}
                  </p>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {!citation && evidenceDetail && evidenceDetail.relatedClaims.length === 0 && (
        <div className="inspector-state" role="status">
          No claims are linked to this source, so there is no validated quotation to
          highlight. The recorded source metadata remains available below.
        </div>
      )}

      {activeEvidence && (
        <section className="inspector-section" aria-labelledby="source-heading">
          <h4 id="source-heading">Source and capture metadata</h4>
          <div className="inspector-fields">
            <Field label="Evidence ID">{knownOrUnknown(activeEvidence.id)}</Field>
            <Field label="Title">{knownOrUnknown(activeEvidence.title)}</Field>
            <Field label="Publisher">{knownOrUnknown(activeEvidence.publisher)}</Field>
            <Field label="Source type">{knownOrUnknown(activeEvidence.sourceType)}</Field>
            <Field label="Recorded verification">
              {knownOrUnknown(activeEvidence.verificationStatus)} (not reviewer-confirmed)
            </Field>
            <Field label="Published">
              {activeEvidence.publishedAt
                ? formatTimestamp(activeEvidence.publishedAt)
                : 'Unknown'}
            </Field>
            <ExternalUrlField label="Original URL" url={activeEvidence.originUrl} />
            <ExternalUrlField label="Canonical URL" url={activeEvidence.canonicalUrl} />
            <Field label="Capture ID">{knownOrUnknown(effectiveCaptureId)}</Field>
            <Field label="Capture kind">
              {knownOrUnknown(captureSummary?.captureKind)}
            </Field>
            <Field label="Current capture">
              {captureSummary ? (captureSummary.isCurrent ? 'Yes' : 'No') : 'Unknown'}
            </Field>
            <Field label="Recorded at">
              {captureSummary?.recordedAt
                ? formatTimestamp(captureSummary.recordedAt)
                : 'Unknown'}
            </Field>
            <Field label="Observed at">
              {captureSummary?.observedAt
                ? formatTimestamp(captureSummary.observedAt)
                : 'Unknown (not recorded)'}
            </Field>
            <Field label="Content SHA-256">
              {knownOrUnknown(captureSummary?.textSha256)}
            </Field>
            <Field label="Capture length">
              {captureSummary ? `${captureSummary.charLength} code points` : 'Unknown'}
            </Field>
            <Field label="Extraction scope">
              {extractionScope(captureSummary?.metadata)}
            </Field>
            <Field label="Analysis provenance">
              {passage?.assessmentOrigin || passage?.assessmentVersion
                ? [
                    passage.assessmentOrigin
                      ? `origin: ${passage.assessmentOrigin}`
                      : null,
                    passage.assessmentVersion
                      ? `version: ${passage.assessmentVersion}`
                      : null,
                  ]
                    .filter(Boolean)
                    .join('; ')
                : summariseProvenance(captureSummary?.metadata?.origin_stage_attempt_id) ??
                  'Unknown'}
            </Field>
            <Field label="Extraction metadata">
              {summariseProvenance(captureSummary?.metadata?.extraction) ?? 'Unknown'}
            </Field>
          </div>
        </section>
      )}

      {!citation && captures.length > 0 && (
        <section className="inspector-section" aria-labelledby="captures-heading">
          <h4 id="captures-heading">Capture versions</h4>
          <div className="inspector-captures" role="group" aria-label="Capture versions">
            {captures.map((capture) => {
              const isSelected = capture.id === effectiveCaptureId;
              return (
                <button
                  key={capture.id}
                  type="button"
                  className={`inspector-capture${isSelected ? ' is-selected' : ''}`}
                  aria-pressed={isSelected}
                  onClick={() =>
                    updateSelection({ captureId: capture.id, start: null })
                  }
                >
                  <span className="inspector-capture-kind">
                    {capture.isCurrent ? 'Current capture' : 'Older capture'}
                  </span>
                  <code>{shortId(capture.id)}</code>
                  <span className="inspector-capture-meta">
                    {capture.charLength} code points ·{' '}
                    {capture.captureKind ?? 'kind unknown'}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {activeEvidence && !effectiveCaptureId && (
        <div className="inspector-state" role="status">
          No immutable capture is recorded for this source, so its text cannot be
          shown. Captures are not created by this read-only view.
        </div>
      )}

      {!captureSelectionKnown && (
        <div className="inspector-state" role="status">
          Capture {shortId(captureId)} is not recorded for this evidence. Select a
          listed capture version or close the inspector.
        </div>
      )}

      {activeEvidence && effectiveCaptureId && captureSelectionKnown && (
        <section className="inspector-section" aria-labelledby="capture-text-heading">
          <h4 id="capture-text-heading">Captured text</h4>
          {windowQuery.isLoading && (
            <div className="inspector-state" role="status">
              Loading capture window…
            </div>
          )}
          {windowQuery.error != null &&
            (isNotFound(windowQuery.error) ? (
              <div className="inspector-state inspector-state--error" role="alert">
                <AlertTriangle size={16} />
                <div>
                  <strong>Capture not found for this evidence.</strong>
                  <p>
                    The selected capture version may have been removed from this case
                    payload. Choose another listed version.
                  </p>
                </div>
              </div>
            ) : isUnprocessable(windowQuery.error) ? (
              <div className="inspector-state inspector-state--error" role="alert">
                <AlertTriangle size={16} />
                <div>
                  <strong>The requested text window is outside this capture.</strong>
                  <p>
                    {windowQuery.error instanceof Error
                      ? windowQuery.error.message
                      : 'The range was rejected.'}
                  </p>
                  <div className="inspector-state-actions">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => updateSelection({ start: 0 })}
                    >
                      Start of capture
                    </button>
                    {passage?.startChar !== null && passage?.startChar !== undefined && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() =>
                          updateSelection({
                            start: Math.max(0, passage.startChar! - CONTEXT_BEFORE),
                          })
                        }
                      >
                        Jump to quotation
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="inspector-state inspector-state--error" role="alert">
                <AlertTriangle size={16} />
                <div>
                  <strong>Failed to load the capture window.</strong>
                  <p>
                    {windowQuery.error instanceof Error
                      ? windowQuery.error.message
                      : 'The text could not be loaded.'}
                  </p>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => void windowQuery.refetch()}
                  >
                    <RefreshCw size={14} /> Retry
                  </button>
                </div>
              </div>
            ))}

          {windowQuery.data && (
            <CaptureWindowView
              text={windowQuery.data.text}
              start={windowQuery.data.start}
              length={windowQuery.data.length}
              totalLength={windowQuery.data.totalLength}
              highlight={
                passage && passageMatchesCapture && isExactAlignment(passage.alignmentStatus)
                  ? splitHighlight(
                      windowQuery.data.text,
                      windowQuery.data.start,
                      passage.quote,
                      passage.startChar,
                      passage.endChar
                    )
                  : null
              }
              exactAlignment={
                Boolean(
                  passage &&
                    passageMatchesCapture &&
                    isExactAlignment(passage.alignmentStatus)
                )
              }
              quoteStart={passage?.startChar ?? null}
              onPrevious={() =>
                updateSelection({
                  start: Math.max(0, windowQuery.data!.start - WINDOW_LENGTH),
                })
              }
              onNext={() =>
                updateSelection({
                  start: windowQuery.data!.start + windowQuery.data!.length,
                })
              }
              onJump={() =>
                updateSelection({
                  start: Math.max(0, (passage?.startChar ?? 0) - CONTEXT_BEFORE),
                })
              }
              onStart={() => updateSelection({ start: 0 })}
            />
          )}
        </section>
      )}
    </section>
  );
};

interface CaptureWindowViewProps {
  text: string;
  start: number;
  length: number;
  totalLength: number;
  highlight: { before: string; match: string; after: string } | null;
  exactAlignment: boolean;
  quoteStart: number | null;
  onPrevious: () => void;
  onNext: () => void;
  onJump: () => void;
  onStart: () => void;
}

const CaptureWindowView: React.FC<CaptureWindowViewProps> = ({
  text,
  start,
  length,
  totalLength,
  highlight,
  exactAlignment,
  quoteStart,
  onPrevious,
  onNext,
  onJump,
  onStart,
}) => {
  const end = start + length;
  const atStart = start <= 0;
  const atEnd = end >= totalLength;
  const windowText = Array.from(text);

  return (
    <div className="inspector-window">
      <div className="inspector-window-status">
        <span>
          Showing code points {start}–{end} of {totalLength} ({codePointLength(text)}{' '}
          returned)
        </span>
        <div className="inspector-window-actions">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onPrevious}
            disabled={atStart}
          >
            <ChevronLeft size={14} /> Previous window
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onNext}
            disabled={atEnd}
          >
            Next window <ChevronRight size={14} />
          </button>
          {quoteStart !== null && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onJump}>
              Jump to quotation
            </button>
          )}
          {!atStart && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onStart}>
              Start of capture
            </button>
          )}
        </div>
      </div>

      {windowText.length === 0 ? (
        <div className="inspector-state" role="status">
          This window starts at the end of the capture, so there is no text to show.
        </div>
      ) : (
        <pre className="inspector-capture-text" data-testid="capture-text">
          {highlight ? (
            <>
              <span>{highlight.before}</span>
              <mark>{highlight.match}</mark>
              <span>{highlight.after}</span>
            </>
          ) : (
            text
          )}
        </pre>
      )}

      {exactAlignment && !highlight && windowText.length > 0 && (
        <div className="inspector-state" role="status">
          The validated quotation is outside this window or could not be matched
          exactly in the returned text.
          {quoteStart !== null && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onJump}>
              <ExternalLink size={14} /> Jump to quotation
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default EvidenceInspector;
