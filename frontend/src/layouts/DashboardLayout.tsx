import type { ReactNode } from 'react'
import Navbar from '../components/Navbar'
import type { MonitoringStatus } from '../services/api'

interface DashboardLayoutProps {
  sessionState: MonitoringStatus
  onPause: () => void
  onResume: () => void
  onStop: () => void
  children: ReactNode
}

export default function DashboardLayout({ sessionState, onPause, onResume, onStop, children }: DashboardLayoutProps) {
  return <div className="app-shell"><Navbar dashboard sessionState={sessionState} onPause={onPause} onResume={onResume} onStop={onStop} />{children}</div>
}
