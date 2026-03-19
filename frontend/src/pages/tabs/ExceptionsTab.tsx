import React, { useEffect, useState } from 'react';
import type { Exception } from '../../types/backend-models';
import { getExceptionsForCase } from '../../services/api';
import { AlertOctagon, AlertTriangle, Info, CheckCircle2, TerminalSquare } from 'lucide-react';
import './ExceptionsTab.css';

interface ExceptionsTabProps {
  caseId: string;
  refreshToken?: number;
}

const ExceptionsTab: React.FC<ExceptionsTabProps> = ({ caseId, refreshToken = 0 }) => {
    const [exceptions, setExceptions] = useState<Exception[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (caseId) {
            getExceptionsForCase(caseId).then(setExceptions).catch((err: Error) => setError(err.message));
        }
    }, [caseId, refreshToken]);

    const getSeverityIcon = (severity: Exception['severity']) => {
        switch (severity) {
            case 'high': return <AlertOctagon size={18} className="text-danger" />;
            case 'medium': return <AlertTriangle size={18} className="text-warning" />;
            case 'low': return <Info size={18} className="text-info" />;
        }
    };

    return (
        <div className="exceptions-container p-base">
            <div className="exceptions-header">
                <h3>Exception Queue</h3>
                <p className="subtitle">Human interventions blocking the automated pipeline.</p>
            </div>

            <div className="exceptions-list">
                {error && <div>Failed to load exceptions: {error}</div>}
                {exceptions.map(exc => (
                    <div key={exc.id} className={`exception-card glass-panel severity-${exc.severity}`}>
                        <div className="exc-main">
                            <div className="exc-icon">{getSeverityIcon(exc.severity)}</div>
                            <div className="exc-content">
                                <div className="exc-type">{exc.type.replace(/_/g, ' ')}</div>
                                <div className="exc-message">{exc.message}</div>
                                <div className="exc-recommendation">Status: {exc.status}</div>
                                <div className="exc-recommendation">Action: {exc.recommendedAction}</div>
                            </div>
                        </div>
                        <div className="exc-actions">
                            <div className="exc-recommendation">
                                <TerminalSquare size={14} /> CLI Only
                            </div>
                            <code className="exc-recommendation">
                                {`uv run triangulate case exception ${caseId} ${exc.id} --action ${exc.isOpen ? 'resolve' : 'reopen'}`}
                            </code>
                        </div>
                    </div>
                ))}
                {exceptions.length === 0 && (
                    <div className="empty-state">
                        <CheckCircle2 size={32} className="text-success" />
                        <p>No open exceptions blocking the pipeline.</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default ExceptionsTab;
