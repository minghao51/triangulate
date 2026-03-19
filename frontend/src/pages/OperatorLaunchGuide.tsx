import React from 'react';
import Card, { CardBody, CardHeader, CardTitle } from '../components/design-system/Card';
import './OperatorLaunchGuide.css';

const OperatorLaunchGuide: React.FC = () => {
  const commands = [
    'uv run triangulate fetch-topic "Gaza ceasefire negotiations"',
    'uv run triangulate monitor --start --topics ./topics.yaml --interval 30',
    'uv run triangulate ingest',
    'uv run triangulate process',
    'uv run triangulate process-url "https://example.com/article" --save',
  ];

  return (
    <div className="operator-guide">
      <div className="operator-guide-header">
        <h1>Operator Launch Guide</h1>
        <p>
          Triangulate runs from the CLI or background workers. The website only presents persisted
          case state and does not trigger ingestion or pipeline execution.
        </p>
      </div>

      <div className="operator-guide-grid">
        <Card className="glass-panel">
          <CardHeader>
            <CardTitle>Canonical Workflow</CardTitle>
          </CardHeader>
          <CardBody>
            <ol className="operator-guide-list">
              <li>Capture or ingest material from the CLI.</li>
              <li>Create or update a case from the service-backed case workflow.</li>
              <li>Review run status, exceptions, and outputs in the web interface.</li>
              <li>Use CLI commands for reruns, reviews, and exception handling.</li>
            </ol>
          </CardBody>
        </Card>

        <Card className="glass-panel">
          <CardHeader>
            <CardTitle>Example Commands</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="operator-guide-commands">
              {commands.map((command) => (
                <pre key={command} className="operator-command">
                  <code>{command}</code>
                </pre>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
};

export default OperatorLaunchGuide;
