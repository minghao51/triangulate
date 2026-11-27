import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { MapPinned, Globe2, MapPinOff, CircleSlash } from 'lucide-react';
import type { TimelineEvent } from '../../types/backend-models';
import { getTimelineForCase } from '../../services/api';
import { isNotFound } from '../../services/api-error';
import ReaderState from '../../components/design-system/ReaderState';
import { classifyCoordinate, coordinateStateLabel, projectCoordinate } from './coordinates';
import './MapTab.css';

interface MapTabProps {
  caseId: string;
  refreshToken?: number;
}

interface PlottableEvent {
  event: TimelineEvent;
  leftPercent: number;
  topPercent: number;
}

interface UnplottableEvent {
  event: TimelineEvent;
  state: 'invalid' | 'missing';
  label: string;
  reason: string | null;
}

/** The event context/list for a case. Never an invented inspector claim id. */
const eventContextHref = (caseId: string): string =>
  `/cases/${encodeURIComponent(caseId)}/timeline`;

/**
 * Geotagged reader.
 *
 * Only coordinates that are *stored* in the timeline row are plotted: finite
 * numbers inside the inclusive WGS-84 ranges. Nothing is inferred — no
 * centroid, no geocoding, no country fallback, no tiles and no browser
 * location permission. `0, 0` is a recorded position at 0,0; `invalid` and
 * `missing` are separate states and are listed (never silently dropped).
 *
 * The timeline is queried under the same `['timeline', caseId]` key the other
 * timeline readers use, so a case has exactly one timeline cache entry and a
 * slow response for a previous case can never populate the current case. The
 * `refreshToken` prop is a parent-driven refresh signal; it is not part of the
 * key (it does not change the result), it just asks the query to refetch.
 */
const MapTab: React.FC<MapTabProps> = ({ caseId, refreshToken = 0 }) => {
  const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['timeline', caseId],
    queryFn: () => getTimelineForCase(caseId),
    enabled: Boolean(caseId),
  });

  const lastRefreshToken = useRef(refreshToken);
  useEffect(() => {
    if (lastRefreshToken.current === refreshToken) return;
    lastRefreshToken.current = refreshToken;
    void refetch();
  }, [refreshToken, refetch]);

  const events = useMemo(() => data ?? [], [data]);

  const { plottable, unplottable } = useMemo(() => {
    const plotted: PlottableEvent[] = [];
    const unplotted: UnplottableEvent[] = [];

    for (const event of events) {
      const classification = classifyCoordinate(event.locationLat, event.locationLon);
      if (classification.state === 'recorded') {
        const projection = projectCoordinate(event.locationLat, event.locationLon);
        // A recorded pair always projects; the guard keeps the types honest.
        if (projection) {
          plotted.push({
            event,
            leftPercent: projection.leftPercent,
            topPercent: projection.topPercent,
          });
          continue;
        }
      }
      if (classification.state === 'missing' || classification.state === 'invalid') {
        unplotted.push({
          event,
          state: classification.state,
          label: coordinateStateLabel(classification.state),
          reason: classification.reason,
        });
      }
    }

    return { plottable: plotted, unplottable: unplotted };
  }, [events]);

  // Selection is keyed by the recorded event id only — never by a claim id.
  // The case id is stored beside the selection so a different case (a different
  // recorded data set) simply has no selection, without a state-resetting effect.
  const [selection, setSelection] = useState<{ caseId: string; eventId: string } | null>(
    null
  );
  const markerRefs = useRef(new Map<string, HTMLButtonElement>());
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());

  const selectedEventId = selection && selection.caseId === caseId ? selection.eventId : null;

  const selected = plottable.find((item) => item.event.id === selectedEventId) ?? null;

  const selectFromList = (eventId: string) => {
    setSelection({ caseId, eventId });
    markerRefs.current.get(eventId)?.focus();
  };

  const selectFromMarker = (eventId: string) => {
    setSelection({ caseId, eventId });
    rowRefs.current.get(eventId)?.focus();
  };

  const lastFetched = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  const unplottableList =
    unplottable.length > 0 ? (
      <section className="map-unplottable" aria-labelledby="map-unplottable-heading">
        <h4 id="map-unplottable-heading" className="map-unplottable-heading">
          {unplottable.length} event{unplottable.length === 1 ? '' : 's'} not plotted
        </h4>
        <ul className="map-unplottable-list">
          {unplottable.map(({ event, state, label, reason }) => (
            <li
              key={event.id}
              className="map-unplottable-row"
              data-coordinate-state={state}
            >
              <span className={`map-state-tag map-state-tag--${state}`}>
                {state === 'invalid' ? <CircleSlash size={12} /> : <MapPinOff size={12} />}
                {label}
              </span>
              <span className="map-unplottable-title">{event.title}</span>
              {reason && <span className="map-unplottable-reason">{reason}</span>}
              <Link className="map-event-link" to={eventContextHref(caseId)}>
                Open event context
              </Link>
            </li>
          ))}
        </ul>
      </section>
    ) : null;

  let stateBody: React.ReactNode;
  if (!caseId) {
    stateBody = (
      <ReaderState
        state="not-found"
        title="No case selected"
        description="Choose a case to view its mapped timeline events."
      />
    );
  } else if (isLoading) {
    stateBody = (
      <ReaderState
        state="loading"
        description="Fetching mapped timeline events for this case."
      />
    );
  } else if (error) {
    stateBody = isNotFound(error) ? (
      <ReaderState state="not-found" description="This case has no timeline to map." />
    ) : (
      <ReaderState
        state="network-error"
        description="The mapped events could not be loaded."
        detail={error instanceof Error ? error.message : null}
        onRetry={() => {
          void refetch();
        }}
        lastFetched={lastFetched}
      />
    );
  } else if (plottable.length === 0) {
    // `map-empty`: distinct from loading/error. Unplottable events are still
    // listed below so nothing recorded is hidden.
    stateBody = (
      <>
        <ReaderState
          state="empty"
          className="map-empty"
          description="No geotagged events are available for this case yet."
          lastFetched={lastFetched}
        />
        {unplottableList}
      </>
    );
  } else {
    stateBody = (
      <>
        <div className="map-layout">
          <div className="map-canvas glass-panel" role="group" aria-label="Projected event map">
            <div className="map-grid" />
            {plottable.map(({ event, leftPercent, topPercent }) => {
              const isSelected = event.id === selectedEventId;
              return (
                <button
                  key={event.id}
                  ref={(node) => {
                    if (node) markerRefs.current.set(event.id, node);
                    else markerRefs.current.delete(event.id);
                  }}
                  className={`map-marker${isSelected ? ' map-marker--selected' : ''}`}
                  style={{ left: `${leftPercent}%`, top: `${topPercent}%` }}
                  title={`${event.title} (${event.locationLat}, ${event.locationLon})`}
                  aria-label={`${event.title} at ${event.locationLat}, ${event.locationLon}`}
                  aria-pressed={isSelected}
                  data-event-id={event.id}
                  type="button"
                  onClick={() => selectFromMarker(event.id)}
                >
                  <span className="map-marker-dot" />
                </button>
              );
            })}
          </div>

          <ul className="map-event-list" aria-label="Mapped events">
            {plottable.map(({ event }) => {
              const isSelected = event.id === selectedEventId;
              return (
                <li key={event.id} className="map-event-card glass-panel">
                  <button
                    ref={(node) => {
                      if (node) rowRefs.current.set(event.id, node);
                      else rowRefs.current.delete(event.id);
                    }}
                    className={`map-event-select${isSelected ? ' map-event-select--selected' : ''}`}
                    aria-pressed={isSelected}
                    data-event-id={event.id}
                    type="button"
                    onClick={() => selectFromList(event.id)}
                  >
                    <span className="map-event-title-row">
                      <span className="badge badge-info">{event.verificationStatus}</span>
                      {event.locationCountryCode && (
                        <span className="badge badge-neutral">{event.locationCountryCode}</span>
                      )}
                    </span>
                    <span className="map-event-heading">{event.title}</span>
                    {event.summary && <span className="map-event-summary">{event.summary}</span>}
                    <code className="map-event-coordinates">
                      {event.locationLat?.toFixed(4)}, {event.locationLon?.toFixed(4)}
                    </code>
                  </button>
                  <Link className="map-event-link" to={eventContextHref(caseId)}>
                    Open event context
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
        {selected && (
          <p className="map-selection-note" role="status">
            Selected: {selected.event.title} at {selected.event.locationLat},{' '}
            {selected.event.locationLon}
          </p>
        )}
        {unplottableList}
      </>
    );
  }

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
            {plottable.length} mapped
          </span>
          {unplottable.length > 0 && (
            <span className="map-summary-pill">
              <MapPinOff size={14} />
              {unplottable.length} not plotted
            </span>
          )}
          <span className="map-summary-pill">
            <Globe2 size={14} />
            {events.length} total events
          </span>
        </div>
      </div>

      {stateBody}
    </div>
  );
};

export default MapTab;
