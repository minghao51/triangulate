import React, { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { Exception } from '../../types/backend-models';
import { getExceptionsForCase, submitExceptionAction } from '../../services/api';
import Button from '../../components/design-system/Button';
import { AlertOctagon, AlertTriangle, Info, CheckCircle2, TerminalSquare } from 'lucide-react';
import './ExceptionsTab.css';

interface ExceptionsTabProps {
  caseId: string;
  refreshToken?: number;
}

const ExceptionsTab: React.FC<ExceptionsTabProps> = ({ caseId, refreshToken = 0 }) => {
    const queryClient = useQueryClient();
    const [exceptions, setExceptions] = useState<Exception[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [activeExceptionId, setActiveExceptionId] = useState<string | null>(null);

    useEffect(() => {
        if (caseId) {
            getExceptionsForCase(caseId).then(setExceptions).catch((err: Error) => setError(err.message));
        }
    }, [caseId, refreshToken]);

    const actionMutation = useMutation({
        mutationFn: ({ exceptionId, action }: { exceptionId: string; action: string }) =>
            submitExceptionAction(caseId, exceptionId, action),
        onMutate: ({ exceptionId }) => {
            setActiveExceptionId(exceptionId);
            setError(null);
        },
        onSuccess: async () => {
            const refreshed = await getExceptionsForCase(caseId);
            setExceptions(refreshed);
            await Promise.all([
                queryClient.invalidateQueries({ queryKey: ['caseDetail', caseId] }),
                queryClient.invalidateQueries({ queryKey: ['cases'] }),
                queryClient.invalidateQueries({ queryKey: ['reviewActivity', caseId] }),
                queryClient.invalidateQueries({ queryKey: ['evaluationSummary', caseId] }),
                queryClient.invalidateQueries({ queryKey: ['monitoringSummary'] }),
            ]);
            setActiveExceptionId(null);
        },
        onError: (err: Error) => {
            setError(err.message);
            setActiveExceptionId(null);
        },
    });

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
                            <div className="action-buttons">
                                {exc.isOpen ? (
                                    <>
                                        <Button
                                            variant="primary"
                                            size="sm"
                                            onClick={() => actionMutation.mutate({ exceptionId: exc.id, action: 'resolve' })}
                                            disabled={actionMutation.isPending && activeExceptionId === exc.id}
                                        >
                                            Resolve
                                        </Button>
                                        <Button
                                            variant="secondary"
                                            size="sm"
                                            onClick={() => actionMutation.mutate({ exceptionId: exc.id, action: 'defer' })}
                                            disabled={actionMutation.isPending && activeExceptionId === exc.id}
                                        >
                                            Defer
                                        </Button>
                                    </>
                                ) : (
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        onClick={() => actionMutation.mutate({ exceptionId: exc.id, action: 'reopen' })}
                                        disabled={actionMutation.isPending && activeExceptionId === exc.id}
                                    >
                                        Reopen
                                    </Button>
                                )}
                            </div>
                            <div className="exc-recommendation">
                                <TerminalSquare size={14} /> CLI fallback
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
