/**
 * Recorded-coordinate classification for the geographic reader.
 *
 * The map plots **stored** coordinates and nothing else. There is deliberately
 * no centroid inference, no geocoding, no fallback country lookup and no
 * browser location permission: a coordinate is either recorded in the event
 * row, unusable but recorded (invalid), or absent (missing).
 *
 * The three states are mutually exclusive and visibly distinct:
 *
 * - `recorded` — both values are finite numbers inside the inclusive WGS-84
 *   ranges (latitude ∈ [-90, 90], longitude ∈ [-180, 180]). `0, 0` is a real
 *   recorded position and is never treated as "unknown".
 * - `invalid`  — a value is present but cannot be plotted: outside the range,
 *   `NaN`, `±Infinity`, or not a number at all.
 * - `missing`  — a value is `null`/`undefined` (or simply absent).
 *
 * Nothing here repairs or backfills data; repairing stored coordinates is a
 * separate data-owner decision (D01), not a rendering concern.
 */

export type CoordinateState = 'recorded' | 'invalid' | 'missing';

export interface CoordinateClassification {
  /** Which of the three recorded/absent states this pair is in. */
  state: CoordinateState;
  /** The latitude as recorded, or null when absent. */
  lat: number | null;
  /** The longitude as recorded, or null when absent. */
  lon: number | null;
  /**
   * Short human-readable reason for an `invalid` classification. Null for
   * `recorded` and `missing` (nothing to explain).
   */
  reason: string | null;
}

export const LATITUDE_MIN = -90;
export const LATITUDE_MAX = 90;
export const LONGITUDE_MIN = -180;
export const LONGITUDE_MAX = 180;

const isAbsent = (value: unknown): boolean => value === null || value === undefined;

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const asRecorded = (value: unknown): number | null =>
  isFiniteNumber(value) ? value : null;

const outOfRangeReason = (lat: number, lon: number): string | null => {
  if (lat < LATITUDE_MIN || lat > LATITUDE_MAX) {
    return `Latitude ${lat} is outside [-90, 90]`;
  }
  if (lon < LONGITUDE_MIN || lon > LONGITUDE_MAX) {
    return `Longitude ${lon} is outside [-180, 180]`;
  }
  return null;
};

const nonNumericReason = (value: unknown): string | null => {
  if (isAbsent(value) || isFiniteNumber(value)) return null;
  return 'A recorded coordinate is not a finite number';
};

/**
 * Classify one stored coordinate pair.
 *
 * Both values are required for a plot: a half-recorded pair (one side absent)
 * is `missing`, because nothing may be invented for the other side.
 */
export function classifyCoordinate(
  lat: unknown,
  lon: unknown
): CoordinateClassification {
  if (isAbsent(lat) || isAbsent(lon)) {
    return {
      state: 'missing',
      lat: asRecorded(lat),
      lon: asRecorded(lon),
      reason: null,
    };
  }

  const nonNumeric = nonNumericReason(lat) ?? nonNumericReason(lon);
  if (nonNumeric !== null) {
    return {
      state: 'invalid',
      lat: asRecorded(lat),
      lon: asRecorded(lon),
      reason: nonNumeric,
    };
  }

  const reason = outOfRangeReason(lat as number, lon as number);
  if (reason !== null) {
    return {
      state: 'invalid',
      lat: asRecorded(lat),
      lon: asRecorded(lon),
      reason,
    };
  }

  return { state: 'recorded', lat: lat as number, lon: lon as number, reason: null };
}

/** True only for a finite, in-range pair — the sole condition for plotting. */
export function isPlotable(lat: unknown, lon: unknown): boolean {
  return classifyCoordinate(lat, lon).state === 'recorded';
}

export interface ProjectedCoordinate {
  /** Percentage position from the left edge of the equirectangular field. */
  leftPercent: number;
  /** Percentage position from the top edge of the equirectangular field. */
  topPercent: number;
}

/**
 * Project a recorded coordinate into a plain equirectangular field.
 *
 * This is the existing CSS projection (no tiles, no map library): longitude
 * maps linearly to the horizontal axis and latitude is flipped on the vertical
 * axis. Only recorded pairs may be projected; invalid/missing pairs return
 * null so a caller cannot accidentally plot them at an implied position.
 */
export function projectCoordinate(
  lat: unknown,
  lon: unknown
): ProjectedCoordinate | null {
  const classification = classifyCoordinate(lat, lon);
  if (classification.state !== 'recorded') return null;

  const latitude = classification.lat as number;
  const longitude = classification.lon as number;
  return {
    leftPercent: ((longitude + LONGITUDE_MAX) / (LONGITUDE_MAX - LONGITUDE_MIN)) * 100,
    topPercent: ((LATITUDE_MAX - latitude) / (LATITUDE_MAX - LATITUDE_MIN)) * 100,
  };
}

/** Human-readable label for a state, used in the accessible event list. */
export function coordinateStateLabel(state: CoordinateState): string {
  switch (state) {
    case 'recorded':
      return 'Recorded coordinates';
    case 'invalid':
      return 'Invalid coordinates';
    case 'missing':
      return 'No recorded coordinates';
    default:
      return 'Unknown coordinate state';
  }
}
