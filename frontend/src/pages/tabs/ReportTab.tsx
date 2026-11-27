import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Archive,
  CheckCircle2,
  ChevronLeft,
  Clock3,
  Download,
  FileJson,
  FileWarning,
} from 'lucide-react';

import type { ArtifactDescriptor, ReportData, RunHistoryItem } from '../../types/backend-models';
import {
  downloadInvestigationRunArtifact,
  downloadManifestReport,
  downloadMarkdownReport,
  getInvestigationRunArtifacts,
  getInvestigationRuns,
  getReportForCase,
  getRunHistoryForCase,
} from '../../services/api';
import { isNotFound } from '../../services/api-error';
import { buildReportUrl, parseReportSelection, REPORT_PARAMS } from '../../services/deep-links';
import Badge from '../../components/design-system/Badge';
import Button from '../../components/design-system/Button';
import Card from '../../components/design-system/Card';
import ReaderState from '../../components/design-system/ReaderState';
import './ReportTab.css';

interface ReportTabProps {
  caseId: string;
  refreshToken?: number;
}

/**
 * Truthful read states for the current stored report.
 *
 * `pending` is only reachable with recorded in-progress evidence from the run
 * history (a stage attempt recorded as `running`/`pending`). A report the API
 * merely reports as `status: 'pending'` while nothing is recorded as running is
 * NOT treated as pending — it is a missing report.
 */
type ReadState = 'no-case' | 'loading' | 'unavailable' | 'not-generated' | 'pending' | 'ready';

type DownloadKind = 'markdown' | 'manifest';

interface DownloadFailure {
  kind: DownloadKind;
  message: string;
}

// ---------------------------------------------------------------------------
// Safe markdown rendering
//
// The stored markdown is parsed into plain strings and rendered as semantic
// JSX. Nothing here interprets raw HTML: React escapes every text node, so a
// `<script>` or `<img onerror>` payload stays inert, visible text.
// ---------------------------------------------------------------------------

type MarkdownBlock =
  | { kind: 'heading'; level: 1 | 2 | 3 | 4 | 5 | 6; text: string }
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'quote'; lines: string[] }
  | { kind: 'code'; text: string }
  | { kind: 'rule' };

const HEADING_PATTERN = /^(#{1,6})\s+(.*)$/;
const UNORDERED_PATTERN = /^[-*+]\s+(.*)$/;
const ORDERED_PATTERN = /^\d+[.)]\s+(.*)$/;
const RULE_PATTERN = /^(?:-{3,}|\*{3,}|_{3,})$/;
const INLINE_PATTERN = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g;

/** True when the line opens (or terminates) a block instead of continuing a paragraph. */
function startsBlock(line: string): boolean {
  const trimmed = line.trim();
  return (
    trimmed === '' ||
    trimmed.startsWith('```') ||
    HEADING_PATTERN.test(trimmed) ||
    UNORDERED_PATTERN.test(trimmed) ||
    ORDERED_PATTERN.test(trimmed) ||
    trimmed.startsWith('>') ||
    RULE_PATTERN.test(trimmed)
  );
}

function parseMarkdown(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const trimmed = lines[index].trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith('```')) {
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push({ kind: 'code', text: body.join('\n') });
      continue;
    }

    const heading = HEADING_PATTERN.exec(trimmed);
    if (heading) {
      const level = Math.min(heading[1].length, 6) as 1 | 2 | 3 | 4 | 5 | 6;
      blocks.push({ kind: 'heading', level, text: heading[2].trim() });
      index += 1;
      continue;
    }

    if (RULE_PATTERN.test(trimmed)) {
      blocks.push({ kind: 'rule' });
      index += 1;
      continue;
    }

    if (UNORDERED_PATTERN.test(trimmed) || ORDERED_PATTERN.test(trimmed)) {
      const ordered = ORDERED_PATTERN.test(trimmed);
      const items: string[] = [];
      while (index < lines.length) {
        const itemLine = lines[index].trim();
        const item = ordered ? ORDERED_PATTERN.exec(itemLine) : UNORDERED_PATTERN.exec(itemLine);
        if (!item) break;
        items.push(item[1].trim());
        index += 1;
      }
      blocks.push({ kind: 'list', ordered, items });
      continue;
    }

    if (trimmed.startsWith('>')) {
      const quoted: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith('>')) {
        quoted.push(lines[index].trim().replace(/^>\s?/, ''));
        index += 1;
      }
      blocks.push({ kind: 'quote', lines: quoted });
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && !startsBlock(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ kind: 'paragraph', text: paragraph.join(' ') });
  }

  return blocks;
}

/** Emphasised spans are built from strings only; no HTML is parsed or executed. */
function renderInline(text: string, keyPrefix: string): React.ReactNode {
  const parts = text.split(INLINE_PATTERN).filter((part) => part !== '');
  if (parts.length <= 1) {
    return text;
  }
  return parts.map((part, partIndex) => {
    const key = `${keyPrefix}-inline-${partIndex}`;
    if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.length > 2 && part.startsWith('`') && part.endsWith('`')) {
      return <code key={key}>{part.slice(1, -1)}</code>;
    }
    return <React.Fragment key={key}>{part}</React.Fragment>;
  });
}

function renderHeading(block: { level: 1 | 2 | 3 | 4 | 5 | 6; text: string }, key: string): React.ReactNode {
  const content = renderInline(block.text, key);
  switch (block.level) {
    case 1:
      return (
        <h1 key={key} data-testid="report-heading-1">
          {content}
        </h1>
      );
    case 2:
      return (
        <h2 key={key} data-testid="report-heading-2">
          {content}
        </h2>
      );
    case 3:
      return (
        <h3 key={key} data-testid="report-heading-3">
          {content}
        </h3>
      );
    case 4:
      return (
        <h4 key={key} data-testid="report-heading-4">
          {content}
        </h4>
      );
    case 5:
      return (
        <h5 key={key} data-testid="report-heading-5">
          {content}
        </h5>
      );
    default:
      return (
        <h6 key={key} data-testid="report-heading-6">
          {content}
        </h6>
      );
  }
}

function renderBlocks(blocks: MarkdownBlock[]): React.ReactNode[] {
  return blocks.map((block, index) => {
    const key = `block-${index}`;
    switch (block.kind) {
      case 'heading':
        return renderHeading(block, key);
      case 'paragraph':
        return <p key={key}>{renderInline(block.text, key)}</p>;
      case 'list': {
        const items = block.items.map((item, itemIndex) => (
          <li key={`${key}-item-${itemIndex}`}>
            {renderInline(item, `${key}-item-${itemIndex}`)}
          </li>
        ));
        return block.ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>;
      }
      case 'quote':
        return (
          <blockquote key={key}>
            {block.lines.map((line, lineIndex) => (
              <p key={`${key}-line-${lineIndex}`}>{renderInline(line, `${key}-line-${lineIndex}`)}</p>
            ))}
          </blockquote>
        );
      case 'code':
        return (
          <pre key={key}>
            <code>{block.text}</code>
          </pre>
        );
      case 'rule':
        return <hr key={key} />;
      default:
        return null;
    }
  });
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

const isInProgress = (run: RunHistoryItem): boolean =>
  run.status === 'running' || run.status === 'pending';

function errorMessage(error: unknown): string | null {
  return error instanceof Error ? error.message : null;
}

function renderStatusBadge(
  readState: ReadState,
  status: ReportData['status'] | undefined
): React.ReactNode {
  switch (readState) {
    case 'ready':
      return (
        <Badge variant="success">
          <CheckCircle2 size={12} aria-hidden="true" /> {status === 'generated' ? 'Generated' : 'Stored'}
        </Badge>
      );
    case 'pending':
      return (
        <Badge variant="warning">
          <Clock3 size={12} aria-hidden="true" /> Pending
        </Badge>
      );
    case 'not-generated':
      return (
        <Badge variant="neutral">
          <FileWarning size={12} aria-hidden="true" /> Not generated
        </Badge>
      );
    case 'unavailable':
      return (
        <Badge variant="danger">
          <FileWarning size={12} aria-hidden="true" /> Unavailable
        </Badge>
      );
    case 'loading':
      return (
        <Badge variant="info">
          <Clock3 size={12} aria-hidden="true" /> Loading
        </Badge>
      );
    default:
      return (
        <Badge variant="neutral">
          <FileWarning size={12} aria-hidden="true" /> No case
        </Badge>
      );
  }
}

// ---------------------------------------------------------------------------
// X02 / F20 run-pin helpers
// ---------------------------------------------------------------------------

/** How many recent recorded runs the pin selector lists (shared cache size). */
const RUN_SELECTOR_LIMIT = 50;

const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  report_markdown: 'Markdown report',
  report_json: 'JSON report',
  execution_manifest: 'Execution manifest',
};

/**
 * The only artifact types the F19 reader serves. A descriptor of any other type
 * is shown as recorded but explicitly not offered, never downloaded anyway.
 */
const OFFERED_ARTIFACT_TYPES = [
  'report_markdown',
  'report_json',
  'execution_manifest',
] as const;

function artifactTypeLabel(type: string): string {
  return ARTIFACT_TYPE_LABELS[type] ?? type;
}

function isOfferedArtifact(descriptor: ArtifactDescriptor): boolean {
  return (OFFERED_ARTIFACT_TYPES as readonly string[]).includes(descriptor.type);
}

/**
 * Plain wording for `checksumKind`. `payload_json` means the stored canonical
 * payload re-hashes to the recorded value; `unknown` means that could not be
 * established. Neither says anything about the bytes of a downloaded file.
 */
function checksumKindNote(kind: ArtifactDescriptor['checksumKind']): string {
  return kind === 'payload_json'
    ? 'the stored payload re-hashes to this value'
    : 'no stored payload to re-hash';
}

/** Grouped-run status wording; it is a run status, not a stage-attempt status. */
function runStatusLabel(status: string): string {
  switch (status) {
    case 'running':
      return 'Running';
    case 'succeeded':
      return 'Succeeded';
    case 'paused':
      return 'Paused';
    case 'failed':
      return 'Failed';
    case 'interrupted':
      return 'Interrupted';
    default:
      return status;
  }
}

function shortRunId(value: string): string {
  return value.length > 14 ? `${value.slice(0, 10)}…` : value;
}

/**
 * One failed artifact download on a pinned run.
 *
 * `missing` is the F19 404 (no bytes for this artifact of this run). It is a
 * distinct state: no substitute artifact, no other run's report and no
 * regeneration — only a re-read of the recorded descriptors.
 */
interface ArtifactFailure {
  artifactId: string;
  displayName: string;
  missing: boolean;
  message: string;
}

/**
 * Report reader for the current stored report and — X02/F20 — optionally one
 * run's frozen report.
 *
 * Both reads are keyed by case id, so a case switch can never render another
 * case's report or run history. `refreshToken` is a parent-driven freshness
 * signal only: it triggers a refetch and is deliberately not part of the keys.
 * Reads and downloads are separate states with separate retries; nothing here
 * asks the server to generate or recompute a report.
 *
 * X02/F20 adds one optional mode on top: an explicit run pin (`?reportRun=…`)
 * shows the frozen report artifacts one recorded grouped run published. The
 * current report stays the default, a pin is only ever entered through an
 * explicit link, and a pinned view never reads or substitutes the current
 * report.
 */
const ReportTab: React.FC<ReportTabProps> = ({ caseId, refreshToken = 0 }) => {
  // Browser-held pin: reload, Back/Forward and a shared link all keep exactly
  // the same run pinned. An absent key means the current report; a present but
  // empty key is an explicit pin that names no run (never silently "current").
  const [searchParams] = useSearchParams();
  const pinMode = searchParams.has(REPORT_PARAMS.run);
  const pinnedRunId = parseReportSelection(searchParams).runId;

  const {
    data: report,
    isLoading: reportLoading,
    error: reportError,
    refetch: refetchReport,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['report', caseId],
    queryFn: () => getReportForCase(caseId),
    // A pinned view never reads the current report: "current" is never an
    // implicit substitute for the run the operator asked for.
    enabled: Boolean(caseId) && !pinMode,
  });

  const {
    data: runHistory,
    isLoading: historyLoading,
    error: historyError,
    refetch: refetchHistory,
  } = useQuery({
    queryKey: ['run-history', caseId],
    queryFn: () => getRunHistoryForCase(caseId),
    enabled: Boolean(caseId) && !pinMode,
  });

  // Same key and limit as the Changes and Run-history tabs, so the recorded run
  // list is shared rather than fetched a second time for the same case.
  const {
    data: groupedRuns,
    error: groupedRunsError,
    refetch: refetchGroupedRuns,
  } = useQuery({
    queryKey: ['investigation-runs', caseId],
    queryFn: () => getInvestigationRuns(caseId, { limit: RUN_SELECTOR_LIMIT }),
    enabled: Boolean(caseId) && !pinMode,
    retry: false,
  });

  const {
    data: artifacts,
    isLoading: artifactsLoading,
    error: artifactsError,
    refetch: refetchArtifacts,
    dataUpdatedAt: artifactsUpdatedAt,
  } = useQuery({
    queryKey: ['investigation-run-artifacts', caseId, pinnedRunId],
    queryFn: () => getInvestigationRunArtifacts(caseId, pinnedRunId as string),
    enabled: Boolean(caseId) && pinMode && pinnedRunId !== null,
    retry: false,
  });

  const lastRefreshToken = useRef(refreshToken);
  useEffect(() => {
    if (lastRefreshToken.current === refreshToken) return;
    lastRefreshToken.current = refreshToken;
    if (pinMode) {
      if (pinnedRunId) void refetchArtifacts();
      return;
    }
    void refetchReport();
    void refetchHistory();
    void refetchGroupedRuns();
  }, [
    refreshToken,
    pinMode,
    pinnedRunId,
    refetchReport,
    refetchHistory,
    refetchGroupedRuns,
    refetchArtifacts,
  ]);

  const [downloading, setDownloading] = useState<DownloadKind | null>(null);
  const [downloadFailure, setDownloadFailure] = useState<DownloadFailure | null>(null);
  const [downloadingArtifactId, setDownloadingArtifactId] = useState<string | null>(null);
  const [artifactFailure, setArtifactFailure] = useState<ArtifactFailure | null>(null);

  const markdown = report?.markdownContent ?? '';
  const blocks = useMemo(() => (markdown.trim() ? parseMarkdown(markdown) : []), [markdown]);
  const hasInProgressEvidence = useMemo(
    () => (runHistory ?? []).some(isInProgress),
    [runHistory]
  );

  let readState: ReadState;
  if (!caseId) {
    readState = 'no-case';
  } else if (reportLoading) {
    readState = 'loading';
  } else if (reportError) {
    readState = 'unavailable';
  } else if (blocks.length > 0) {
    readState = 'ready';
  } else if (historyLoading) {
    // The report is absent; wait for the recorded run history before deciding
    // between "Not generated" and "Pending".
    readState = 'loading';
  } else if (hasInProgressEvidence) {
    readState = 'pending';
  } else if (historyError) {
    readState = 'unavailable';
  } else if (report?.status === 'generated') {
    readState = 'unavailable';
  } else {
    readState = 'not-generated';
  }

  const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  /**
   * A re-read only. In the pinned view this re-reads the recorded descriptors;
   * it never re-runs a download and never asks for a report to be produced.
   */
  const retryRead = () => {
    setDownloadFailure(null);
    setArtifactFailure(null);
    if (pinMode) {
      if (pinnedRunId) void refetchArtifacts();
      return;
    }
    void refetchReport();
    void refetchHistory();
    void refetchGroupedRuns();
  };

  const handleDownload = async (kind: DownloadKind) => {
    if (!caseId) return;
    setDownloading(kind);
    setDownloadFailure(null);
    try {
      if (kind === 'markdown') {
        await downloadMarkdownReport(caseId);
      } else {
        await downloadManifestReport(caseId);
      }
    } catch (error) {
      setDownloadFailure({
        kind,
        message: errorMessage(error) ?? 'The download failed.',
      });
    } finally {
      setDownloading(null);
    }
  };

  /**
   * One pinned-run artifact download, using only the F19 descriptor.
   *
   * A 404 is recorded as `missing` — no other artifact and no other run is
   * tried in its place, and nothing is regenerated.
   */
  const handleArtifactDownload = async (descriptor: ArtifactDescriptor) => {
    if (!caseId || !pinnedRunId) return;
    setDownloadingArtifactId(descriptor.artifactId);
    setArtifactFailure(null);
    try {
      await downloadInvestigationRunArtifact(caseId, pinnedRunId, descriptor);
    } catch (error) {
      setArtifactFailure({
        artifactId: descriptor.artifactId,
        displayName: descriptor.displayName,
        missing: isNotFound(error),
        message: errorMessage(error) ?? 'The download failed.',
      });
    } finally {
      setDownloadingArtifactId(null);
    }
  };

  let body: React.ReactNode;
  switch (readState) {
    case 'no-case':
      body = (
        <div data-testid="report-state-no-case" data-report-state="no-case">
          <ReaderState
            state="not-found"
            title="No case selected"
            description="Choose a case to read its stored report."
          />
        </div>
      );
      break;
    case 'loading':
      body = (
        <div data-testid="report-state-loading" data-report-state="loading">
          <ReaderState
            state="loading"
            title="Loading the stored report"
            description="Fetching the report stored for this case."
          />
        </div>
      );
      break;
    case 'unavailable': {
      if (reportError || historyError) {
        const source = reportError ?? historyError;
        body = (
          <div data-testid="report-state-unavailable" data-report-state="unavailable">
            <ReaderState
              state="network-error"
              title="Unavailable"
              description={
                reportError
                  ? 'The stored report could not be read. Retry the read; nothing is regenerated.'
                  : 'No stored report was returned and the recorded run history could not be read, so no in-progress stage can be confirmed.'
              }
              detail={errorMessage(source)}
              onRetry={retryRead}
              retryLabel="Retry read"
              lastFetched={lastFetched}
            />
          </div>
        );
      } else {
        // The read succeeded but returned no readable text for a record the API
        // reports as generated.
        body = (
          <div data-testid="report-state-unavailable" data-report-state="unavailable">
            <ReaderState
              state="empty"
              title="Unavailable"
              description="The stored report record contains no readable text."
              lastFetched={lastFetched}
            />
            <div className="report-state__actions">
              <Button
                variant="secondary"
                size="sm"
                onClick={retryRead}
                data-testid="report-retry-read"
              >
                Retry read
              </Button>
            </div>
          </div>
        );
      }
      break;
    }
    case 'not-generated':
      body = (
        <div data-testid="report-state-not-generated" data-report-state="not-generated">
          <ReaderState
            state="empty"
            title="Not generated"
            description="No stored report exists for this case and no recorded report stage is in progress."
            lastFetched={lastFetched}
          />
          <div className="report-state__actions">
            <Button variant="secondary" size="sm" onClick={retryRead} data-testid="report-retry-read">
              Retry read
            </Button>
          </div>
        </div>
      );
      break;
    case 'pending':
      body = (
        <div data-testid="report-state-pending" data-report-state="pending">
          <Card variant="bordered" padding="md" className="report-pending" role="status">
            <div className="report-pending__header">
              <Badge variant="warning">
                <Clock3 size={12} aria-hidden="true" /> Pending
              </Badge>
            </div>
            <h4 className="report-pending__title">Report generation in progress</h4>
            <p className="report-pending__description">
              A recorded report stage is still in progress for this case and no stored report exists
              yet. This view only reads stored data; it does not start or restart generation.
            </p>
            <div className="report-state__actions">
              <Button
                variant="secondary"
                size="sm"
                onClick={retryRead}
                data-testid="report-retry-read"
              >
                Retry read
              </Button>
            </div>
          </Card>
        </div>
      );
      break;
    default:
      body = (
        <article className="report-canvas glass-panel" data-testid="report-content" data-report-state="ready">
          <div className="markdown-body">{renderBlocks(blocks)}</div>
        </article>
      );
      break;
  }

  // -------------------------------------------------------------------------
  // X02 / F20 pinned run view
  //
  // This branch is reached only when the URL carries an explicit `reportRun`
  // key. It renders the recorded artifacts of that run and nothing else: no
  // current report, no nearby run, no regeneration.
  // -------------------------------------------------------------------------
  if (pinMode) {
    const descriptors = artifacts ?? [];
    const pinLastFetched = artifactsUpdatedAt
      ? new Date(artifactsUpdatedAt).toLocaleTimeString()
      : null;

    let pinBody: React.ReactNode;
    if (!caseId) {
      pinBody = (
        <div data-testid="report-state-no-case" data-report-state="no-case">
          <ReaderState
            state="not-found"
            title="No case selected"
            description="Choose a case before opening a recorded run's frozen report."
          />
        </div>
      );
    } else if (!pinnedRunId) {
      pinBody = (
        <div data-testid="report-state-run-not-recorded" data-report-state="run-not-recorded">
          <ReaderState
            state="not-found"
            title="Run not recorded"
            description="This link carries no usable run reference, so no frozen report can be addressed. Nothing nearby is shown in its place; open the current report or pick a run from the run history."
          />
          <div className="report-state__actions">
            <Link className="report-pin-link" to={buildReportUrl(caseId)}>
              Open the current report
            </Link>
          </div>
        </div>
      );
    } else if (artifactsLoading) {
      pinBody = (
        <div data-testid="report-state-pin-loading" data-report-state="pin-loading">
          <ReaderState
            state="loading"
            title="Loading the frozen report"
            description="Reading the report artifacts this run published."
          />
        </div>
      );
    } else if (artifactsError) {
      pinBody = isNotFound(artifactsError) ? (
        <div data-testid="report-state-run-not-recorded" data-report-state="run-not-recorded">
          <ReaderState
            state="not-found"
            title="Run not recorded"
            description="No recorded run in this case matches this run reference, or the run was removed. No nearby, newer or current report is substituted."
            detail={errorMessage(artifactsError)}
            lastFetched={pinLastFetched}
          />
          <div className="report-state__actions">
            <Link className="report-pin-link" to={buildReportUrl(caseId)}>
              Open the current report
            </Link>
            <Button
              variant="secondary"
              size="sm"
              onClick={retryRead}
              data-testid="report-pin-retry-read"
            >
              Retry read
            </Button>
          </div>
        </div>
      ) : (
        <div data-testid="report-state-pin-unavailable" data-report-state="pin-unavailable">
          <ReaderState
            state="network-error"
            title="Unavailable"
            description="The recorded artifacts for this run could not be read. Retry the read; nothing is regenerated and no other run is shown."
            detail={errorMessage(artifactsError)}
            onRetry={retryRead}
            retryLabel="Retry read"
            lastFetched={pinLastFetched}
          />
        </div>
      );
    } else if (descriptors.length === 0) {
      pinBody = (
        <div data-testid="report-state-run-no-report" data-report-state="run-no-report">
          <ReaderState
            state="empty"
            title="No published report for this run"
            description="This run is recorded but it published no report artifacts for this case. No other run's report is shown and nothing is regenerated."
            lastFetched={pinLastFetched}
          />
          <div className="report-state__actions">
            <Button
              variant="secondary"
              size="sm"
              onClick={retryRead}
              data-testid="report-pin-retry-read"
            >
              Retry read
            </Button>
          </div>
        </div>
      );
    } else {
      pinBody = (
        <section
          className="report-artifacts"
          aria-labelledby="report-artifacts-heading"
          data-testid="report-artifact-list"
        >
          <h4 id="report-artifacts-heading" className="report-artifacts__title">
            Recorded report artifacts
          </h4>
          <p className="report-artifacts__note">
            Exactly the artifacts this run recorded, and only the report types the publication
            step writes. Each checksum is the <strong>recorded payload checksum</strong> stored at
            publication: it describes that stored payload record, not the bytes of a downloaded
            file.
          </p>
          <ul className="report-artifacts__list">
            {descriptors.map((descriptor) => (
              <li
                key={descriptor.artifactId}
                className="report-artifact"
                data-testid="report-artifact"
                data-artifact-type={descriptor.type}
                data-artifact-id={descriptor.artifactId}
              >
                <div className="report-artifact__identity">
                  <span className="report-artifact__name">{descriptor.displayName}</span>
                  <span className="report-artifact__type">
                    {artifactTypeLabel(descriptor.type)}
                  </span>
                  <code className="report-artifact__type-code" title={descriptor.type}>
                    {descriptor.type}
                  </code>
                </div>
                <div className="report-artifact__checksum">
                  <span className="report-artifact__checksum-label">
                    Recorded payload checksum
                  </span>
                  <code
                    className="report-artifact__checksum-value"
                    data-testid="report-artifact-checksum"
                    title={descriptor.recordedChecksum ?? undefined}
                  >
                    {descriptor.recordedChecksum ?? 'not recorded'}
                  </code>
                  <span
                    className="report-artifact__checksum-kind"
                    data-testid="report-artifact-checksum-kind"
                  >
                    <code>{descriptor.checksumKind}</code> —{' '}
                    {checksumKindNote(descriptor.checksumKind)}
                  </span>
                </div>
                {isOfferedArtifact(descriptor) ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Download size={14} />}
                    loading={downloadingArtifactId === descriptor.artifactId}
                    disabled={downloadingArtifactId !== null}
                    onClick={() => {
                      void handleArtifactDownload(descriptor);
                    }}
                    data-testid={`report-artifact-download-${descriptor.type}`}
                  >
                    Download {descriptor.displayName}
                  </Button>
                ) : (
                  <span className="report-artifact__not-offered" data-testid="report-artifact-not-offered">
                    Not an offered artifact type
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      );
    }

    return (
      <div
        className="report-container p-base"
        data-testid="report-pinned-run"
        data-pinned-run-id={pinnedRunId ?? ''}
      >
        <div className="report-header">
          <div className="report-title-area">
            <h3>Frozen report for a recorded run</h3>
            <Badge variant="info">
              <Archive size={12} aria-hidden="true" /> Recorded run
            </Badge>
          </div>
          <div className="report-actions">
            <Link
              className="report-pin-link"
              to={buildReportUrl(caseId)}
              data-testid="report-back-to-current"
            >
              <ChevronLeft size={14} aria-hidden="true" /> Back to the current report
            </Link>
          </div>
        </div>

        <p className="report-subtitle">
          The report artifacts this run published, read from the record. Nothing here is
          regenerated, recomputed or replaced by another run's report.
        </p>

        <div className="report-pin-identity">
          <span className="report-pin-identity__label">Pinned grouped run ID</span>
          <code
            className="report-pin-identity__id"
            data-testid="report-pinned-run-id"
            title={pinnedRunId ?? undefined}
          >
            {pinnedRunId ?? 'not recorded in this link'}
          </code>
          <span className="report-pin-identity__note">
            A grouped run ID identifies one investigation invocation; it is not a stage attempt ID.
          </span>
        </div>

        {artifactFailure && artifactFailure.missing ? (
          <Card
            variant="bordered"
            padding="md"
            className="report-download-error"
            data-testid="report-state-artifact-missing"
            data-report-state="artifact-missing"
            role="alert"
          >
            <div className="report-download-error__header">
              <Badge variant="danger">
                <FileWarning size={12} aria-hidden="true" /> Artifact missing
              </Badge>
            </div>
            <p className="report-download-error__description">
              The recorded artifact <strong>{artifactFailure.displayName}</strong> is not available
              for this run. No other artifact, run or current report is substituted, and nothing
              is regenerated.
            </p>
            <p className="report-download-error__detail">{artifactFailure.message}</p>
            <div className="report-state__actions">
              <Button
                variant="secondary"
                size="sm"
                onClick={retryRead}
                data-testid="report-artifact-retry-read"
              >
                Retry read
              </Button>
            </div>
          </Card>
        ) : null}

        {artifactFailure && !artifactFailure.missing ? (
          <Card
            variant="bordered"
            padding="md"
            className="report-download-error"
            data-testid="report-artifact-download-error"
            data-report-state="download-error"
            role="alert"
          >
            <div className="report-download-error__header">
              <Badge variant="danger">
                <FileWarning size={12} aria-hidden="true" /> Download error
              </Badge>
            </div>
            <p className="report-download-error__description">
              The recorded artifact <strong>{artifactFailure.displayName}</strong> could not be
              downloaded. The stored record itself was not changed.
            </p>
            <p className="report-download-error__detail">{artifactFailure.message}</p>
            <div className="report-state__actions">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  const failed = descriptors.find(
                    (item) => item.artifactId === artifactFailure.artifactId
                  );
                  if (failed) void handleArtifactDownload(failed);
                }}
                data-testid="report-artifact-retry-download"
              >
                Retry download
              </Button>
            </div>
          </Card>
        ) : null}

        {pinBody}
      </div>
    );
  }

  return (
    <div className="report-container p-base">
      <div className="report-header">
        <div className="report-title-area">
          <h3>Final Investigation Report</h3>
          {renderStatusBadge(readState, report?.status)}
        </div>
        <div className="report-actions">
          <Button
            variant="secondary"
            size="md"
            icon={<FileJson size={16} />}
            disabled={!report?.manifestPath || downloading !== null}
            loading={downloading === 'manifest'}
            onClick={() => {
              void handleDownload('manifest');
            }}
            data-testid="report-download-manifest"
          >
            Raw JSON
          </Button>
          <Button
            variant="primary"
            size="md"
            icon={<Download size={16} />}
            disabled={!report?.markdownPath || downloading !== null}
            loading={downloading === 'markdown'}
            onClick={() => {
              void handleDownload('markdown');
            }}
            data-testid="report-download-markdown"
          >
            Download Markdown
          </Button>
        </div>
      </div>

      <p className="report-subtitle">
        The report currently stored for this case. Opening this view and retrying performs reads
        only; nothing is regenerated.
      </p>

      {downloadFailure && (
        <Card
          variant="bordered"
          padding="md"
          className="report-download-error"
          data-testid="report-download-error"
          data-report-state="download-error"
          role="alert"
        >
          <div className="report-download-error__header">
            <Badge variant="danger">
              <FileWarning size={12} aria-hidden="true" /> Download error
            </Badge>
          </div>
          <p className="report-download-error__description">
            {downloadFailure.kind === 'markdown'
              ? 'The Markdown report file could not be downloaded.'
              : 'The manifest file could not be downloaded.'}{' '}
            The stored report itself was not changed.
          </p>
          <p className="report-download-error__detail">{downloadFailure.message}</p>
          <div className="report-state__actions">
            <Button
              variant="secondary"
              size="sm"
              loading={downloading === downloadFailure.kind}
              onClick={() => {
                void handleDownload(downloadFailure.kind);
              }}
              data-testid="report-retry-download"
            >
              Retry download
            </Button>
          </div>
        </Card>
      )}

      {body}

      {caseId ? (
        <section
          className="report-pin-picker"
          aria-labelledby="report-run-pin-heading"
          data-testid="report-pin-picker"
        >
          <h4 id="report-run-pin-heading" className="report-pin-picker__title">
            Frozen reports by recorded run
          </h4>
          <p className="report-pin-picker__note">
            The current report above stays the default for this view. Each link opens one recorded
            run's frozen report instead; opening a pin performs reads only and never regenerates a
            report.
          </p>
          {groupedRunsError ? (
            <div className="report-pin-picker__state" role="alert">
              <span>Recorded runs could not be read for this case.</span>
              <Button
                variant="secondary"
                size="sm"
                onClick={retryRead}
                data-testid="report-runs-retry-read"
              >
                Retry read
              </Button>
            </div>
          ) : (groupedRuns?.items ?? []).length === 0 ? (
            <p className="report-pin-picker__state" data-testid="report-pin-empty">
              No recorded investigation run is available to pin for this case.
            </p>
          ) : (
            <ul className="report-pin-picker__list">
              {(groupedRuns?.items ?? []).map((run) => (
                <li
                  key={run.id}
                  className="report-pin-picker__run"
                  data-testid="report-pin-run"
                  data-id-kind="grouped-run"
                >
                  <span className="report-pin-picker__sequence">Grouped run #{run.sequence}</span>
                  <code className="report-pin-picker__id" title={run.id}>
                    {shortRunId(run.id)}
                  </code>
                  <span className="report-pin-picker__status">{runStatusLabel(run.status)}</span>
                  <Link
                    className="report-pin-picker__link"
                    to={buildReportUrl(caseId, { runId: run.id })}
                    data-testid={`report-pin-link-${run.id}`}
                  >
                    View frozen report
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {groupedRuns && groupedRuns.total > (groupedRuns.items ?? []).length ? (
            <p className="report-pin-picker__state">
              Showing {groupedRuns.items.length} of {groupedRuns.total} recorded runs.
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
};

export default ReportTab;
