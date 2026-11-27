import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Shell from './Shell';

function renderShell(initialPath = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<Shell />}>
          <Route path="dashboard" element={<h1>Dashboard page</h1>} />
          <Route path="cases" element={<h1>Cases page</h1>} />
          <Route path="cases/new" element={<h1>New case page</h1>} />
          <Route path="cases/:id" element={<h1>Case page</h1>} />
          <Route path="cases/:id/*" element={<h1>Case section page</h1>} />
          <Route path="monitoring" element={<h1>Monitoring page</h1>} />
          <Route path="ai-info" element={<h1>AI page</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

/** Elements reachable by Tab in DOM order, skipping collapsed sub-trees. */
function tabbables(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>('a[href], button, [tabindex]:not([tabindex="-1"])')
  ).filter((element) => !element.closest('[hidden]') && !element.hasAttribute('disabled'));
}

function mainRegion(): HTMLElement {
  const main = document.getElementById('shell-main');
  if (!main) throw new Error('main content region missing');
  return main;
}

function navToggle(): HTMLElement {
  return screen.getByRole('button', { name: /navigation menu/i });
}

describe('Shell truthful chrome', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('renders no fabricated system status, notification count or identity', () => {
    const { container } = renderShell('/dashboard');

    // The three fabrications named by the contract are gone.
    expect(screen.queryByText(/System Online/i)).toBeNull();
    expect(container.querySelector('.notification-badge')).toBeNull();
    expect(screen.queryByText('3')).toBeNull();
    expect(screen.queryByText(/^Analyst$/)).toBeNull();
    expect(screen.queryByText(/^Administrator$/)).toBeNull();

    // No health-derived status dot/indicator remains either.
    expect(container.querySelector('.status-dot')).toBeNull();
    expect(screen.queryByText(/process ok/i)).toBeNull();
  });

  it('always shows a non-dismissible local/trusted unauthenticated caveat', () => {
    renderShell('/dashboard');

    const boundary = screen.getByRole('region', { name: /trust boundary/i });
    expect(within(boundary).getByText(/local, trusted, unauthenticated boundary/i)).toBeDefined();
    expect(within(boundary).getByText(/anyone who can reach it can read and change case data/i)).toBeDefined();
    // /health may only be described as process liveness.
    expect(within(boundary).getByText(/process liveness only/i)).toBeDefined();
    expect(within(boundary).queryByText(/readiness signal/i)).toBeNull();

    // Plain persistent text: no dismiss/close affordance and not inside the
    // collapsible navigation panel.
    expect(within(boundary).queryAllByRole('button')).toHaveLength(0);
    expect(boundary.closest('[hidden]')).toBeNull();
    expect(boundary.closest('#shell-navigation')).toBeNull();
  });

  it('labels the fallback data mode truthfully when no API base is configured', () => {
    vi.stubEnv('VITE_API_BASE_URL', '');
    renderShell('/dashboard');

    expect(screen.getByText('Static preferred; missing fixtures may use API')).toBeDefined();
    expect(screen.queryByText('Configured API')).toBeNull();
    // Never an unconditional Demo/Live claim.
    expect(screen.queryByText(/\bdemo\b/i)).toBeNull();
    expect(screen.queryByText(/\blive\b/i)).toBeNull();
    expect(screen.queryByText(/fixture[- ]only/i)).toBeNull();
  });

  it('labels the data mode as Configured API when an API base is configured', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000');
    renderShell('/dashboard');

    expect(screen.getByText('Configured API')).toBeDefined();
    expect(screen.queryByText('Static preferred; missing fixtures may use API')).toBeNull();
  });

  it('makes the skip link the first tab stop and moves focus to main', () => {
    const { container } = renderShell('/dashboard');

    const [firstFocusable] = tabbables(container);
    const skipLink = screen.getByRole('link', { name: /skip to main content/i });
    expect(firstFocusable).toBe(skipLink);
    expect(skipLink.getAttribute('href')).toBe('#shell-main');

    fireEvent.click(skipLink);

    expect(document.activeElement).toBe(mainRegion());
    expect(mainRegion().getAttribute('tabindex')).toBe('-1');
    expect(screen.getByRole('heading', { name: 'Dashboard page' })).toBeDefined();
  });

  it('opens the menu by button activation and closes it with Escape, returning focus', () => {
    renderShell('/dashboard');

    const toggle = navToggle();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.tagName).toBe('BUTTON');
    expect(toggle.getAttribute('aria-controls')).toBe('shell-nav-panels');

    fireEvent.click(toggle);

    expect(navToggle().getAttribute('aria-expanded')).toBe('true');
    const firstLink = screen.getByRole('link', { name: 'Dashboard' });
    expect(document.activeElement).toBe(firstLink);

    const nav = screen.getByRole('navigation', { name: 'Main' });
    fireEvent.keyDown(nav, { key: 'Escape' });

    expect(navToggle().getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('link', { name: 'Dashboard' })).toBeNull();
    expect(document.activeElement).toBe(navToggle());
  });

  it('closes the menu and moves focus to main content on route change', () => {
    renderShell('/dashboard');

    fireEvent.click(navToggle());
    expect(navToggle().getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(screen.getByRole('link', { name: 'Case Explorer' }));

    expect(screen.getByRole('heading', { name: 'Cases page' })).toBeDefined();
    expect(navToggle().getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(mainRegion());
  });

  it('reflects the current nested route in the breadcrumbs', () => {
    renderShell('/cases/case-1234abcd/pipeline');

    const breadcrumbs = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(within(breadcrumbs).getByText('Workspace')).toBeDefined();
    expect(within(breadcrumbs).getByText('Cases')).toBeDefined();
    expect(within(breadcrumbs).getByText('Case case-123')).toBeDefined();
    expect(within(breadcrumbs).getByText('Pipeline Monitor')).toBeDefined();

    const current = within(breadcrumbs).getByText('Pipeline Monitor');
    expect(current.getAttribute('aria-current')).toBe('page');
    expect(current.tagName).toBe('SPAN');
    expect(within(breadcrumbs).getByRole('link', { name: 'Cases' }).getAttribute('href')).toBe(
      '/cases'
    );
  });

  it('labels nested case sections rather than leaking raw path segments', () => {
    renderShell('/cases/case-1234abcd/claims');

    const breadcrumbs = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(within(breadcrumbs).getByText('Claims')).toBeDefined();
    expect(within(breadcrumbs).getByText('Claims').getAttribute('aria-current')).toBe('page');
  });
});
