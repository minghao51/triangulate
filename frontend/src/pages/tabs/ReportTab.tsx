import React, { useEffect, useState } from 'react';
import type { ReportData } from '../../types/backend-models';
import { downloadManifestReport, downloadMarkdownReport, getReportForCase } from '../../services/api';
import { Download, FileJson, CheckCircle2 } from 'lucide-react';
import './ReportTab.css';

interface ReportTabProps {
  caseId: string;
  refreshToken?: number;
}

const ReportTab: React.FC<ReportTabProps> = ({ caseId, refreshToken = 0 }) => {
    const [report, setReport] = useState<ReportData | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [downloading, setDownloading] = useState<'markdown' | 'manifest' | null>(null);

    useEffect(() => {
        if (caseId) {
            getReportForCase(caseId).then(setReport).catch((err: Error) => setError(err.message));
        }
    }, [caseId, refreshToken]);

    const handleDownload = async (kind: 'markdown' | 'manifest') => {
        if (!caseId) {
            return;
        }
        setDownloading(kind);
        setError(null);
        try {
            if (kind === 'markdown') {
                await downloadMarkdownReport(caseId);
            } else {
                await downloadManifestReport(caseId);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to download report');
        } finally {
            setDownloading(null);
        }
    };

    return (
        <div className="report-container p-base">
            <div className="report-header">
                <div className="report-title-area">
                    <h3>Final Investigation Report</h3>
                    <span className="badge badge-success"><CheckCircle2 size={12} /> {report?.status === 'generated' ? 'Generated' : 'Pending'}</span>
                </div>
                <div className="report-actions">
                    <button className="btn btn-secondary" disabled={!report?.manifestPath || downloading !== null} onClick={() => handleDownload('manifest')}>
                        <FileJson size={16} /> Raw JSON
                    </button>
                    <button className="btn btn-primary" disabled={!report?.markdownPath || downloading !== null} onClick={() => handleDownload('markdown')}>
                        <Download size={16} /> {downloading === 'markdown' ? 'Downloading...' : 'Download Markdown'}
                    </button>
                </div>
            </div>

            <div className="report-canvas glass-panel">
                <div className="markdown-body">
                    {error && <p>Failed to load report: {error}</p>}
                    {!error && !report?.markdownContent && <p>No report has been generated yet.</p>}
                    {report?.markdownContent && (
                        <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{report.markdownContent}</pre>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ReportTab;
