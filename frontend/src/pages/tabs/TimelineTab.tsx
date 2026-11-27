import React, { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { VerificationStatus } from '../../types/backend-models';
import { getTimelineForCase } from '../../services/api';
import { isNotFound } from '../../services/api-error';
import ReaderState from '../../components/design-system/ReaderState';
import { ShieldCheck, ShieldAlert, ShieldX, ShieldQuestionMark, FileText } from 'lucide-react';
import { format, isValid, parseISO } from 'date-fns';
import './TimelineTab.css';

interface StatusDisplay {
    label: string;
    badgeClass: string;
    dotClass: string;
    Icon: React.ComponentType<{ size?: number }>;
}

// One row per status the read model can record. The label, badge and dot always
// describe the same recorded status; nothing is promoted to "Confirmed".
const STATUS_DISPLAY: Record<VerificationStatus, StatusDisplay> = {
    confirmed: { label: 'Confirmed', badgeClass: 'badge-success', dotClass: 'dot-success', Icon: ShieldCheck },
    probable: { label: 'Probable', badgeClass: 'badge-info', dotClass: 'dot-info', Icon: ShieldCheck },
    alleged: { label: 'Alleged', badgeClass: 'badge-warning', dotClass: 'dot-warning', Icon: ShieldAlert },
    contested: { label: 'Contested', badgeClass: 'badge-warning', dotClass: 'dot-warning', Icon: ShieldAlert },
    debunked: { label: 'Debunked', badgeClass: 'badge-danger', dotClass: 'dot-danger', Icon: ShieldX },
    unknown: { label: 'Unknown', badgeClass: 'badge-neutral', dotClass: 'dot-neutral', Icon: ShieldQuestionMark },
};

const UNRECOGNIZED_STATUS: StatusDisplay = {
    label: 'Unrecognized status',
    badgeClass: 'badge-neutral',
    dotClass: 'dot-neutral',
    Icon: ShieldQuestionMark,
};

/**
 * Exactly the six statuses the read model can record. Anything else — including
 * an unexpected stored string — renders as "Unrecognized status" with the raw
 * value kept beside it; it is never coerced to `unknown` and never promoted.
 */
const RECOGNIZED_STATUSES = [
    'confirmed',
    'probable',
    'alleged',
    'contested',
    'debunked',
    'unknown',
] as const;

const isRecognizedStatus = (status: string): status is VerificationStatus =>
    (RECOGNIZED_STATUSES as readonly string[]).includes(status);

const getStatusDisplay = (status: string | null | undefined): StatusDisplay =>
    typeof status === 'string' && isRecognizedStatus(status)
        ? STATUS_DISPLAY[status]
        : UNRECOGNIZED_STATUS;

/**
 * Format a stored timestamp, or report that none is recorded.
 *
 * A missing/unparseable timestamp is *not* a status and is never replaced by a
 * synthetic date (no 1970 epoch, no "now", no inferred ordering) — the reader
 * simply states that the date is not recorded.
 */
const formatRecordedDate = (timestamp: string | null | undefined): string | null => {
    if (typeof timestamp !== 'string' || timestamp.trim() === '') return null;
    const parsed = parseISO(timestamp);
    return isValid(parsed) ? format(parsed, 'yyyy-MM-dd HH:mm') : null;
};

interface TimelineTabProps {
  caseId: string;
  refreshToken?: number;
}

/**
 * Timeline reader.
 *
 * Query key is `['timeline', caseId]` — the shape the other timeline readers
 * already use — so one case has exactly one timeline cache entry and a late
 * response for a previous case cannot render under the current one.
 */
const TimelineTab: React.FC<TimelineTabProps> = ({ caseId, refreshToken = 0 }) => {
    const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
        queryKey: ['timeline', caseId],
        queryFn: () => getTimelineForCase(caseId),
        enabled: Boolean(caseId),
    });

    // Parent-driven refresh signal: not part of the key, just a refetch request.
    const lastRefreshToken = useRef(refreshToken);
    useEffect(() => {
        if (lastRefreshToken.current === refreshToken) return;
        lastRefreshToken.current = refreshToken;
        void refetch();
    }, [refreshToken, refetch]);

    const events = data ?? [];
    const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

    let stateBody: React.ReactNode;
    if (!caseId) {
        stateBody = (
            <ReaderState
                state="not-found"
                title="No case selected"
                description="Choose a case to view its investigation timeline."
            />
        );
    } else if (isLoading) {
        stateBody = <ReaderState state="loading" description="Fetching the timeline for this case." />;
    } else if (error) {
        stateBody = isNotFound(error) ? (
            <ReaderState state="not-found" description="This case has no timeline recorded." />
        ) : (
            <ReaderState
                state="network-error"
                description="The timeline could not be loaded."
                detail={error instanceof Error ? error.message : null}
                onRetry={() => {
                    void refetch();
                }}
                lastFetched={lastFetched}
            />
        );
    } else if (events.length === 0) {
        stateBody = (
            <ReaderState
                state="empty"
                description="No timeline events have been recorded for this case yet."
                lastFetched={lastFetched}
            />
        );
    } else {
        stateBody = events.map((evt, index) => {
            const rawStatus = typeof evt.verificationStatus === 'string' ? evt.verificationStatus : null;
            // A value outside the recorded set is not coerced to `unknown`: the
            // DTO keeps the fallback status and carries the stored text beside
            // it, so the reader sees "Unrecognized status" plus the raw value.
            const storedStatus =
                rawStatus === 'unknown' &&
                typeof evt.rawVerificationStatus === 'string' &&
                evt.rawVerificationStatus !== ''
                    ? evt.rawVerificationStatus
                    : rawStatus;
            const status = getStatusDisplay(storedStatus);
            const StatusIcon = status.Icon;
            const recognized = storedStatus !== null && isRecognizedStatus(storedStatus);
            const recordedDate = formatRecordedDate(evt.timestamp);
            return (
                <div key={evt.id} className="timeline-item">
                    <div className="timeline-marker">
                        <div className={`timeline-dot ${status.dotClass}`}></div>
                        {index < events.length - 1 && <div className="timeline-line"></div>}
                    </div>

                    <div className="timeline-content glass-panel">
                        <div
                            className={`timeline-date${recordedDate === null ? ' timeline-date--unknown' : ''}`}
                            data-date-state={recordedDate === null ? 'unknown' : 'recorded'}
                        >
                            {recordedDate ?? 'Date not recorded'}
                        </div>
                        <h4 className="timeline-title">{evt.title}</h4>
                        <p className="timeline-summary">{evt.summary}</p>

                        <div className="timeline-footer">
                            <div className="timeline-status">
                                <span className={`badge ${status.badgeClass}`}><StatusIcon size={12} /> {status.label}</span>
                                {!recognized && storedStatus !== null && (
                                    <span className="timeline-status-raw" title="Stored status value">
                                        Stored value: <code>{storedStatus}</code>
                                    </span>
                                )}
                            </div>
                            <div className="timeline-evidence">
                                <FileText size={14} className="text-secondary" />
                                <span>{evt.linkedEvidenceCount} Linked Sources</span>
                            </div>
                        </div>
                    </div>
                </div>
            );
        });
    }

    return (
        <div className="timeline-container p-base">
            <div className="timeline-header">
                <h3>Investigation Timeline</h3>
                <p className="subtitle">Events in recorded order. Dates and statuses are shown as stored.</p>
            </div>

            <div className="timeline-track">
                {stateBody}
            </div>
        </div>
    );
};

export default TimelineTab;
