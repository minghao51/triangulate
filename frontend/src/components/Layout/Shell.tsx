import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import {
  ShieldAlert,
  Search,
  FolderGit2,
  Activity,
  BarChart3,
  ChevronRight,
  Github,
  Info,
  Menu,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import './Shell.css';

interface Breadcrumb {
  label: string;
  path: string;
}

const CASE_SECTION_LABELS: Record<string, string> = {
  evidence: 'Evidence',
  claims: 'Claims',
  compare: 'Compare',
  parties: 'Parties',
  map: 'Map',
  timeline: 'Timeline',
  exceptions: 'Exceptions',
  report: 'Report',
  changes: 'Changes',
  search: 'Search',
  'run-history': 'Run History',
  pipeline: 'Pipeline Monitor',
  network: 'Corroboration Network',
  sources: 'Source Analysis',
  narratives: 'Narrative Landscape',
};

const FALLBACK_DATA_MODE_LABEL = 'Static preferred; missing fixtures may use API';
const CONFIGURED_DATA_MODE_LABEL = 'Configured API';

/**
 * The only configuration the shell reads. When `VITE_API_BASE_URL` is absent the
 * client still prefers bundled fixtures but falls through to the same-origin
 * `/api` path for missing fixtures — that fallback must never be described as
 * fixture-only, offline or live.
 */
function readConfiguredApiBase(): string {
  const base = import.meta.env.VITE_API_BASE_URL;
  return typeof base === 'string' ? base.trim() : '';
}

function buildBreadcrumbs(pathname: string): Breadcrumb[] {
  const segments = pathname.split('/').filter(Boolean);
  const breadcrumbs: Breadcrumb[] = [{ label: 'Workspace', path: '/dashboard' }];
  const [root, second, third] = segments;

  if (root === 'cases') {
    breadcrumbs.push({ label: 'Cases', path: '/cases' });
    if (second === 'new') {
      breadcrumbs.push({ label: 'CLI Launch Guide', path: '/cases/new' });
    } else if (second) {
      breadcrumbs.push({ label: `Case ${second.slice(0, 8)}`, path: `/cases/${second}` });
      if (third) {
        breadcrumbs.push({
          label: CASE_SECTION_LABELS[third] ?? third.replace(/-/g, ' '),
          path: `/cases/${second}/${third}`,
        });
      }
    }
  } else if (root === 'monitoring') {
    breadcrumbs.push({ label: 'Monitoring Center', path: '/monitoring' });
  } else if (root === 'ai-info') {
    breadcrumbs.push({ label: 'AI Integration', path: '/ai-info' });
  }

  return breadcrumbs;
}

const Shell: React.FC = () => {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const navToggleRef = useRef<HTMLButtonElement>(null);
  const navPanelsRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const previousPathRef = useRef(location.pathname);

  const breadcrumbs = buildBreadcrumbs(location.pathname);
  const configuredApiBase = readConfiguredApiBase();
  const dataModeLabel = configuredApiBase
    ? CONFIGURED_DATA_MODE_LABEL
    : FALLBACK_DATA_MODE_LABEL;

  // Route change: move focus to the main content region so keyboard and
  // screen-reader users land on the new view. Navigating from the menu itself
  // collapses the disclosure in the link handlers below.
  useEffect(() => {
    if (previousPathRef.current === location.pathname) return;
    previousPathRef.current = location.pathname;
    mainRef.current?.focus();
  }, [location.pathname]);

  // Opening the menu moves focus to the first navigation link.
  useEffect(() => {
    if (!menuOpen) return;
    const firstLink = navPanelsRef.current?.querySelector<HTMLElement>('a[href]');
    firstLink?.focus();
  }, [menuOpen]);

  // Closing returns focus to the toggle that opened the menu.
  const closeMenu = useCallback(() => {
    setMenuOpen(false);
    navToggleRef.current?.focus();
  }, []);

  // Following a navigation link collapses the disclosure without stealing the
  // focus that the route-change effect is about to place on the main region.
  const handleNavigate = useCallback(() => {
    setMenuOpen(false);
  }, []);

  const handleToggleMenu = () => {
    if (menuOpen) {
      closeMenu();
      return;
    }
    setMenuOpen(true);
  };

  const handleNavKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape' && menuOpen) {
      event.stopPropagation();
      closeMenu();
    }
  };

  return (
    <div className="shell-container">
      <a
        className="shell-skip-link"
        href="#shell-main"
        onClick={(event) => {
          event.preventDefault();
          mainRef.current?.focus();
        }}
      >
        Skip to main content
      </a>

      <nav
        id="shell-navigation"
        className={clsx('shell-sidebar', menuOpen && 'open')}
        aria-label="Main"
        onKeyDown={handleNavKeyDown}
      >
        <div className="shell-nav-head">
          <div className="shell-brand">
            <div className="brand-icon-wrapper">
              <ShieldAlert size={20} className="brand-icon" aria-hidden="true" />
            </div>
            <div className="brand-text">
              <span className="brand-name">TRIANGULATE</span>
              <span className="brand-tagline">Intelligence Platform</span>
            </div>
          </div>

          <button
            type="button"
            ref={navToggleRef}
            className="shell-menu-toggle"
            aria-expanded={menuOpen}
            aria-controls="shell-nav-panels"
            aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            onClick={handleToggleMenu}
          >
            {menuOpen ? (
              <X size={18} aria-hidden="true" />
            ) : (
              <Menu size={18} aria-hidden="true" />
            )}
            <span className="shell-menu-toggle-text">Menu</span>
          </button>
        </div>

        <div
          id="shell-nav-panels"
          ref={navPanelsRef}
          className="shell-nav-panels"
          hidden={!menuOpen}
        >
          <div className="shell-nav-section">
            <div className="shell-nav-title">INVESTIGATION</div>
            <NavLink
              to="/dashboard"
              onClick={handleNavigate}
              className={({ isActive }) => clsx('shell-nav-item', isActive && 'active')}
              end
            >
              <BarChart3 size={16} className="nav-icon" aria-hidden="true" />
              <span>Dashboard</span>
            </NavLink>
            <NavLink
              to="/cases"
              onClick={handleNavigate}
              className={({ isActive }) => clsx('shell-nav-item', isActive && 'active')}
            >
              <FolderGit2 size={16} className="nav-icon" aria-hidden="true" />
              <span>Case Explorer</span>
            </NavLink>
            <NavLink
              to="/cases/new"
              onClick={handleNavigate}
              className={({ isActive }) => clsx('shell-nav-item', isActive && 'active')}
            >
              <Search size={16} className="nav-icon" aria-hidden="true" />
              <span>CLI Launch Guide</span>
            </NavLink>
          </div>

          <div className="shell-nav-section">
            <div className="shell-nav-title">ANALYSIS</div>
            <NavLink
              to="/monitoring"
              onClick={handleNavigate}
              className={({ isActive }) => clsx('shell-nav-item', isActive && 'active')}
            >
              <Activity size={16} className="nav-icon" aria-hidden="true" />
              <span>Monitoring Center</span>
            </NavLink>
          </div>

          <div className="shell-nav-section">
            <div className="shell-nav-title">SYSTEM</div>
            <NavLink
              to="/ai-info"
              onClick={handleNavigate}
              className={({ isActive }) => clsx('shell-nav-item', isActive && 'active')}
            >
              <Info size={16} className="nav-icon" aria-hidden="true" />
              <span>AI Integration</span>
            </NavLink>
          </div>
        </div>
      </nav>

      <div className="shell-main-column">
        <header className="shell-header">
          <nav className="header-breadcrumbs" aria-label="Breadcrumb">
            <ol className="breadcrumb-list">
              {breadcrumbs.map((crumb, index) => {
                const isLast = index === breadcrumbs.length - 1;
                return (
                  <li className="breadcrumb-segment" key={`${crumb.path}-${index}`}>
                    {index > 0 && (
                      <ChevronRight
                        size={14}
                        className="breadcrumb-separator"
                        aria-hidden="true"
                      />
                    )}
                    {isLast ? (
                      <span className="breadcrumb-item breadcrumb-item-active" aria-current="page">
                        {crumb.label}
                      </span>
                    ) : (
                      <NavLink to={crumb.path} className="breadcrumb-item">
                        {crumb.label}
                      </NavLink>
                    )}
                  </li>
                );
              })}
            </ol>
          </nav>

          <div className="header-actions">
            <a
              href="https://github.com/minghao51/triangulate"
              target="_blank"
              rel="noopener noreferrer"
              className="header-action-btn"
              aria-label="Triangulate repository on GitHub"
            >
              <Github size={18} aria-hidden="true" />
            </a>
          </div>
        </header>

        <section
          className="shell-boundary"
          aria-label="Trust boundary and configured data mode"
        >
          <p className="shell-boundary-text">
            <strong>Local, trusted, unauthenticated boundary.</strong> This instance has no
            sign-in; anyone who can reach it can read and change case data. Do not expose it to
            untrusted networks.
          </p>
          <p className="shell-data-mode">
            <span className="shell-data-mode-label">Data mode</span>
            <span className="shell-data-mode-value">{dataModeLabel}</span>
          </p>
          <p className="shell-boundary-note">
            /health reports process liveness only — it is not a readiness or permission check.
          </p>
        </section>

        <main id="shell-main" ref={mainRef} className="shell-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default Shell;
