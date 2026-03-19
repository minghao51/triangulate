import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import {
  ArrowLeft,
  ArrowRight,
  Play,
  Plus,
  Trash2,
  ShieldAlert,
  Zap,
  Lock,
  CheckCircle2,
  AlertTriangle,
  Info,
} from 'lucide-react';
import { createCase } from '../services/api';
import Button from '../components/design-system/Button';
import Card from '../components/design-system/Card';
import { CardHeader, CardTitle, CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import './InvestigationComposer.css';

type Step = 'query' | 'sources' | 'parties' | 'configuration' | 'review';

interface AutomationModeOption {
  value: 'autonomous' | 'blocked' | 'safe';
  label: string;
  description: string;
  icon: React.ReactNode;
  warning?: string;
  color: string;
}

const AUTOMATION_MODES: AutomationModeOption[] = [
  {
    value: 'autonomous',
    label: 'Autonomous',
    description: 'Runs fully automated through all pipeline stages without intervention',
    icon: <Zap size={20} />,
    warning: 'Best for exploratory investigations. May generate large volumes of data.',
    color: '#00d4ff',
  },
  {
    value: 'safe',
    label: 'Safe Mode',
    description: 'Pauses at key exceptions and requires approval before continuing',
    icon: <ShieldAlert size={20} />,
    warning: 'Recommended for production use. Balances automation with oversight.',
    color: '#ffb800',
  },
  {
    value: 'blocked',
    label: 'Manual Approval',
    description: 'Requires explicit approval before each pipeline stage',
    icon: <Lock size={20} />,
    warning: 'Maximum control. Best for sensitive or high-stakes investigations.',
    color: '#ff4757',
  },
];

const QUERY_SUGGESTIONS = [
  'Origins of the 2024 tech subsidy controversy',
  'Claims about election interference in swing states',
  'Allegations of corporate espionage in AI sector',
  'Disputes over climate policy implementation',
  'Conflicting reports on international trade agreements',
];

const InvestigationComposer: React.FC = () => {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState<Step>('query');
  const [query, setQuery] = useState('');
  const [conflictDomain, setConflictDomain] = useState('');
  const [parties, setParties] = useState<string[]>(['']);
  const [manualLinks, setManualLinks] = useState<string[]>(['']);
  const [automationMode, setAutomationMode] = useState<'autonomous' | 'blocked' | 'safe'>('safe');
  const [maxArticles, setMaxArticles] = useState(50);
  const [relevanceThreshold, setRelevanceThreshold] = useState(0.3);
  const [error, setError] = useState<string | null>(null);

  const createCaseMutation = useMutation({
    mutationFn: createCase,
    onSuccess: (data) => {
      navigate(`/cases/${data.id}`);
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const steps: { id: Step; label: string; number: number }[] = [
    { id: 'query', label: 'Query', number: 1 },
    { id: 'sources', label: 'Sources', number: 2 },
    { id: 'parties', label: 'Parties', number: 3 },
    { id: 'configuration', label: 'Configuration', number: 4 },
    { id: 'review', label: 'Review', number: 5 },
  ];

  const currentStepIndex = steps.findIndex((s) => s.id === currentStep);

  const canProceed = () => {
    switch (currentStep) {
      case 'query':
        return query.trim().length > 0;
      case 'sources':
      case 'parties':
        return true;
      case 'configuration':
        return true;
      case 'review':
        return query.trim().length > 0;
      default:
        return false;
    }
  };

  const handleNext = () => {
    if (canProceed() && currentStepIndex < steps.length - 1) {
      setCurrentStep(steps[currentStepIndex + 1].id);
      setError(null);
    }
  };

  const handleBack = () => {
    if (currentStepIndex > 0) {
      setCurrentStep(steps[currentStepIndex - 1].id);
      setError(null);
    }
  };

  const handleSubmit = () => {
    setError(null);
    createCaseMutation.mutate({
      query,
      conflictDomain: conflictDomain || undefined,
      confirmedParties: parties.map((party) => party.trim()).filter(Boolean),
      manualLinks: manualLinks.map((link) => link.trim()).filter(Boolean),
      automationMode,
      maxArticles,
      relevanceThreshold,
    });
  };

  const addParty = () => setParties([...parties, '']);
  const updateParty = (index: number, val: string) => {
    const newParties = [...parties];
    newParties[index] = val;
    setParties(newParties);
  };
  const removeParty = (index: number) => {
    if (parties.length > 1) {
      setParties(parties.filter((_, i) => i !== index));
    }
  };

  const addManualLink = () => setManualLinks([...manualLinks, '']);
  const updateManualLink = (index: number, val: string) => {
    const nextLinks = [...manualLinks];
    nextLinks[index] = val;
    setManualLinks(nextLinks);
  };
  const removeManualLink = (index: number) => {
    if (manualLinks.length > 1) {
      setManualLinks(manualLinks.filter((_, i) => i !== index));
    }
  };

  return (
    <div className="investigation-composer">
      {/* Header */}
      <div className="composer-header">
        <div className="composer-header-left">
          <Button
            variant="ghost"
            size="sm"
            icon={<ArrowLeft size={16} />}
            onClick={() => navigate('/cases')}
          >
            Back to Cases
          </Button>
          <div>
            <h1 className="composer-title">New Investigation</h1>
            <p className="composer-subtitle">Configure and launch a new intelligence pipeline</p>
          </div>
        </div>
      </div>

      {/* Progress Steps */}
      <div className="composer-progress">
        <div className="progress-track">
          <div
            className="progress-bar"
            style={{ width: `${((currentStepIndex + 1) / steps.length) * 100}%` }}
          />
        </div>
        <div className="progress-steps">
          {steps.map((step, index) => (
            <div
              key={step.id}
              className={`progress-step ${
                index === currentStepIndex ? 'active' : ''
              } ${index < currentStepIndex ? 'completed' : ''}`}
              onClick={() => {
                if (index <= currentStepIndex) {
                  setCurrentStep(step.id);
                }
              }}
            >
              <div className="step-number">{step.number}</div>
              <div className="step-label">{step.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="composer-error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Step Content */}
      <div className="composer-content">
        {currentStep === 'query' && (
          <Card className="composer-card">
            <CardHeader>
              <CardTitle>Investigation Query</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="query-section">
                <div className="form-group">
                  <label className="form-label">
                    What do you want to investigate?
                    <span className="required">*</span>
                  </label>
                  <textarea
                    className="form-textarea"
                    rows={5}
                    placeholder="Describe the topic, event, or claim you want to investigate in detail..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                  <div className="form-hint">
                    Be specific and include relevant context, dates, or entities for better results
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Conflict Domain (Optional)</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g., Global Trade, Climate Policy, Geopolitics"
                    value={conflictDomain}
                    onChange={(e) => setConflictDomain(e.target.value)}
                  />
                  <div className="form-hint">
                    Helps categorize and route the investigation
                  </div>
                </div>

                <div className="suggestions-section">
                  <div className="suggestions-header">
                    <Info size={16} />
                    <span>Suggested investigations</span>
                  </div>
                  <div className="suggestions-list">
                    {QUERY_SUGGESTIONS.map((suggestion) => (
                      <button
                        key={suggestion}
                        className="suggestion-item"
                        onClick={() => setQuery(suggestion)}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>
        )}

        {currentStep === 'sources' && (
          <Card className="composer-card">
            <CardHeader>
              <CardTitle>Manual Sources</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="sources-section">
                <div className="info-banner">
                  <Info size={16} />
                  <div>
                    <strong>Optional:</strong> Provide specific URLs to seed the investigation.
                    The system will also discover additional sources automatically.
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Source URLs</label>
                  <div className="links-list">
                    {manualLinks.map((link, i) => (
                      <div key={i} className="link-row">
                        <input
                          type="url"
                          className="form-input"
                          placeholder="https://example.com/article"
                          value={link}
                          onChange={(e) => updateManualLink(i, e.target.value)}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={<Trash2 size={14} />}
                          onClick={() => removeManualLink(i)}
                          disabled={manualLinks.length === 1}
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Plus size={14} />}
                    onClick={addManualLink}
                  >
                    Add Another Source
                  </Button>
                </div>
              </div>
            </CardBody>
          </Card>
        )}

        {currentStep === 'parties' && (
          <Card className="composer-card">
            <CardHeader>
              <CardTitle>Known Parties</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="parties-section">
                <div className="info-banner">
                  <Info size={16} />
                  <div>
                    <strong>Optional:</strong> Pre-define known entities, organizations, or
                    individuals. The system will also discover parties automatically.
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Party Names</label>
                  <div className="parties-list">
                    {parties.map((party, i) => (
                      <div key={i} className="party-row">
                        <input
                          type="text"
                          className="form-input"
                          placeholder="Party name (e.g., United Nations, Tesla, John Doe)"
                          value={party}
                          onChange={(e) => updateParty(i, e.target.value)}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={<Trash2 size={14} />}
                          onClick={() => removeParty(i)}
                          disabled={parties.length === 1}
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Plus size={14} />}
                    onClick={addParty}
                  >
                    Add Another Party
                  </Button>
                </div>
              </div>
            </CardBody>
          </Card>
        )}

        {currentStep === 'configuration' && (
          <Card className="composer-card">
            <CardHeader>
              <CardTitle>Pipeline Configuration</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="configuration-section">
                {/* Automation Mode */}
                <div className="form-group">
                  <label className="form-label">Automation Mode</label>
                  <div className="automation-modes">
                    {AUTOMATION_MODES.map((mode) => (
                      <div
                        key={mode.value}
                        className={`mode-card ${
                          automationMode === mode.value ? 'mode-card-selected' : ''
                        }`}
                        style={{
                          borderColor:
                            automationMode === mode.value ? mode.color : undefined,
                        }}
                        onClick={() => setAutomationMode(mode.value)}
                      >
                        <div className="mode-icon" style={{ color: mode.color }}>
                          {mode.icon}
                        </div>
                        <div className="mode-content">
                          <div className="mode-label">{mode.label}</div>
                          <div className="mode-description">{mode.description}</div>
                        </div>
                        {automationMode === mode.value && (
                          <CheckCircle2 size={20} style={{ color: mode.color }} />
                        )}
                      </div>
                    ))}
                  </div>
                  {automationMode && (
                    <div className="mode-warning">
                      <AlertTriangle size={14} />
                      <span>
                        {
                          AUTOMATION_MODES.find((m) => m.value === automationMode)?.warning
                        }
                      </span>
                    </div>
                  )}
                </div>

                {/* Advanced Settings */}
                <div className="advanced-settings">
                  <h4 className="settings-title">Advanced Settings</h4>

                  <div className="form-group">
                    <label className="form-label">Max Articles to Retrieve</label>
                    <input
                      type="number"
                      min={1}
                      max={200}
                      className="form-input"
                      value={maxArticles}
                      onChange={(e) => setMaxArticles(Number(e.target.value) || 1)}
                    />
                    <div className="form-hint">
                      Higher values provide more comprehensive results but take longer
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Relevance Threshold</label>
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      className="form-input"
                      value={relevanceThreshold}
                      onChange={(e) =>
                        setRelevanceThreshold(Math.min(1, Math.max(0, Number(e.target.value))))
                      }
                    />
                    <div className="form-hint">
                      Filters out less relevant sources (0.0 = all, 1.0 = only exact matches)
                    </div>
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>
        )}

        {currentStep === 'review' && (
          <Card className="composer-card">
            <CardHeader>
              <CardTitle>Review & Launch</CardTitle>
            </CardHeader>
            <CardBody>
              <div className="review-section">
                <div className="review-summary">
                  <h3 className="review-title">Investigation Summary</h3>

                  <div className="review-item">
                    <span className="review-label">Query</span>
                    <span className="review-value">{query}</span>
                  </div>

                  {conflictDomain && (
                    <div className="review-item">
                      <span className="review-label">Domain</span>
                      <span className="review-value">{conflictDomain}</span>
                    </div>
                  )}

                  {parties.filter(Boolean).length > 0 && (
                    <div className="review-item">
                      <span className="review-label">Parties</span>
                      <span className="review-value">
                        {parties.filter(Boolean).join(', ')}
                      </span>
                    </div>
                  )}

                  {manualLinks.filter(Boolean).length > 0 && (
                    <div className="review-item">
                      <span className="review-label">Manual Sources</span>
                      <span className="review-value">
                        {manualLinks.filter(Boolean).length} URL
                        {manualLinks.filter(Boolean).length > 1 ? 's' : ''}
                      </span>
                    </div>
                  )}

                  <div className="review-item">
                    <span className="review-label">Automation Mode</span>
                    <Badge variant="info" size="sm">
                      {AUTOMATION_MODES.find((m) => m.value === automationMode)?.label}
                    </Badge>
                  </div>

                  <div className="review-item">
                    <span className="review-label">Max Articles</span>
                    <span className="review-value">{maxArticles}</span>
                  </div>

                  <div className="review-item">
                    <span className="review-label">Relevance Threshold</span>
                    <span className="review-value">{relevanceThreshold}</span>
                  </div>
                </div>

                <div className="review-warning">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>Before launching:</strong> This investigation will retrieve up to{' '}
                    {maxArticles} articles and run through multiple AI pipeline stages.{' '}
                    {automationMode === 'autonomous'
                      ? 'It will run completely autonomously.'
                      : automationMode === 'safe'
                      ? 'It will pause when exceptions occur.'
                      : 'It will require approval at each stage.'}
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>
        )}
      </div>

      {/* Navigation */}
      <div className="composer-navigation">
        <div className="nav-left">
          <Button
            variant="secondary"
            onClick={handleBack}
            disabled={currentStepIndex === 0 || createCaseMutation.isPending}
          >
            <ArrowLeft size={16} />
            Back
          </Button>
        </div>

        <div className="nav-right">
          {currentStep === 'review' ? (
            <Button
              variant="primary"
              icon={<Play size={16} />}
              onClick={handleSubmit}
              disabled={!canProceed() || createCaseMutation.isPending}
              loading={createCaseMutation.isPending}
            >
              {createCaseMutation.isPending ? 'Launching...' : 'Launch Investigation'}
            </Button>
          ) : (
            <Button
              variant="primary"
              icon={<ArrowRight size={16} />}
              onClick={handleNext}
              disabled={!canProceed() || createCaseMutation.isPending}
            >
              Continue
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default InvestigationComposer;
