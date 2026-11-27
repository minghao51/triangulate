import { expect, type Page } from '@playwright/test';
import { appendFileSync, mkdirSync } from 'node:fs';

/**
 * Shared gate assertions: page hygiene (no uncaught error, no console.error),
 * document-level horizontal overflow and per-cell screenshots.
 *
 * Artifacts are written outside the checkout so a gate run never dirties the
 * worktree.
 */

export const SCREENSHOT_ROOT = '/tmp/refinement-gate/screens';

export interface PageHygiene {
  consoleErrors: string[];
  pageErrors: string[];
  /**
   * Browser-emitted lines for a non-2xx response. These are not application
   * `console.error` calls: a state test that deliberately answers 404/500/422
   * makes the browser log "Failed to load resource: … status of NNN". They are
   * counted separately and reported, never silently mixed into app errors.
   */
  transportStatusLines: string[];
  assertClean: (label: string) => void;
}

const TRANSPORT_STATUS_LINE = /^Failed to load resource: the server responded with a status of \d+/;

export function attachPageHygiene(page: Page): PageHygiene {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const transportStatusLines: string[] = [];

  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (TRANSPORT_STATUS_LINE.test(text)) {
      transportStatusLines.push(text);
      return;
    }
    consoleErrors.push(text);
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('requestfailed', (request) => {
    // A blocked/aborted request is a console-level failure worth surfacing.
    pageErrors.push(`request failed: ${request.method()} ${request.url()}`);
  });

  return {
    consoleErrors,
    pageErrors,
    transportStatusLines,
    assertClean(label: string) {
      expect(pageErrors, `${label}: uncaught page error`).toEqual([]);
      expect(consoleErrors, `${label}: console.error`).toEqual([]);
    },
  };
}

export interface OverflowReading {
  scrollWidth: number;
  innerWidth: number;
  widest: string;
}

/**
 * Document-level horizontal overflow.
 *
 * The recipe: `document.documentElement.scrollWidth <= window.innerWidth + 1`.
 * The widest offending element is reported too, so a failure is actionable.
 */
export async function readHorizontalOverflow(page: Page): Promise<OverflowReading> {
  return page.evaluate(() => {
    const root = document.documentElement;
    const viewport = window.innerWidth;
    let widest = '';
    let widestRight = viewport;
    for (const element of Array.from(root.querySelectorAll<HTMLElement>('body *'))) {
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      if (rect.right > widestRight) {
        widestRight = rect.right;
        const tag = element.tagName.toLowerCase();
        const cls = element.className && typeof element.className === 'string'
          ? `.${element.className.trim().split(/\s+/).join('.')}`
          : '';
        widest = `${tag}${cls} right=${Math.round(rect.right)}`;
      }
    }
    return { scrollWidth: root.scrollWidth, innerWidth: viewport, widest };
  });
}

export async function assertNoHorizontalOverflow(page: Page, label: string) {
  const reading = await readHorizontalOverflow(page);
  expect(
    reading.scrollWidth,
    `${label}: document scrollWidth ${reading.scrollWidth} > innerWidth ${reading.innerWidth} (widest: ${reading.widest})`
  ).toBeLessThanOrEqual(reading.innerWidth + 1);
  return reading;
}

export const CELL_LOG = '/tmp/refinement-gate/cells.jsonl';

export interface CellRecord {
  cell: string;
  project: string;
  suite: string;
  /** Text observed in the browser for this cell (the recorded marker). */
  marker: string;
  overflow: OverflowReading;
  transportStatusLines: string[];
  appConsoleErrors: string[];
  pageErrors: string[];
}

/** Append one evidence line per gate cell (workers = 1, so ordering is stable). */
export function recordCell(record: CellRecord) {
  mkdirSync('/tmp/refinement-gate', { recursive: true });
  appendFileSync(CELL_LOG, `${JSON.stringify(record)}\n`, 'utf8');
}

/** One screenshot per gate cell, outside the checkout. */
export async function captureCell(page: Page, project: string, cell: string) {
  const directory = `${SCREENSHOT_ROOT}/${project.replace(/[^\w.-]+/g, '_')}`;
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: `${directory}/${cell}.png`, fullPage: true });
}

/** Wait until the app shell has rendered content inside `main`. */
export async function waitForShell(page: Page) {
  await expect(page.locator('main#shell-main')).toBeVisible();
}
