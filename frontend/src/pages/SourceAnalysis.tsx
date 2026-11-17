import React from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { Evidence } from '../types/backend-models';
import { getEvidenceForCase } from '../services/api';
import Card, { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import Button from '../components/design-system/Button';
import './SourceAnalysis.css';

/**
 * Source analysis for a case.
 *
 * Counts only what each evidence record actually stores. Publisher names are
 * never used to guess a region, political leaning or factuality rating, and no
 * baseline/benchmark scores are invented.
 */

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

export const SourceAnalysis: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  const { data: evidence, isLoading, error, refetch } = useQuery({
    queryKey: ['evidence', id],
    queryFn: () => getEvidenceForCase(id!),
    enabled: !!id,
    refetchInterval: 15000,
  });

  const items: Evidence[] = evidence ?? [];
  const total = items.length;

  const byType = countBy(items.map((item) => item.sourceType || null));
  const byPublisher = countBy(items.map((item) => item.publisher || null));
  const byCredibility = countBy(items.map((item) => item.credibilityTier || null));
  const withoutCredibility = items.filter((item) => !item.credibilityTier).length;

  const repeatedUrls = (() => {
    const urlCounts = new Map<string, number>();
    items.forEach((item) => {
      if (!item.canonicalUrl) return;
      urlCounts.set(item.canonicalUrl, (urlCounts.get(item.canonicalUrl) || 0) + 1);
    });
    return Array.from(urlCounts.entries()).filter(([, count]) => count > 1);
  })();

  return (
    <div className="source-analysis">
      <div className="source-analysis-header">
        <div>
          <h1>Source Analysis</h1>
          <p className="source-analysis-subtitle">
            Recorded counts for this case's evidence items. Bias, factuality and independence
            assessments are not provided by this read API, so none is shown.
          </p>
        </div>
        <Button variant="secondary" onClick={() => refetch()}>Refresh</Button>
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
            <div className="source-analysis-state" role="status">Loading evidence records…</div>
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
              <Button variant="secondary" onClick={() => refetch()}>Retry</Button>
            </div>
          </CardBody>
        </Card>
      ) : total === 0 ? (
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
          <div className="source-analysis-stats">
            <Card padding="sm">
              <CardBody>
                <div className="source-analysis-stat-label">Evidence Items</div>
                <div className="source-analysis-stat-value">{total}</div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="source-analysis-stat-label">Source Types Recorded</div>
                <div className="source-analysis-stat-value">{byType.length}</div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="source-analysis-stat-label">Publishers Recorded</div>
                <div className="source-analysis-stat-value">{byPublisher.length}</div>
              </CardBody>
            </Card>
            <Card padding="sm">
              <CardBody>
                <div className="source-analysis-stat-label">Credibility Labels Recorded</div>
                <div className="source-analysis-stat-value">
                  {byCredibility.length}
                  {withoutCredibility > 0 && (
                    <span className="source-analysis-stat-note">
                      {' '}· {withoutCredibility} without a label
                    </span>
                  )}
                </div>
              </CardBody>
            </Card>
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
                        <div className="source-analysis-bar-fill" style={{ width: barWidth(count, total) }} />
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
                <CardTitle>Publishers Recorded</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="source-analysis-bars">
                  {byPublisher.map(([publisher, count]) => (
                    <div key={publisher} className="source-analysis-publisher-row">
                      <span className="source-analysis-bar-label">{publisher}</span>
                      <Badge variant="neutral" size="sm">{count}</Badge>
                    </div>
                  ))}
                  {items.filter((item) => !item.publisher).length > 0 && (
                    <div className="source-analysis-bar-note">
                      {items.filter((item) => !item.publisher).length} evidence item(s) have no
                      recorded publisher.
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
                        <div className="source-analysis-bar-fill" style={{ width: barWidth(count, total) }} />
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
                <div className="source-analysis-state source-analysis-state--unavailable" role="status">
                  <Badge variant="neutral" size="sm">Not provided</Badge>
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
                      The same canonical URL is recorded on more than one evidence item. These remain
                      separate evidence records; this is not a source-independence analysis.
                    </p>
                    <ul className="source-analysis-urls">
                      {repeatedUrls.map(([url, count]) => (
                        <li key={url}>
                          <span className="source-analysis-url">{url}</span>
                          <Badge variant="neutral" size="sm">{count} records</Badge>
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
