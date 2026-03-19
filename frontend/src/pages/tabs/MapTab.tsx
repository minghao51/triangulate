import React, { useEffect, useMemo, useState } from 'react';
import { MapPinned, Globe2, LocateFixed } from 'lucide-react';
import type { TimelineEvent } from '../../types/backend-models';
import { getTimelineForCase } from '../../services/api';
import './MapTab.css';

interface MapTabProps {
  caseId: string;
  refreshToken?: number;
}

interface MappedEvent extends TimelineEvent {
  projectedLeft: number;
  projectedTop: number;
}

const MapTab: React.FC<MapTabProps> = ({ caseId, refreshToken = 0 }) => {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!caseId) {
      return;
    }

    getTimelineForCase(caseId).then(setEvents).catch((err: Error) => setError(err.message));
  }, [caseId, refreshToken]);

  const mappedEvents = useMemo<MappedEvent[]>(
    () =>
      events
        .filter(
          (event) =>
            typeof event.locationLat === 'number' && typeof event.locationLon === 'number'
        )
        .map((event) => ({
          ...event,
          projectedLeft: ((event.locationLon ?? 0) + 180) / 360 * 100,
          projectedTop: ((90 - (event.locationLat ?? 0)) / 180) * 100,
        })),
    [events]
  );

  return (
    <div className="map-tab-container p-base">
      <div className="map-tab-header">
        <div>
          <h3>Geographic Event Map</h3>
          <p className="subtitle">Mapped timeline events with extracted coordinates.</p>
        </div>
        <div className="map-summary">
          <span className="map-summary-pill">
            <MapPinned size={14} />
            {mappedEvents.length} mapped
          </span>
          <span className="map-summary-pill">
            <Globe2 size={14} />
            {events.length} total events
          </span>
        </div>
      </div>

      {error && <div className="map-empty-state">Failed to load map data: {error}</div>}

      {!error && mappedEvents.length === 0 && (
        <div className="map-empty-state glass-panel">
          <LocateFixed size={18} />
          <span>No geotagged events are available for this case yet.</span>
        </div>
      )}

      {!error && mappedEvents.length > 0 && (
        <div className="map-layout">
          <div className="map-canvas glass-panel" aria-label="Projected event map">
            <div className="map-grid" />
            {mappedEvents.map((event) => (
              <button
                key={event.id}
                className="map-marker"
                style={{
                  left: `${event.projectedLeft}%`,
                  top: `${event.projectedTop}%`,
                }}
                title={`${event.title} (${event.locationLat}, ${event.locationLon})`}
                type="button"
              >
                <span className="map-marker-dot" />
              </button>
            ))}
          </div>

          <div className="map-event-list">
            {mappedEvents.map((event) => (
              <div key={event.id} className="map-event-card glass-panel">
                <div className="map-event-title-row">
                  <span className="badge badge-info">{event.verificationStatus}</span>
                  {event.locationCountryCode && (
                    <span className="badge badge-neutral">{event.locationCountryCode}</span>
                  )}
                </div>
                <h4>{event.title}</h4>
                {event.summary && <p>{event.summary}</p>}
                <code>
                  {event.locationLat?.toFixed(4)}, {event.locationLon?.toFixed(4)}
                </code>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default MapTab;
