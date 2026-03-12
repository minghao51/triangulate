import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import type { Exception } from '../../types/backend-models';
import { getExceptionsForCase, updateCaseException } from '../../services/api';
import { AlertOctagon, AlertTriangle, Info, CheckCircle2, MoreHorizontal } from 'lucide-react';
import './ExceptionsTab.css';

const ExceptionsTab: React.FC<{ onCaseMutated?: () => void; refreshToken?: number }> = ({ onCaseMutated, refreshToken = 0 }) => {
    const { id } = useParams();
    const [exceptions, setExceptions] = useState<Exception[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [pendingId, setPendingId] = useState<string | null>(null);

    const loadExceptions = async () => {
        if (!id) {
            return;
        }
        const next = await getExceptionsForCase(id);
        setExceptions(next);
    };

    useEffect(() => {
        if (id) {
            getExceptionsForCase(id).then(setExceptions).catch((err: Error) => setError(err.message));
        }
    }, [id, refreshToken]);

    const getSeverityIcon = (severity: Exception['severity']) => {
        switch (severity) {
            case 'high': return <AlertOctagon size={18} className="text-danger" />;
            case 'medium': return <AlertTriangle size={18} className="text-warning" />;
            case 'low': return <Info size={18} className="text-info" />;
        }
    };

    const handleExceptionAction = async (exceptionId: string, action: 'resolve' | 'defer' | 'reopen') => {
        if (!id) {
            return;
        }
        setPendingId(exceptionId);
        setError(null);
        try {
            await updateCaseException(id, exceptionId, action);
            await loadExceptions();
            onCaseMutated?.();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to update exception');
        } finally {
            setPendingId(null);
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
                    <div key={exc.id} className={`exception-card severity-${exc.severity}`}>
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
                            {exc.isOpen ? (
                                <>
                                    <button className="btn btn-primary" disabled={pendingId === exc.id} onClick={() => handleExceptionAction(exc.id, 'resolve')}>
                                        <CheckCircle2 size={16} /> Resolve
                                    </button>
                                    <button className="btn btn-secondary" disabled={pendingId === exc.id} onClick={() => handleExceptionAction(exc.id, 'defer')}>
                                        <MoreHorizontal size={16} /> Defer
                                    </button>
                                </>
                            ) : (
                                <button className="btn btn-secondary" disabled={pendingId === exc.id} onClick={() => handleExceptionAction(exc.id, 'reopen')}>
                                    <MoreHorizontal size={16} /> Reopen
                                </button>
                            )}
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
