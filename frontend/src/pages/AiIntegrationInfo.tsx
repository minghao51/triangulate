import React, { useMemo } from 'react';
import ReactFlow, {
  type Node,
  type Edge,
  Controls,
  Background,
  BackgroundVariant,
  MarkerType,
  Handle,
  Position,
} from 'reactflow';
import 'reactflow/dist/style.css';
import Card, { CardBody, CardHeader, CardTitle } from '../components/design-system/Card';
import './AiIntegrationInfo.css';

const agentNodes = [
  { id: 'collector', label: 'Collector', description: 'Extracts factual claims from articles', icon: '📝', color: '#00d4ff' },
  { id: 'clusterer', label: 'Clusterer', description: 'Groups claims by narrative using TF-IDF + KMeans', icon: '🔗', color: '#a55eea' },
  { id: 'narrator', label: 'Narrator', description: 'Generates narrative summaries per cluster', icon: '📖', color: '#00ff9d' },
  { id: 'classifier', label: 'Classifier', description: 'Assigns verification status to events', icon: '✅', color: '#ffb800' },
];

const verificationStatuses = [
  { status: 'CONFIRMED', color: '#00d4ff', description: 'Multiple credible sources agree on this event.' },
  { status: 'PROBABLE', color: '#00ff9d', description: 'Most evidence supports this event.' },
  { status: 'ALLEGED', color: '#ffb800', description: 'Claims exist but verification is inconclusive.' },
  { status: 'CONTESTED', color: '#ff6b00', description: 'Sources disagree on key facts.' },
  { status: 'DEBUNKED', color: '#ff4757', description: 'Evidence contradicts this event.' },
];

const buildDagNodes = (): Node[] => {
  const positions = [
    { x: 0, y: 100 },
    { x: 250, y: 100 },
    { x: 500, y: 100 },
    { x: 750, y: 100 },
  ];

  return agentNodes.map((agent, index) => ({
    id: agent.id,
    type: 'input',
    position: positions[index],
    data: {
      label: agent.label,
      description: agent.description,
      icon: agent.icon,
    },
    style: {
      background: '#0a0a0a',
      border: `2px solid ${agent.color}`,
      borderRadius: '8px',
      padding: '16px 24px',
      minWidth: '160px',
      boxShadow: `0 0 20px ${agent.color}30`,
    },
  }));
};

const buildDagEdges = (): Edge[] => {
  const edges: Edge[] = [];
  for (let i = 0; i < agentNodes.length - 1; i++) {
    edges.push({
      id: `${agentNodes[i].id}-${agentNodes[i + 1].id}`,
      source: agentNodes[i].id,
      target: agentNodes[i + 1].id,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#6c7385', strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#6c7385' },
    });
  }
  return edges;
};

const InputNode: React.FC<{ data: { label: string; description: string; icon: string } }> = ({ data }) => (
  <div style={{ textAlign: 'center' }}>
    <Handle type="target" position={Position.Left} style={{ visibility: 'hidden' }} />
    <div style={{ fontSize: '28px', marginBottom: '8px' }}>{data.icon}</div>
    <div style={{ color: '#f0f2f5', fontSize: '14px', fontWeight: 600, marginBottom: '4px' }}>{data.label}</div>
    <div style={{ color: '#9aa1b3', fontSize: '11px', maxWidth: '140px' }}>{data.description}</div>
    <Handle type="source" position={Position.Right} style={{ visibility: 'hidden' }} />
  </div>
);

const nodeTypes = { input: InputNode };

const AiIntegrationInfo: React.FC = () => {
  const nodes = useMemo(() => buildDagNodes(), []);
  const edges = useMemo(() => buildDagEdges(), []);

  return (
    <div className="ai-info">
      <div className="ai-info-header">
        <h1>AI Integration</h1>
        <p>
          Triangulate uses a multi-agent LangGraph workflow to interpret events. The pipeline
          extracts claims, clusters them by narrative, generates summaries, and assigns
          verification statuses to determine event credibility.
        </p>
      </div>

      <div className="ai-info-grid">
        <Card className="dag-card">
          <CardHeader>
            <CardTitle>Agent Pipeline</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="dag-container">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                fitView
                attributionPosition="bottom-left"
                proOptions={{ hideAttribution: true }}
                style={{ backgroundColor: '#0a0a0a' }}
              >
                <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#2d3340" />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
            <div className="dag-legend">
              <div className="legend-item">
                <span className="legend-line animated" />
                <span>Data Flow</span>
              </div>
              <div className="legend-item">
                <span className="legend-line static" />
                <span>State Transition</span>
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="agents-card">
          <CardHeader>
            <CardTitle>Agent Details</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="agents-list">
              {agentNodes.map((agent, index) => (
                <div key={agent.id} className="agent-item">
                  <div className="agent-number" style={{ borderColor: agent.color }}>{index + 1}</div>
                  <div className="agent-content">
                    <div className="agent-header">
                      <span className="agent-icon">{agent.icon}</span>
                      <span className="agent-name" style={{ color: agent.color }}>{agent.label}</span>
                    </div>
                    <p className="agent-description">{agent.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card className="verification-card">
          <CardHeader>
            <CardTitle>Verification Status</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="verification-list">
              {verificationStatuses.map((item) => (
                <div key={item.status} className="verification-item">
                  <div className="verification-status" style={{ backgroundColor: item.color }} />
                  <div className="verification-content">
                    <span className="verification-name">{item.status}</span>
                    <p className="verification-description">{item.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card className="arbitars-card">
          <CardHeader>
            <CardTitle>Arbiters & Event Interpretation</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="arbitars-content">
              <p>
                Triangulate employs <strong>arbiters</strong> as intelligent agents that evaluate
                conflicting claims across multiple dimensions:
              </p>
              <ul>
                <li><strong>Source Credibility</strong> — Evaluates the reliability and track record of information sources</li>
                <li><strong>Temporal Consistency</strong> — Checks if claims align with known timelines</li>
                <li><strong>Cross-Source Corroboration</strong> — Measures agreement across independent sources</li>
                <li><strong>Entity Resolution</strong> — Identifies and links related parties and events</li>
                <li><strong>Narrative Coherence</strong> — Assesses whether claims fit within logical event patterns</li>
              </ul>
              <p>
                The <strong>Classifier</strong> agent uses these arbiter signals to assign
                verification statuses, enabling analysts to quickly assess event credibility
                and identify areas of contention.
              </p>
            </div>
          </CardBody>
        </Card>

        <Card className="tech-card">
          <CardHeader>
            <CardTitle>Technology Stack</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="tech-list">
              <div className="tech-item">
                <span className="tech-name">LangGraph</span>
                <span className="tech-purpose">Multi-agent workflow orchestration with state management</span>
              </div>
              <div className="tech-item">
                <span className="tech-name">LiteLLM</span>
                <span className="tech-purpose">Unified LLM API interface for agent reasoning</span>
              </div>
              <div className="tech-item">
                <span className="tech-name">TF-IDF + KMeans</span>
                <span className="tech-purpose">Semantic clustering of claims by narrative</span>
              </div>
              <div className="tech-item">
                <span className="tech-name">ReactFlow</span>
                <span className="tech-purpose">DAG visualization of the agent pipeline</span>
              </div>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
};

export default AiIntegrationInfo;
