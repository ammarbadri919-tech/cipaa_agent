import { Activity, Shield } from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'
import type { MonitoringStatus } from '../services/api'

interface NavbarProps {
  dashboard?: boolean
  sessionState?: MonitoringStatus
  onPause?: () => void
  onResume?: () => void
  onStop?: () => void
}

export default function Navbar({ dashboard = false, sessionState = 'idle', onPause, onResume, onStop }: NavbarProps) {
  const canStop = ['starting', 'running', 'paused', 'error'].includes(sessionState)
  return <header className="topbar">
    <Link to="/" className="brand" aria-label="CryptoGuardian upload page"><span className="brand-mark"><Shield size={17} strokeWidth={1.8} /></span><span>CryptoGuardian<small>INTELLIGENCE TERMINAL</small></span></Link>
    <nav className="terminal-nav" aria-label="Main navigation">
      <NavLink to="/dashboard" className={({ isActive }) => isActive ? 'nav-link selected' : 'nav-link'}>Dashboard</NavLink>
      <NavLink to="/" className={({ isActive }) => isActive ? 'nav-link selected' : 'nav-link'}>Upload CSV</NavLink>
      <a href={dashboard ? '#session-history' : '/dashboard#session-history'} className="nav-link">Session History</a>
    </nav>
    <div className="top-actions">
      {dashboard ? <>
        <span className={`status-pill backend-status ${sessionState}`} title="Monitoring state reported by the FastAPI process."><span className={`status-dot ${sessionState === 'running' ? 'green' : ''}`} />{sessionState.toUpperCase()}</span>
        {sessionState === 'running' && <button className="btn control-btn" onClick={onPause}>Pause</button>}
        {sessionState === 'paused' && <button className="btn control-btn btn-primary" onClick={onResume}>Resume</button>}
        <button className="btn control-btn stop-btn" disabled={!canStop} onClick={onStop}>Stop</button>
      </> : <><span className="status-pill"><span className="status-dot" />SYSTEM STANDBY</span><span className="tag"><Activity size={12} /> WATCHLIST SETUP</span></>}
    </div>
  </header>
}
