import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import type { RunHistoryItem } from '../../types/backend-models';
import { getRunHistoryForCase } from '../../services/api';
import { Activity, Code2, AlertCircle, Clock } from 'lucide-react';
import { formatDistanceStrict, parseISO } from 'date-fns';
import './RunHistoryTab.css';

const RunHistoryTab: React.FC<{ refreshToken?: number }> = ({ refreshToken = 0 }) => {
    const { id } = useParams();
    const [runs, setRuns] = useState<RunHistoryItem[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (id) {
            getRunHistoryForCase(id).then(setRuns).catch((err: Error) => setError(err.message));
        }
    }, [id, refreshToken]);

    return (
        <div className="run-history-container p-base">
            <div className="history-header">
                <h3>Pipeline Execution History</h3>
                <p className="subtitle">Audit log of system actions, model interventions, and parse fallbacks.</p>
            </div>

            <div className="history-table-container card">
                {error && <div style={{ padding: '1rem' }}>Failed to load run history: {error}</div>}
                <table className="history-table">
                    <thead>
                        <tr>
                            <th>Stage</th>
                            <th>Model / Engine</th>
                            <th>Duration</th>
                            <th>Fallbacks</th>
                            <th>Status / Output</th>
                            <th>Time</th>
                        </tr>
                    </thead>
                    <tbody>
                        {runs.map(run => (
                            <tr key={run.id} className="history-row">
                                <td>
                                    <span className="badge badge-neutral">{run.stage}</span>
                                </td>
                                <td className="model-cell">
                                    <Code2 size={14} className="text-secondary" /> {run.model}
                                </td>
                                <td>{run.durationMs ? formatDistanceStrict(0, run.durationMs) : '-'}</td>
                                <td>{run.fallbackCount}</td>
                                <td>
                                    {run.status === 'success' ? (
                                        <span className="text-success" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                            <Activity size={14} /> Success
                                        </span>
                                    ) : (
                                        <span className="text-danger" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.875rem' }}>
                                            <AlertCircle size={14} /> {run.message}
                                        </span>
                                    )}
                                </td>
                                <td className="time-cell">
                                    <Clock size={12} className="text-tertiary" /> {run.timestamp ? parseISO(run.timestamp).toISOString() : '-'}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default RunHistoryTab;
