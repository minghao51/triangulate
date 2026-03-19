import React, { useEffect, useState } from 'react';
import type { TimelineEvent } from '../../types/backend-models';
import { getTimelineForCase } from '../../services/api';
import { ShieldCheck, ShieldAlert, FileText } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import './TimelineTab.css';

interface TimelineTabProps {
  caseId: string;
  refreshToken?: number;
}

const TimelineTab: React.FC<TimelineTabProps> = ({ caseId, refreshToken = 0 }) => {
    const [events, setEvents] = useState<TimelineEvent[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (caseId) {
            getTimelineForCase(caseId).then(setEvents).catch((err: Error) => setError(err.message));
        }
    }, [caseId, refreshToken]);

    return (
        <div className="timeline-container p-base">
            <div className="timeline-header">
                <h3>Investigation Timeline</h3>
                <p className="subtitle">Chronological reconstruction from extracted claims.</p>
            </div>

            <div className="timeline-track">
                {error && <div>Failed to load timeline: {error}</div>}
                {events.map((evt, index) => (
                    <div key={evt.id} className="timeline-item">
                        <div className="timeline-marker">
                            <div className={`timeline-dot ${evt.verificationStatus === 'contested' ? 'dot-warning' : 'dot-success'}`}></div>
                            {index < events.length - 1 && <div className="timeline-line"></div>}
                        </div>

                        <div className="timeline-content card">
                            <div className="timeline-date">{evt.timestamp ? format(parseISO(evt.timestamp), 'yyyy-MM-dd HH:mm') : 'Unknown date'}</div>
                            <h4 className="timeline-title">{evt.title}</h4>
                            <p className="timeline-summary">{evt.summary}</p>

                            <div className="timeline-footer">
                                <div className="timeline-status">
                                    {evt.verificationStatus === 'contested' ? (
                                        <span className="badge badge-warning"><ShieldAlert size={12} /> Contested</span>
                                    ) : (
                                        <span className="badge badge-success"><ShieldCheck size={12} /> Confirmed</span>
                                    )}
                                </div>
                                <div className="timeline-evidence">
                                    <FileText size={14} className="text-secondary" />
                                    <span>{evt.linkedEvidenceCount} Linked Sources</span>
                                </div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default TimelineTab;
