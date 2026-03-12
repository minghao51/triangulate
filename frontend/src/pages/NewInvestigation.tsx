import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createCase } from '../services/api';
import { ShieldAlert, PlayCircle, Plus, Trash2 } from 'lucide-react';
import './NewInvestigation.css';

const NewInvestigation: React.FC = () => {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const [conflictDomain, setConflictDomain] = useState('');
    const [parties, setParties] = useState<string[]>(['']);
    const [manualLinks, setManualLinks] = useState<string[]>(['']);
    const [automationMode, setAutomationMode] = useState<'autonomous' | 'blocked' | 'safe'>('safe');
    const [maxArticles, setMaxArticles] = useState(50);
    const [relevanceThreshold, setRelevanceThreshold] = useState(0.3);
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const addParty = () => setParties([...parties, '']);
    const updateParty = (index: number, val: string) => {
        const newParties = [...parties];
        newParties[index] = val;
        setParties(newParties);
    };
    const removeParty = (index: number) => {
        setParties(parties.filter((_, i) => i !== index));
    };
    const addManualLink = () => setManualLinks([...manualLinks, '']);
    const updateManualLink = (index: number, val: string) => {
        const nextLinks = [...manualLinks];
        nextLinks[index] = val;
        setManualLinks(nextLinks);
    };
    const removeManualLink = (index: number) => {
        setManualLinks(manualLinks.filter((_, i) => i !== index));
    };

    const handleRun = async () => {
        setSubmitting(true);
        setError(null);
        try {
            const created = await createCase({
                query,
                conflictDomain: conflictDomain || undefined,
                confirmedParties: parties.map((party) => party.trim()).filter(Boolean),
                manualLinks: manualLinks.map((link) => link.trim()).filter(Boolean),
                automationMode,
                maxArticles,
                relevanceThreshold,
            });
            navigate(`/cases/${created.id}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create case');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="new-case-container p-base">
            <div className="case-header">
                <h1>Bootstrap Investigation</h1>
                <p className="subtitle">Initialize a new case pipeline. The system will retrieve sources and bootstrap parties based on your seed query.</p>
            </div>

            <div className="form-grid">
                <div className="form-section card">
                    <div className="card-header">Core Parameters</div>
                    <div className="card-body form-body">
                        <div className="form-group">
                            <label>Investigation Query *</label>
                            <textarea
                                className="input-field"
                                rows={3}
                                placeholder="e.g. Origins of the 2024 tech subsidy crisis..."
                                value={query}
                                onChange={e => setQuery(e.target.value)}
                            />
                        </div>

                        <div className="form-group">
                            <label>Conflict / Domain (Optional Override)</label>
                            <input
                                type="text"
                                className="input-field"
                                placeholder="e.g. Global Trade"
                                value={conflictDomain}
                                onChange={e => setConflictDomain(e.target.value)}
                            />
                        </div>

                        <div className="form-group">
                            <label>Automation Mode</label>
                            <select
                                className="input-field"
                                value={automationMode}
                                onChange={e => setAutomationMode(e.target.value as 'autonomous' | 'blocked' | 'safe')}
                            >
                                <option value="autonomous">Autonomous (Fully runs to Report)</option>
                                <option value="safe">Safe (Pauses at key exceptions)</option>
                                <option value="blocked">Blocked (Requires explicit approval per stage)</option>
                            </select>
                        </div>

                        <div className="form-group">
                            <label>Max Articles</label>
                            <input
                                type="number"
                                min={1}
                                max={200}
                                className="input-field"
                                value={maxArticles}
                                onChange={e => setMaxArticles(Number(e.target.value) || 1)}
                            />
                        </div>

                        <div className="form-group">
                            <label>Relevance Threshold</label>
                            <input
                                type="number"
                                min={0}
                                max={1}
                                step={0.05}
                                className="input-field"
                                value={relevanceThreshold}
                                onChange={e => setRelevanceThreshold(Number(e.target.value))}
                            />
                        </div>
                    </div>
                </div>

                <div className="form-section card">
                    <div className="card-header">Confirmed Parties / Nationalities</div>
                    <div className="card-body form-body">
                        <p className="help-text">Seed the investigation with known entities to guide the claims engine.</p>
                        {parties.map((p, i) => (
                            <div key={i} className="party-row">
                                <input
                                    type="text"
                                    className="input-field"
                                    placeholder="Party Name"
                                    value={p}
                                    onChange={e => updateParty(i, e.target.value)}
                                />
                                <button className="btn btn-secondary btn-icon" onClick={() => removeParty(i)}>
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        ))}
                        <button className="btn btn-secondary mt-2" onClick={addParty}>
                            <Plus size={16} /> Add Party
                        </button>
                    </div>
                </div>

                <div className="form-section card">
                    <div className="card-header">Manual Source Links</div>
                    <div className="card-body form-body">
                        <p className="help-text">Seed the case with URLs that should be treated as evidence inputs.</p>
                        {manualLinks.map((link, i) => (
                            <div key={i} className="party-row">
                                <input
                                    type="url"
                                    className="input-field"
                                    placeholder="https://example.com/source"
                                    value={link}
                                    onChange={e => updateManualLink(i, e.target.value)}
                                />
                                <button className="btn btn-secondary btn-icon" onClick={() => removeManualLink(i)}>
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        ))}
                        <button className="btn btn-secondary mt-2" onClick={addManualLink}>
                            <Plus size={16} /> Add Link
                        </button>
                    </div>
                </div>
            </div>

            <div className="action-bar card">
                <div className="preview-info">
                    <ShieldAlert size={18} className="text-warning" />
                    <span>
                        This run will fetch up to {maxArticles} articles and stop {automationMode === 'blocked' ? 'after each stage' : automationMode === 'safe' ? 'when unresolved exceptions appear' : 'only on hard failures'}.
                    </span>
                </div>
                {error && <div style={{ color: 'var(--danger, #b42318)' }}>{error}</div>}
                <div className="actions">
                    <button className="btn btn-secondary" onClick={() => navigate('/')}>Cancel</button>
                    <button className="btn btn-primary" onClick={handleRun} disabled={!query || submitting}>
                        <PlayCircle size={18} /> {submitting ? 'Running...' : 'Run Pipeline'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default NewInvestigation;
