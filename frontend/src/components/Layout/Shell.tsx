import React from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { Search, FolderGit2, ShieldAlert, Activity, FileText } from 'lucide-react';
import clsx from 'clsx';
import './Shell.css';

const Shell: React.FC = () => {
    return (
        <div className="shell-container">
            {/* Sidebar */}
            <nav className="shell-sidebar">
                <div className="shell-brand">
                    <ShieldAlert size={24} className="brand-icon" />
                    <span>Triangulate</span>
                </div>

                <div className="shell-nav-section">
                    <div className="shell-nav-title">WORKSPACE</div>
                    <NavLink to="/" className={({ isActive }) => clsx("shell-nav-item", isActive && "active")} end>
                        <FolderGit2 size={18} />
                        <span>Investigations</span>
                    </NavLink>
                    <NavLink to="/cases/new" className={({ isActive }) => clsx("shell-nav-item", isActive && "active")}>
                        <Search size={18} />
                        <span>New Case</span>
                    </NavLink>
                </div>

                <div className="shell-nav-section">
                    <div className="shell-nav-title">SYSTEM</div>
                    <NavLink to="/monitoring" className="shell-nav-item">
                        <Activity size={18} />
                        <span>Exceptions Queue</span>
                    </NavLink>
                    <NavLink to="/reports" className="shell-nav-item">
                        <FileText size={18} />
                        <span>Generated Reports</span>
                    </NavLink>
                </div>
            </nav>

            {/* Main Content Area */}
            <main className="shell-main">
                <header className="shell-header">
                    <div className="header-breadcrumbs">
                        <span>Workspace</span> / <span className="active-breadcrumb">All Cases</span>
                    </div>
                    <div className="header-actions">
                        <div className="user-profile">Analyst OS</div>
                    </div>
                </header>
                <div className="shell-content">
                    <Outlet />
                </div>
            </main>
        </div>
    );
};

export default Shell;
