import React from 'react';
import Card, { CardBody, CardHeader, CardTitle } from '../components/design-system/Card';
import './OperatorLaunchGuide.css';

/**
 * Operator launch guide.
 *
 * Every command and endpoint below exists today. The web UI exposes exactly
 * three POST families (case review actions, exception actions, annotations);
 * case creation, ingestion, reruns, search-index rebuilds and writer recovery
 * are CLI-only. Nothing here claims notifications, scheduling, RBAC or
 * deployment control.
 */

const WRITE_SURFACE = [
  'POST /api/cases/{case-id}/review-actions/review',
  'POST /api/cases/{case-id}/review-actions/exceptions/{exception-id}',
  'POST /api/cases/{case-id}/annotations',
];

const CLI_COMMANDS: { command: string; purpose: string }[] = [
  {
    command: 'uv run triangulate fetch-topic "Gaza ceasefire negotiations"',
    purpose: 'Create a case from a topic query (case creation).',
  },
  {
    command: 'uv run triangulate osint ingest --tool <tool> --file <artifact> --case-id <case-id>',
    purpose: 'Ingest an OSINT artifact into an existing case.',
  },
  {
    command: 'uv run triangulate case rerun <case-id> --from retrieve',
    purpose: 'Rerun the pipeline for a case from a recorded stage.',
  },
  {
    command: 'uv run triangulate case rebuild-search <case-id>',
    purpose: 'Rebuild one case’s search-index rows (the only repair path for a search 503).',
  },
  {
    command: 'uv run triangulate case interrupt <case-id> --reason "<why>"',
    purpose: 'CLI-only writer recovery when a case writer must be interrupted.',
  },
  {
    command: 'uv run triangulate case evaluate <case-id>',
    purpose: 'Store an evaluation record; the HTTP evaluation reader never creates one.',
  },
];

const WORKFLOW_STEPS = [
  'Create the case or ingest material from the CLI.',
  'Run or rerun the pipeline from the CLI.',
  'Review recorded status, counts, exceptions and outputs in the web interface.',
  'Resolve exceptions, record review decisions and write annotations — the three POST families above.',
];

const OperatorLaunchGuide: React.FC = () => (
  <div className="operator-guide">
    <div className="operator-guide-header">
      <h1>Operator Launch Guide</h1>
      <p>
        Triangulate runs from the CLI and background workers. The website reads persisted case
        state and writes only review decisions, exception actions and annotations. It does not
        create cases, ingest material or start pipeline runs.
      </p>
    </div>

    <div className="operator-guide-grid">
      <Card className="glass-panel">
        <CardHeader>
          <CardTitle>Web Write Surface (Exactly Three POST Families)</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="operator-guide-commands">
            {WRITE_SURFACE.map((endpoint) => (
              <pre key={endpoint} className="operator-command">
                <code>{endpoint}</code>
              </pre>
            ))}
          </div>
          <p className="operator-guide-note">
            Everything else over HTTP is a GET reader. There is no notifications endpoint, no
            scheduling endpoint, no role or permission endpoint and no deployment control.
          </p>
        </CardBody>
      </Card>

      <Card className="glass-panel">
        <CardHeader>
          <CardTitle>Canonical Workflow</CardTitle>
        </CardHeader>
        <CardBody>
          <ol className="operator-guide-list">
            {WORKFLOW_STEPS.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </CardBody>
      </Card>
    </div>

    <Card className="glass-panel">
      <CardHeader>
        <CardTitle>CLI Commands</CardTitle>
      </CardHeader>
      <CardBody>
        <div className="operator-guide-commands">
          {CLI_COMMANDS.map((item) => (
            <div key={item.command} className="operator-guide-command">
              <pre className="operator-command">
                <code>{item.command}</code>
              </pre>
              <p className="operator-guide-note">{item.purpose}</p>
            </div>
          ))}
        </div>
      </CardBody>
    </Card>
  </div>
);

export default OperatorLaunchGuide;
