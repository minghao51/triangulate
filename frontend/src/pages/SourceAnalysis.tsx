import React from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Evidence } from '../types/backend-models';
import {
  getCaseSources,
  getEvidenceForCase,
  type SourceDependencyGroup,
  type SourcePolicy,
  type SourceSummary,
} from '../services/api';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import Button from '../components/design-system/Button';
import './SourceAnalysis.css';

/**
 * Source analysis for a case.
 *
 * Two reads, nothing more:
 *
 * 1. the existing source-dependency summary (`GET /api/cases/{id}/sources`),
 *    which is the only source of the publisher/group counts; and
 * 2. one case-keyed evidence collection read, used only for the recorded
 *    evidence-metadata distributions kept from the previous screen.
 *
 * There is no per-source or per-evidence detail fan-out, and no count from the
 * summary is turned into an independence, bias or factuality judgement. Copies,
 * syndicated repeats and model agreement never count as corroboration.
 */

const MEMBERS_RENDERED = 10;
const PUBLISHERS_RENDERED = 25;

const DEPENDENCY_REASON_LABELS: Record<string, string> = {
  same_source_url: 'same normalized source URL',
  same_publisher: 'same publisher key',
  identical_normalized_capture: 'identical long captured text',
  same_case_article: 'same case article',
  documented_common_origin: 'documented common origin',
};

const INDEPENDENCE_LABELS: Record<SourceSummary['independenceStatus'], string> = {
  unknown: 'Unknown — no independence determined',
  dependency_detected: 'Dependency detected between recorded sources',
};

const countBy = (values: Array<string | null>): Array<[string, number]> => {
  const counts = new Map<string, number>();
  values.forEach((value) => {
    if (!value) return;
    counts.set(value, (counts.get(value) || 0) + 1);
  });
  return Array.from(counts.entries()).sort(([, a], [, b]) => b - a);
};

const percentage = (count: number, total: number): string => {
  if (!Number.isFinite(total) || total <= 0) return 'n/a';
  return `${((count / total) * 100).toFixed(1)}%`;
};

const barWidth = (count: number, total: number): string => {
  if (!Number.isFinite(total) || total <= 0) return '0%';
  return `${Math.min(100, (count / total) * 100)}%`;
};

const dependencyReasonLabel = (reason: string): string =>
  DEPENDENCY_REASON_LABELS[reason] ?? reason;

const unknownIfEmpty = (value: string | null | undefined): string =>
  typeof value === 'string' && value.trim() !== '' ? value : 'Unknown';

const MetricCard: React.FC<{ label: string; value: React.ReactNode; note?: string }> = ({
  label,
  value,
  note,
}) => (
  <Card padding="sm">
    <CardBody>
      <div className="source-analysis-stat-label">{label}</div>
      <div className="source-analysis-stat-value">{value}</div>
      {note && <div className="source-analysis-stat-note">{note}</div>}
    </CardBody>
  </Card>
);

const DependencyGroupView: React.FC<{ group: SourceDependencyGroup }> = ({ group }) => {
  const shown = group.members.slice(0, MEMBERS_RENDERED);
  return (
    <li className="source-analysis-group">
      <div className="source-analysis-group-head">
        <code className="source-analysis-group-id" title={group.id}>
          {group.id}
        </code>
        <Badge variant="neutral" size="sm">
          {group.evidenceCount} evidence record{group.evidenceCount === 1 ? '' : 's'}
        </Badge>
      </div>
      {group.reasons.length > 0 && (
        <p className="source-analysis-bar-note">
          Recorded dependency reasons:{' '}
          {group.reasons.map(dependencyReasonLabel).join(', ')}.
        </p>
      )}
      {group.publisherKeys.length > 0 && (
        <p className="source-analysis-bar-note">
          Publisher keys in this group: {group.publisherKeys.join(', ')}.
        </p>
      )}
      {shown.length === 0 ? (
        <p className="source-analysis-bar-note">
          No member record is listed for this group in the summary.
        </p>
      ) : (
        <ul className="source-analysis-group-members">
          {shown.map((member) => (
            <li
              key={`${member.evidenceId}-${member.captureId ?? 'no-capture'}`}
              className="source-analysis-member"
            >
              <div className="source-analysis-member-head">
                <code title={member.evidenceId}>{member.evidenceId}</code>
                <span>
                  {unknownIfEmpty(member.publisher)} · {unknownIfEmpty(member.publisherKey)}
                </span>
                {member.publisherKeyProvisional && (
                  <Badge variant="neutral" size="sm">
                    provisional host
                  </Badge>
                )}
              </div>
              <div className="source-analysis-member-meta">
                capture {unknownIfEmpty(member.captureId)} ·{' '}
                {unknownIfEmpty(member.captureKind)} ·{' '}
                {member.captureCharLength === null
                  ? 'length unknown'
                  : `${member.captureCharLength} code points`}
              </div>
              {member.copyNonWhitespaceCount > 0 && (
                <div className="source-analysis-member-meta">
                  {member.copyNonWhitespaceCount} non-whitespace code points compared by the copy
                  fingerprint.
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {group.members.length > shown.length && (
        <p className="source-analysis-bar-note">
          {group.members.length - shown.length} further member record(s) in this group are not
          rendered here.
        </p>
      )}
    </li>
  );
};

const PolicyDetails: React.FC<{ policy: SourcePolicy }> = ({ policy }) => (
  <details className="source-analysis-policy">
    <summary>Source dependency policy (server-reported)</summary>
    <p className="source-analysis-bar-note">
      Policy version: {unknownIfEmpty(policy.version)}. Text fingerprint:{' '}
      {unknownIfEmpty(policy.textFingerprint)} with{' '}
      {unknownIfEmpty(policy.textFingerprintNormalization)} normalization; a copy match needs at
      least {policy.minCopyNonWhitespaceCodePoints} non-whitespace code points.
    </p>
    <dl className="source-analysis-policy-list">
      <div>
        <dt>URL normalization</dt>
        <dd>{policy.urlNormalization.join(', ') || 'Unknown'}</dd>
      </div>
      <div>
        <dt>Publisher identity</dt>
        <dd>{policy.publisherIdentity.join(', ') || 'Unknown'}</dd>
      </div>
      <div>
        <dt>Dependency edges</dt>
        <dd>{policy.dependencyEdges.join(', ') || 'Unknown'}</dd>
      </div>
    </dl>
  </details>
);

const SummaryLimitations: React.FC<{ policy: SourcePolicy }> = ({ policy }) => (
  <section
    className="source-analysis-limitations"
    aria-labelledby="source-analysis-limitations-heading"
  >
    <h3 id="source-analysis-limitations-heading">What this summary does not establish</h3>
    <ul>
      <li>
        An aggregated publisher summary is not proof of independent corroboration. It counts
        recorded evidence records and observed publisher identities; it does not show that any two
        of them are independent.
      </li>
      <li>
        Copies, syndicated repeats and shared wire text are not independent sources. They are
        grouped as a detected dependency, and repeated text does not add corroboration.
      </li>
      <li>
        Model consensus is not truth. Agreement between extraction models is not verification and
        is not shown as support for a claim.
      </li>
      <li>
        A missing dependency is not proof of independence. Absent dependency information stays
        &ldquo;unknown&rdquo;, never &ldquo;none&rdquo; and never &ldquo;verified
        independent&rdquo;.
      </li>
      <li>
        Grouping uses recorded publisher metadata, normalized URLs and capture text fingerprints
        only. It does not read whether a claim is true, and it does not rate bias or factuality.
      </li>
    </ul>
    {policy.limitations.length > 0 && (
      <>
        <h4>Limitations stated by the source policy</h4>
        <ul>
          {policy.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </>
    )}
    <PolicyDetails policy={policy} />
  </section>
);

export const SourceAnalysis: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  // Exactly one sources-summary GET, case-scoped and current-only.
  const summaryQuery = useQuery({
    queryKey: ['case-sources', id],
    queryFn: () => getCaseSources(id!),
    enabled: !!id,
    refetchInterval: 15000,
  });

  // The single case-keyed evidence collection read kept for the recorded
  // metadata distributions. No per-evidence or per-source detail is fetched.
  const evidenceQuery = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => getEvidenceForCase(id!),
    enabled: !!id,
  });

  const retryAll = () => {
    if (summaryQuery.error) void summaryQuery.refetch();
    if (evidenceQuery.error) void evidenceQuery.refetch();
    if (!summaryQuery.error && !evidenceQuery.error) {
      void summaryQuery.refetch();
      void evidenceQuery.refetch();
    }
  };

  const items: Evidence[] = evidenceQuery.data ?? [];
  const total = items.length;

  const byType = countBy(items.map((item) => item.sourceType || null));
  const byPublisher = countBy(items.map((item) => item.publisher || null));
  const byCredibility = countBy(items.map((item) => item.credibilityTier || null));
  const withoutCredibility = items.filter((item) => !item.credibilityTier).length;
  const withoutPublisher = items.filter((item) => !item.publisher).length;

  const repeatedUrls = (() => {
    const urlCounts = new Map<string, number>();
    items.forEach((item) => {
      if (!item.canonicalUrl) return;
      urlCounts.set(item.canonicalUrl, (urlCounts.get(item.canonicalUrl) || 0) + 1);
    });
    return Array.from(urlCounts.entries()).filter(([, count]) => count > 1);
  })();

  const summary = summaryQuery.data;
  const isLoading = summaryQuery.isLoading || evidenceQuery.isLoading;
  const error = summaryQuery.error ?? evidenceQuery.error ?? null;
  const publishersShown = summary?.publisherCounts.slice(0, PUBLISHERS_RENDERED) ?? [];
  const empty = !!summary && summary.evidenceCount === 0 && total === 0;

  return (
    <div className="source-analysis">
      <div className="source-analysis-header">
        <div>
          <h1>Source Analysis</h1>
          <p className="source-analysis-subtitle">
            Observed publishers and recorded dependency groups for this case, plus the source
            metadata actually stored on its evidence records. Bias, factuality and independence
            are not assessed by this read API, so none is shown.
          </p>
        </div>
        <Button variant="secondary" onClick={retryAll}>
          Refresh
        </Button>
      </div>

      {!id ? (
        <Card>
          <CardBody>
            <div className="source-analysis-state source-analysis-state--error" role="alert">
              No case ID in the route.
            </div>
          </CardBody>
        </Card>
      ) : isLoading ? (
        <Card>
          <CardBody>
            <div className="source-analysis-state" role="status">
              Loading the source summary…
            </div>
          </CardBody>
        </Card>
      ) : error ? (
        <Card>
          <CardBody>
            <div className="source-analysis-state source-analysis-state--error" role="alert">
              <p>
                Failed to load source data
                {error instanceof Error && error.message ? `: ${error.message}` : '.'}
              </p>
              <Button variant="secondary" onClick={retryAll}>
                Retry
              </Button>
            </div>
          </CardBody>
        </Card>
      ) : !summary ? (
        <Card>
          <CardBody>
            <div className="source-analysis-state" role="status">
              The source summary did not return a body. No count is invented to fill the gap.
            </div>
          </CardBody>
        </Card>
      ) : empty ? (
        <Card>
          <CardBody>
            <div className="source-analysis-state" role="status">
              <div className="source-analysis-state-title">No evidence records</div>
              <p>
                This case has no recorded evidence items, so there are no source counts to report.
                No source assessment can be inferred from this empty response.
              </p>
            </div>
          </CardBody>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Source summary (sources API)</CardTitle>
            </CardHeader>
            <CardBody>
              <p className="source-analysis-bar-note">
                Scope: {summary.scope === 'claim' ? 'claim' : 'case'}
                {summary.claimId ? ` ${summary.claimId}` : ` ${summary.caseId}`}. Counts come from
                the recorded source-dependency summary, not from the evidence list below.
              </p>

              <div className="source-analysis-stats">
                <MetricCard
                  label="Evidence Records (summary)"
                  value={summary.evidenceCount}
                  note="recorded evidence records in scope"
                />
                <MetricCard
                  label="Distinct Publishers"
                  value={summary.distinctPublisherCount}
                  note="observed publisher identities"
                />
                <MetricCard
                  label="Dependency Groups"
                  value={summary.dependencyGroupCount}
                  note="connected groups of dependent records"
                />
                <MetricCard
                  label="Unknown Publishers"
                  value={summary.unknownPublisherCount}
                  note="records with no recorded publisher"
                />
              </div>

              <p className="source-analysis-independence">
                Independence status: <strong>{INDEPENDENCE_LABELS[summary.independenceStatus]}</strong>
                . This is a policy outcome, not an independence score and not corroboration.
              </p>

              <SummaryLimitations policy={summary.policy} />
            </CardBody>
          </Card>

          <div className="source-analysis-grid">
            <Card className="source-analysis-wide">
              <CardHeader>
                <CardTitle>Dependency Group Detail</CardTitle>
              </CardHeader>
              <CardBody>
                {summary.groups.length === 0 ? (
                  <div className="source-analysis-state" role="status">
                    <p>
                      No dependency group is recorded for this case. That means no dependency was
                      detected from the recorded metadata; it does not mean the sources were shown
                      to be independent.
                    </p>
                  </div>
                ) : (
                  <>
                    <p className="source-analysis-bar-note">
                      Each group lists records that the server grouped as dependent. Grouping is
                      metadata evidence about copies and publisher identity, not an assessment of
                      agreement or truth.
                    </p>
                    <ul className="source-analysis-groups">
                      {summary.groups.map((group) => (
                        <DependencyGroupView key={group.id} group={group} />
                      ))}
                    </ul>
                  </>
                )}
              </CardBody>
            </Card>

            <Card className="source-analysis-wide">
              <CardHeader>
                <CardTitle>Recorded Publishers</CardTitle>
              </CardHeader>
              <CardBody>
                {summary.publisherCounts.length === 0 ? (
                  <div className="source-analysis-state" role="status">
                    No publisher identity is recorded for this case.
                  </div>
                ) : (
                  <>
                    <ul className="source-analysis-urls">
                      {publishersShown.map((publisher) => (
                        <li key={publisher.publisherKey}>
                          <span className="source-analysis-url">
                            {publisher.publisher ?? 'No publisher name'} ·{' '}
                            {publisher.publisherKey}
                            {publisher.provisional ? ' (provisional host)' : ''}
                          </span>
                          <Badge variant="neutral" size="sm">
                            {publisher.evidenceCount} record
                            {publisher.evidenceCount === 1 ? '' : 's'} ·{' '}
                            {publisher.dependencyGroupCount} group
                            {publisher.dependencyGroupCount === 1 ? '' : 's'}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                    {summary.publisherCounts.length > publishersShown.length && (
                      <p className="source-analysis-bar-note">
                        Showing {publishersShown.length} of {summary.publisherCounts.length}{' '}
                        recorded publishers; the rest stay in the summary response.
                      </p>
                    )}
                  </>
                )}
              </CardBody>
            </Card>
          </div>

          <div className="source-analysis-section-heading">
            <h2>Recorded evidence metadata</h2>
            <p className="source-analysis-subtitle">
              These counts are derived from this case's evidence list in the browser. They are
              labelled separately from the source summary above and are metadata coverage only —
              they are not a source-independence analysis.
            </p>
          </div>

          <div className="source-analysis-stats">
            <MetricCard label="Evidence Items" value={total} />
            <MetricCard label="Source Types Recorded" value={byType.length} />
            <MetricCard label="Publishers Recorded" value={byPublisher.length} />
            <MetricCard
              label="Credibility Labels Recorded"
              value={
                <>
                  {byCredibility.length}
                  {withoutCredibility > 0 && (
                    <span className="source-analysis-stat-note">
                      {' '}
                      · {withoutCredibility} without a label
                    </span>
                  )}
                </>
              }
            />
          </div>

          <div className="source-analysis-grid">
            <Card>
              <CardHeader>
                <CardTitle>Source Type Distribution</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="source-analysis-bars">
                  {byType.map(([type, count]) => (
                    <div key={type}>
                      <div className="source-analysis-bar-row">
                        <span className="source-analysis-bar-label">{type}</span>
                        <span className="source-analysis-bar-value">
                          {count} ({percentage(count, total)})
                        </span>
                      </div>
                      <div className="source-analysis-bar-track">
                        <div
                          className="source-analysis-bar-fill"
                          style={{ width: barWidth(count, total) }}
                        />
                      </div>
                    </div>
                  ))}
                  {byType.length === 0 && (
                    <div className="source-analysis-state" role="status">
                      No source type is recorded for these evidence items.
                    </div>
                  )}
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Publishers Recorded (evidence metadata)</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="source-analysis-bars">
                  {byPublisher.map(([publisher, count]) => (
                    <div key={publisher} className="source-analysis-publisher-row">
                      <span className="source-analysis-bar-label">{publisher}</span>
                      <Badge variant="neutral" size="sm">
                        {count}
                      </Badge>
                    </div>
                  ))}
                  {withoutPublisher > 0 && (
                    <div className="source-analysis-bar-note">
                      {withoutPublisher} evidence item(s) have no recorded publisher.
                    </div>
                  )}
                  {byPublisher.length === 0 && (
                    <div className="source-analysis-state" role="status">
                      No publisher is recorded for these evidence items.
                    </div>
                  )}
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Recorded Credibility Labels</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="source-analysis-bars">
                  {byCredibility.map(([tier, count]) => (
                    <div key={tier}>
                      <div className="source-analysis-bar-row">
                        <span className="source-analysis-bar-label">{tier}</span>
                        <span className="source-analysis-bar-value">
                          {count} ({percentage(count, total)})
                        </span>
                      </div>
                      <div className="source-analysis-bar-track">
                        <div
                          className="source-analysis-bar-fill"
                          style={{ width: barWidth(count, total) }}
                        />
                      </div>
                    </div>
                  ))}
                  {byCredibility.length === 0 && (
                    <div className="source-analysis-state" role="status">
                      No credibility label is recorded (not provided) for these evidence items.
                    </div>
                  )}
                  {withoutCredibility > 0 && (
                    <div className="source-analysis-bar-note">
                      {withoutCredibility} of {total} evidence item(s) have no recorded credibility
                      label — treated as not recorded/provided, not as a low score.
                    </div>
                  )}
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Bias &amp; Factuality</CardTitle>
              </CardHeader>
              <CardBody>
                <div
                  className="source-analysis-state source-analysis-state--unavailable"
                  role="status"
                >
                  <Badge variant="neutral" size="sm">
                    Not provided
                  </Badge>
                  <p>
                    Bias, factuality and leaning assessments are not provided by this read API.
                    Publisher names are not used to infer political orientation or accuracy.
                  </p>
                </div>
              </CardBody>
            </Card>

            <Card className="source-analysis-wide">
              <CardHeader>
                <CardTitle>Repeated Canonical URLs</CardTitle>
              </CardHeader>
              <CardBody>
                {repeatedUrls.length === 0 ? (
                  <div className="source-analysis-state" role="status">
                    No canonical URL appears more than once among these evidence records.
                  </div>
                ) : (
                  <>
                    <p className="source-analysis-bar-note">
                      The same canonical URL is recorded on more than one evidence item. These
                      remain separate evidence records and are not independent sources; this is
                      not a source-independence analysis.
                    </p>
                    <ul className="source-analysis-urls">
                      {repeatedUrls.map(([url, count]) => (
                        <li key={url}>
                          <span className="source-analysis-url">{url}</span>
                          <Badge variant="neutral" size="sm">
                            {count} records
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export default SourceAnalysis;
