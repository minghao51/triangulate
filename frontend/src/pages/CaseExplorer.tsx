import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Search,
  Filter,
  Plus,
  FileSearch,
  Activity,
  AlertCircle,
  ShieldCheck,
  ChevronDown,
  Download,
  RefreshCw,
} from 'lucide-react';
import type { TopicCase } from '../types/backend-models';
import { getCases } from '../services/api';
import Button from '../components/design-system/Button';
import Card from '../components/design-system/Card';
import { CardBody } from '../components/design-system/Card';
import Badge from '../components/design-system/Badge';
import { formatDistanceToNow, parseISO } from 'date-fns';
import './CaseExplorer.css';

const CaseExplorer: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [stageFilter, setStageFilter] = useState<string>('all');
  const [domainFilter, setDomainFilter] = useState<string>('all');
  const [showFilters, setShowFilters] = useState(false);
  const [selectedCases, setSelectedCases] = useState<Set<string>>(new Set());

  const { data: cases = [], isLoading, error, refetch } = useQuery({
    queryKey: ['cases'],
    queryFn: getCases,
    refetchInterval: 30000,
  });

  // Get unique values for filters
  const statuses = Array.from(new Set(cases.map((tc) => tc.status)));
  const stages = Array.from(new Set(cases.map((tc) => tc.stage)));
  const domains = Array.from(new Set(cases.map((tc) => tc.conflictDomain))).filter(Boolean);

  // Filter cases
  const filteredCases = cases.filter((tc) => {
    const matchesSearch =
      !search ||
      `${tc.query} ${tc.conflictDomain}`.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || tc.status === statusFilter;
    const matchesStage = stageFilter === 'all' || tc.stage === stageFilter;
    const matchesDomain = domainFilter === 'all' || tc.conflictDomain === domainFilter;
    return matchesSearch && matchesStatus && matchesStage && matchesDomain;
  });

  // Calculate statistics
  const stats = {
    total: filteredCases.length,
    active: filteredCases.filter((c) => c.status !== 'approved' && c.status !== 'rejected').length,
    reviewReady: filteredCases.filter((c) => c.status === 'review ready').length,
    withExceptions: filteredCases.filter((c) => c.openExceptionsCount > 0).length,
  };

  const handleSelectCase = (caseId: string) => {
    const newSelected = new Set(selectedCases);
    if (newSelected.has(caseId)) {
      newSelected.delete(caseId);
    } else {
      newSelected.add(caseId);
    }
    setSelectedCases(newSelected);
  };

  const getStatusVariant = (status: TopicCase['status']): 'success' | 'warning' | 'danger' | 'info' | 'neutral' => {
    switch (status) {
      case 'review ready': return 'success';
      case 'investigating': return 'warning';
      case 'discovering': return 'info';
      case 'processing': return 'info';
      case 'failed': return 'danger';
      case 'rejected': return 'danger';
      case 'approved': return 'success';
      case 'monitoring': return 'info';
      default: return 'neutral';
    }
  };

  return (
    <div className="case-explorer">
      {/* Header */}
      <div className="explorer-header">
        <div className="explorer-header-left">
          <h1 className="explorer-title">Case Explorer</h1>
          <p className="explorer-subtitle">Browse and manage all investigations</p>
        </div>
        <div className="explorer-header-right">
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={() => refetch()}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon={<Plus size={14} />}
            onClick={() => navigate('/cases/new')}
          >
            New Case
          </Button>
        </div>
      </div>

      {error && (
        <div className="explorer-error">
          <AlertCircle size={16} />
          <span>Failed to load cases: {(error as Error).message}</span>
        </div>
      )}

      {isLoading ? (
        <div className="explorer-loading">Loading cases...</div>
      ) : (
        <>
          {/* Stats Bar */}
          <div className="explorer-stats">
            <div className="stat-item">
              <span className="stat-value">{stats.total}</span>
              <span className="stat-label">Total</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.active}</span>
              <span className="stat-label">Active</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.reviewReady}</span>
              <span className="stat-label">Review Ready</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.withExceptions}</span>
              <span className="stat-label">Exceptions</span>
            </div>
          </div>

          {/* Filters Toolbar */}
          <Card className="explorer-toolbar">
            <CardBody className="explorer-toolbar-body">
              <div className="toolbar-search">
                <Search size={18} className="search-icon" />
                <input
                  type="text"
                  className="search-input"
                  placeholder="Search queries or domains..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>

              <div className="toolbar-actions">
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Filter size={14} />}
                  onClick={() => setShowFilters(!showFilters)}
                >
                  Filters
                  <ChevronDown
                    size={14}
                    style={{
                      transform: showFilters ? 'rotate(180deg)' : 'rotate(0)',
                      transition: 'transform 0.2s',
                    }}
                  />
                </Button>

                {selectedCases.size > 0 && (
                  <>
                    <Button variant="ghost" size="sm" icon={<RefreshCw size={14} />}>
                      Rerun ({selectedCases.size})
                    </Button>
                    <Button variant="ghost" size="sm" icon={<Download size={14} />}>
                      Export
                    </Button>
                  </>
                )}
              </div>
            </CardBody>

            {showFilters && (
              <div className="explorer-filters">
                <div className="filter-group">
                  <label className="filter-label">Status</label>
                  <select
                    className="filter-select"
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                  >
                    <option value="all">All Statuses</option>
                    {statuses.map((status) => (
                      <option key={status} value={status}>{status}</option>
                    ))}
                  </select>
                </div>

                <div className="filter-group">
                  <label className="filter-label">Stage</label>
                  <select
                    className="filter-select"
                    value={stageFilter}
                    onChange={(e) => setStageFilter(e.target.value)}
                  >
                    <option value="all">All Stages</option>
                    {stages.map((stage) => (
                      <option key={stage} value={stage}>{stage}</option>
                    ))}
                  </select>
                </div>

                <div className="filter-group">
                  <label className="filter-label">Domain</label>
                  <select
                    className="filter-select"
                    value={domainFilter}
                    onChange={(e) => setDomainFilter(e.target.value)}
                  >
                    <option value="all">All Domains</option>
                    {domains.map((domain) => (
                      <option key={domain} value={domain}>{domain}</option>
                    ))}
                  </select>
                </div>

                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setStatusFilter('all');
                    setStageFilter('all');
                    setDomainFilter('all');
                    setSearch('');
                  }}
                >
                  Clear Filters
                </Button>
              </div>
            )}
          </Card>

          {/* Cases Grid */}
          <div className="explorer-grid">
            {filteredCases.map((caseItem) => (
              <Card
                key={caseItem.id}
                className="case-card"
                hover
                onClick={() => navigate(`/cases/${caseItem.id}`)}
              >
                <CardBody className="case-card-body">
                  {/* Checkbox */}
                  <div
                    className="case-checkbox"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSelectCase(caseItem.id);
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedCases.has(caseItem.id)}
                      onChange={() => handleSelectCase(caseItem.id)}
                    />
                  </div>

                  {/* Header */}
                  <div className="case-header">
                    <h3 className="case-query">{caseItem.query}</h3>
                    <Badge variant={getStatusVariant(caseItem.status)} size="sm">
                      {caseItem.status}
                    </Badge>
                  </div>

                  {/* Domain */}
                  <div className="case-domain">{caseItem.conflictDomain}</div>

                  {/* Metrics */}
                  <div className="case-metrics">
                    <div className="case-metric" title="Articles">
                      <FileSearch size={14} />
                      <span>{caseItem.counts.articles}</span>
                    </div>
                    <div className="case-metric" title="Events">
                      <Activity size={14} />
                      <span>{caseItem.counts.events}</span>
                    </div>
                    <div className="case-metric" title="Review Items">
                      <AlertCircle size={14} />
                      <span>{caseItem.counts.reviewItems}</span>
                    </div>
                  </div>

                  {/* Footer */}
                  <div className="case-footer">
                    <div className="case-stage">
                      <Badge variant="neutral" size="sm">{caseItem.stage}</Badge>
                    </div>

                    {caseItem.openExceptionsCount > 0 ? (
                      <div className="case-exceptions">
                        <AlertCircle size={14} />
                        <span>{caseItem.openExceptionsCount} action{caseItem.openExceptionsCount > 1 ? 's' : ''} required</span>
                      </div>
                    ) : (
                      <div className="case-status-clean">
                        <ShieldCheck size={14} />
                        <span>Clear</span>
                      </div>
                    )}

                    <div className="case-time">
                      {caseItem.lastUpdated
                        ? formatDistanceToNow(parseISO(caseItem.lastUpdated), { addSuffix: true })
                        : 'Unknown'}
                    </div>
                  </div>
                </CardBody>
              </Card>
            ))}

            {filteredCases.length === 0 && (
              <div className="explorer-empty">
                <AlertCircle size={48} />
                <h3>No cases found</h3>
                <p>Try adjusting your filters or create a new investigation</p>
                <Button
                  variant="primary"
                  icon={<Plus size={16} />}
                  onClick={() => navigate('/cases/new')}
                >
                  Create New Case
                </Button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default CaseExplorer;
