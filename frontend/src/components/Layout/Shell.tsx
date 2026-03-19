import React from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import {
  ShieldAlert,
  Search,
  FolderGit2,
  Activity,
  BarChart3,
  ChevronRight,
  Bell,
} from 'lucide-react';
import clsx from 'clsx';
import './Shell.css';

const Shell: React.FC = () => {
  const location = useLocation();

  // Get breadcrumbs based on path
  const getBreadcrumbs = () => {
    const path = location.pathname;
    const breadcrumbs = [{ label: 'Workspace', path: '/dashboard' }];

    if (path.startsWith('/cases') && path !== '/cases' && !path.includes('/new')) {
      breadcrumbs.push({ label: 'Cases', path: '/cases' });
      const caseId = path.split('/')[2];
      if (caseId) {
        breadcrumbs.push({ label: `Case ${caseId.slice(0, 8)}`, path: `/cases/${caseId}` });

        // Add specialized view breadcrumbs
        if (path.includes('/pipeline')) {
          breadcrumbs.push({ label: 'Pipeline Monitor', path: `/cases/${caseId}/pipeline` });
        } else if (path.includes('/network')) {
          breadcrumbs.push({ label: 'Corroboration Network', path: `/cases/${caseId}/network` });
        } else if (path.includes('/sources')) {
          breadcrumbs.push({ label: 'Source Analysis', path: `/cases/${caseId}/sources` });
        } else if (path.includes('/narratives')) {
          breadcrumbs.push({ label: 'Narrative Landscape', path: `/cases/${caseId}/narratives` });
        }
      }
    }

    if (path.includes('/new')) {
      breadcrumbs.push({ label: 'Cases', path: '/cases' });
      breadcrumbs.push({ label: 'New', path: '/cases/new' });
    }

    if (path.startsWith('/monitoring')) {
      breadcrumbs.push({ label: 'Monitoring Center', path: '/monitoring' });
    }

    return breadcrumbs;
  };

  const breadcrumbs = getBreadcrumbs();

  return (
    <div className="shell-container">
      {/* Sidebar */}
      <nav className="shell-sidebar">
        {/* Brand */}
        <div className="shell-brand">
          <div className="brand-icon-wrapper">
            <ShieldAlert size={20} className="brand-icon" />
          </div>
          <div className="brand-text">
            <span className="brand-name">TRIANGULATE</span>
            <span className="brand-tagline">Intelligence Platform</span>
          </div>
        </div>

        {/* Navigation */}
        <div className="shell-nav-section">
          <div className="shell-nav-title">INVESTIGATION</div>
          <NavLink
            to="/dashboard"
            className={({ isActive }) => clsx("shell-nav-item", isActive && "active")}
            end
          >
            <BarChart3 size={16} className="nav-icon" />
            <span>Dashboard</span>
          </NavLink>
          <NavLink
            to="/cases"
            className={({ isActive }) => clsx("shell-nav-item", isActive && "active")}
          >
            <FolderGit2 size={16} className="nav-icon" />
            <span>Case Explorer</span>
          </NavLink>
          <NavLink
            to="/cases/new"
            className={({ isActive }) => clsx("shell-nav-item", isActive && "active")}
          >
            <Search size={16} className="nav-icon" />
            <span>CLI Launch Guide</span>
          </NavLink>
        </div>

        <div className="shell-nav-section">
          <div className="shell-nav-title">ANALYSIS</div>
          <NavLink to="/monitoring" className={({ isActive }) => clsx("shell-nav-item", isActive && "active")}>
            <Activity size={16} className="nav-icon" />
            <span>Monitoring Center</span>
          </NavLink>
        </div>

        {/* System Status */}
        <div className="shell-status">
          <div className="status-indicator">
            <span className="status-dot status-dot-active" />
            <span className="status-text">System Online</span>
          </div>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="shell-main">
        {/* Header */}
        <header className="shell-header">
          <div className="header-left">
            {/* Breadcrumbs */}
            <div className="header-breadcrumbs">
              {breadcrumbs.map((crumb, index) => (
                <React.Fragment key={crumb.path}>
                  {index > 0 && <ChevronRight size={14} className="breadcrumb-separator" />}
                  <NavLink
                    to={crumb.path}
                    className={() =>
                      clsx(
                        "breadcrumb-item",
                        index === breadcrumbs.length - 1 && "breadcrumb-item-active"
                      )
                    }
                  >
                    {crumb.label}
                  </NavLink>
                </React.Fragment>
              ))}
            </div>
          </div>

          <div className="header-right">
            {/* Notifications */}
            <button className="header-action-btn">
              <Bell size={18} />
              <span className="notification-badge">3</span>
            </button>

            {/* User Profile */}
            <div className="header-profile">
              <div className="profile-avatar">A</div>
              <div className="profile-info">
                <span className="profile-name">Analyst</span>
                <span className="profile-role">Administrator</span>
              </div>
            </div>
          </div>
        </header>

        {/* Content Area */}
        <div className="shell-content">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default Shell;
