import { useState, useRef, useEffect } from 'react';
import { Home, LayoutDashboard, Bot, ChevronDown, Settings, Users, User, LogOut, Building2, AlertTriangle } from 'lucide-react';
import type { ViewId, AgentConfig, AppUser } from '../../types';

interface NavBarProps {
  currentView: ViewId;
  onNavigate: (view: ViewId) => void;
  onOpenSettings: () => void;
  onLogout: () => void;
  agents: AgentConfig[];
  currentUser: AppUser | null;
  canViewUsers: boolean;
  canViewSettings: boolean;
  newUI: boolean;
  onToggleNewUI: () => void;
}

export default function NavBar({ currentView, onNavigate, onOpenSettings, onLogout, agents, currentUser, canViewUsers, canViewSettings, newUI, onToggleNewUI }: NavBarProps) {
  const [agentsOpen, setAgentsOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const agentsRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (agentsRef.current && !agentsRef.current.contains(e.target as Node)) setAgentsOpen(false);
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserMenuOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const isAgentView = currentView.startsWith('agent-');
  const p0 = agents.filter((a) => a.phase === 'P0');
  const p1 = agents.filter((a) => a.phase === 'P1');
  const p2 = agents.filter((a) => a.phase === 'P2');

  const initials = currentUser
    ? currentUser.name.split(' ').map((n) => n[0]).join('').toUpperCase()
    : '??';

  const roleLabel = currentUser?.role === 'super_admin' ? 'Platform Admin'
    : currentUser?.role === 'admin' ? 'Admin'
    : currentUser?.role === 'manager' ? 'Manager'
    : 'Viewer';

  const statusDot = (status: AgentConfig['status']) => {
    const colors = { active: '#10b981', beta: '#f59e0b', 'coming-soon': '#64748b' };
    return <span style={{ width: 8, height: 8, borderRadius: '50%', background: colors[status], display: 'inline-block', flexShrink: 0, boxShadow: status === 'active' ? '0 0 8px #10b981' : 'none' }} />;
  };

  const statusLabel = (status: AgentConfig['status']) => {
    const map = { active: 'Active', beta: 'Beta', 'coming-soon': 'Coming Soon' };
    const colors = { active: '#065f46', beta: '#92400e', 'coming-soon': '#64748b' };
    const bgs = { active: '#dcfce7', beta: '#fef3c7', 'coming-soon': '#f1f5f9' };
    return <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: bgs[status], color: colors[status], textTransform: 'uppercase' as const, letterSpacing: '.3px' }}>{map[status]}</span>;
  };

  return (
    <nav className="app-navbar">
      <div className="nav-left">
        <div className="nav-brand" onClick={() => onNavigate('command-center')} style={{ cursor: 'pointer' }}>
          <div className="nav-logo" style={{ background: 'linear-gradient(135deg, #2dd4bf, #818cf8)', boxShadow: '0 0 20px rgba(45, 212, 191, 0.3)' }}>
            <Bot size={22} color="#fff" />
          </div>
          <span className="nav-brand-text" style={{ fontSize: '18px', letterSpacing: '-0.5px' }}>
            Staffing<span style={{ color: '#2dd4bf' }}>Agent</span>
          </span>
        </div>

        <div className="nav-links">
          <button
            className={`nav-link ${currentView === 'command-center' ? 'active' : ''}`}
            onClick={() => onNavigate('command-center')}
          >
            <Home size={16} />
            Command Center
          </button>

          <button
            className={`nav-link ${currentView === 'dashboard' || currentView === 'timeops' || currentView === 'riskops' ? 'active' : ''}`}
            onClick={() => onNavigate('dashboard')}
          >
            <LayoutDashboard size={16} />
            Dashboard
          </button>

          <button
            className={`nav-link ${currentView === 'alert-queue' ? 'active' : ''}`}
            onClick={() => onNavigate('alert-queue')}
          >
            <AlertTriangle size={16} />
            Alert Queue
          </button>

          {canViewSettings && (
            <button
              className={`nav-link ${currentView === 'agent-settings' ? 'active' : ''}`}
              onClick={() => onNavigate('agent-settings')}
            >
              <Bot size={16} />
              Agent Settings
            </button>
          )}

          <div className="nav-dropdown" ref={agentsRef}>
            <button
              className={`nav-link ${isAgentView ? 'active' : ''}`}
              onClick={() => setAgentsOpen(!agentsOpen)}
            >
              <Bot size={16} />
              Agents
              <ChevronDown size={14} style={{ transform: agentsOpen ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }} />
            </button>

            {agentsOpen && (
              <div className="nav-dropdown-panel">
                <div className="nav-dropdown-section">
                  <div className="nav-dropdown-label">Phase 0 — Core Agents</div>
                  {p0.map((a) => (
                    <button key={a.id} className={`nav-dropdown-item ${currentView === a.viewId ? 'active' : ''}`} onClick={() => { onNavigate(a.viewId); setAgentsOpen(false); }}>
                      <span style={{ fontSize: 16 }}>{a.icon}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 700, fontSize: 13 }}>{a.name}</div>
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 1 }}>{a.description}</div>
                      </div>
                      {statusDot(a.status)}
                    </button>
                  ))}
                </div>
                <div className="nav-dropdown-section">
                  <div className="nav-dropdown-label">Phase 1 — Advanced Agents</div>
                  {p1.map((a) => (
                    <button key={a.id} className={`nav-dropdown-item ${currentView === a.viewId ? 'active' : ''}`} onClick={() => { onNavigate(a.viewId); setAgentsOpen(false); }}>
                      <span style={{ fontSize: 16 }}>{a.icon}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 700, fontSize: 13 }}>{a.name}</div>
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 1 }}>{a.description}</div>
                      </div>
                      {statusLabel(a.status)}
                    </button>
                  ))}
                </div>
                <div className="nav-dropdown-section">
                  <div className="nav-dropdown-label">Phase 2 — Specialized</div>
                  {p2.map((a) => (
                    <button key={a.id} className={`nav-dropdown-item ${currentView === a.viewId ? 'active' : ''}`} onClick={() => { onNavigate(a.viewId); setAgentsOpen(false); }}>
                      <span style={{ fontSize: 16 }}>{a.icon}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 700, fontSize: 13 }}>{a.name}</div>
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 1 }}>{a.description}</div>
                      </div>
                      {statusLabel(a.status)}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="nav-right">
        {currentUser?.role === 'super_admin' && (
          <button className={`nav-link ${currentView === 'client-management' ? 'active' : ''}`} onClick={() => onNavigate('client-management')}>
            <Building2 size={16} />
            <span className="nav-link-label">Clients</span>
          </button>
        )}

        {canViewUsers && (
          <button className={`nav-link ${currentView === 'user-management' ? 'active' : ''}`} onClick={() => onNavigate('user-management')}>
            <Users size={16} />
            <span className="nav-link-label">Users</span>
          </button>
        )}

        {canViewSettings && (
          <button className="nav-link" onClick={onOpenSettings}>
            <Settings size={16} />
            <span className="nav-link-label">Admin</span>
          </button>
        )}

        <button
          className="nav-ui-toggle"
          onClick={onToggleNewUI}
          title={newUI ? 'Switch back to classic UI' : 'Try the new UI'}
        >
          {newUI ? 'Classic UI' : 'New UI'}
          <span className="nav-ui-badge">BETA</span>
        </button>

        <div className="nav-dropdown" ref={userRef}>
          <button className="nav-avatar" onClick={() => setUserMenuOpen(!userMenuOpen)}>
            {initials}
          </button>
          {userMenuOpen && (
            <div className="nav-dropdown-panel nav-user-panel">
              <div style={{ padding: '12px 16px', borderBottom: '1px solid #e2e8f0' }}>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{currentUser?.name || 'Unknown'}</div>
                <div style={{ fontSize: 12, color: '#64748b' }}>{currentUser?.email || ''}</div>
                <div style={{ fontSize: 11, color: '#2563eb', fontWeight: 600, marginTop: 4 }}>{roleLabel}</div>
              </div>
              <button className="nav-dropdown-item" onClick={() => { setUserMenuOpen(false); }} style={{ borderRadius: 0 }}>
                <User size={14} /> Profile Settings
              </button>
              <button className="nav-dropdown-item" onClick={() => { setUserMenuOpen(false); onLogout(); }} style={{ borderRadius: 0, color: '#dc2626' }}>
                <LogOut size={14} /> Sign Out
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
