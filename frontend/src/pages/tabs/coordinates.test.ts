import { describe, expect, it } from 'vitest';

import {
  classifyCoordinate,
  coordinateStateLabel,
  isPlotable,
  projectCoordinate,
} from './coordinates';

describe('classifyCoordinate recorded range boundaries', () => {
  it('accepts the inclusive latitude and longitude limits as recorded', () => {
    const cases: Array<[number, number]> = [
      [-90, -180],
      [-90, 180],
      [90, -180],
      [90, 180],
      [90, 0],
      [-90, 0],
      [0, 180],
      [0, -180],
      [51.5, -0.1],
    ];

    for (const [lat, lon] of cases) {
      const result = classifyCoordinate(lat, lon);
      expect(result.state).toBe('recorded');
      expect(result.lat).toBe(lat);
      expect(result.lon).toBe(lon);
      expect(result.reason).toBeNull();
      expect(isPlotable(lat, lon)).toBe(true);
    }
  });

  it('classifies a value immediately outside each limit as invalid', () => {
    const cases: Array<[number, number, string]> = [
      [90.0001, 0, 'latitude above the north limit'],
      [-90.0001, 0, 'latitude below the south limit'],
      [0, 180.0001, 'longitude past the east limit'],
      [0, -180.0001, 'longitude past the west limit'],
      [91, 0, 'latitude out of range'],
      [0, 181, 'longitude out of range'],
      [1000, 1000, 'both out of range'],
    ];

    for (const [lat, lon, label] of cases) {
      const result = classifyCoordinate(lat, lon);
      expect(result.state, label).toBe('invalid');
      expect(result.reason, label).not.toBeNull();
      expect(isPlotable(lat, lon), label).toBe(false);
      // An invalid pair still reports what was stored — nothing is repaired.
      expect(result.lat, label).toBe(lat);
      expect(result.lon, label).toBe(lon);
    }
  });

  it('classifies NaN and either infinity as invalid rather than missing', () => {
    const cases: Array<[number, number]> = [
      [Number.NaN, 0],
      [0, Number.NaN],
      [Number.NaN, Number.NaN],
      [Number.POSITIVE_INFINITY, 0],
      [Number.NEGATIVE_INFINITY, 0],
      [0, Number.POSITIVE_INFINITY],
      [0, Number.NEGATIVE_INFINITY],
    ];

    for (const [lat, lon] of cases) {
      const result = classifyCoordinate(lat, lon);
      expect(result.state).toBe('invalid');
      expect(isPlotable(lat, lon)).toBe(false);
      expect(projectCoordinate(lat, lon)).toBeNull();
    }
  });

  it('classifies a non-numeric stored value as invalid', () => {
    const result = classifyCoordinate('51.5', -0.1);
    expect(result.state).toBe('invalid');
    expect(result.reason).not.toBeNull();
  });
});

describe('classifyCoordinate zero is recorded, not unknown', () => {
  it('treats 0,0 as a recorded position at 0,0', () => {
    const result = classifyCoordinate(0, 0);
    expect(result.state).toBe('recorded');
    expect(result.lat).toBe(0);
    expect(result.lon).toBe(0);

    expect(projectCoordinate(0, 0)).toEqual({ leftPercent: 50, topPercent: 50 });
  });

  it('keeps missing coordinates as a third, distinct state', () => {
    const missingCases: Array<[unknown, unknown]> = [
      [null, null],
      [undefined, undefined],
      [null, -0.1],
      [51.5, null],
      [undefined, 0],
      [0, undefined],
    ];

    for (const [lat, lon] of missingCases) {
      const result = classifyCoordinate(lat, lon);
      expect(result.state).toBe('missing');
      expect(result.reason).toBeNull();
      expect(isPlotable(lat, lon)).toBe(false);
      expect(projectCoordinate(lat, lon)).toBeNull();
    }

    // The three states never collapse into each other.
    const states = [
      classifyCoordinate(0, 0).state,
      classifyCoordinate(91, 0).state,
      classifyCoordinate(null, null).state,
    ];
    expect(new Set(states)).toEqual(new Set(['recorded', 'invalid', 'missing']));
  });
});

describe('projectCoordinate projection', () => {
  it('maps the corners of the field to the corners of the projection', () => {
    expect(projectCoordinate(90, -180)).toEqual({ leftPercent: 0, topPercent: 0 });
    expect(projectCoordinate(-90, 180)).toEqual({ leftPercent: 100, topPercent: 100 });
    expect(projectCoordinate(90, 180)).toEqual({ leftPercent: 100, topPercent: 0 });
    expect(projectCoordinate(-90, -180)).toEqual({ leftPercent: 0, topPercent: 100 });
  });

  it('never invents a position for an unplottable pair', () => {
    expect(projectCoordinate(NaN, NaN)).toBeNull();
    expect(projectCoordinate(Infinity, 0)).toBeNull();
    expect(projectCoordinate(null, 0)).toBeNull();
  });
});

describe('coordinateStateLabel', () => {
  it('gives each state its own wording', () => {
    const labels = [
      coordinateStateLabel('recorded'),
      coordinateStateLabel('invalid'),
      coordinateStateLabel('missing'),
    ];
    expect(new Set(labels).size).toBe(3);
  });
});
