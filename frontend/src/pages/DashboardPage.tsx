import { useCallback, useEffect, useMemo, useState } from 'react'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { Navigate } from 'react-router-dom'
import DecisionPanel from '../components/DecisionPanel'
import MarketScanner from '../components/MarketScanner'
import MultiCoinChartGrid from '../components/MultiCoinChartGrid'
import NewsPanel from '../components/NewsPanel'
import SessionHistory from '../components/SessionHistory'
import DashboardLayout from '../layouts/DashboardLayout'
import { controlMonitoring, getDashboard, getDashboardWebSocketUrl, readWatchlist, type Coin, type DashboardSnapshot, type MonitoringStatus } from '../services/api'
import '../App.css'

function formatDuration(startedAt: string | undefined, now: number): string {
  if (!startedAt || !now) return '—'
  const seconds = Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000))
  if (!Number.isFinite(seconds)) return '—'
  return `${String(Math.floor(seconds / 3600)).padStart(2, '0')}:${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}

export default function DashboardPage() {
  const fallbackCoins = useMemo(() => readWatchlist(), [])
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null)
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'offline'>('connecting')
  const [hasLoaded, setHasLoaded] = useState(false)
  const [controlError, setControlError] = useState('')
  const [controlBusy, setControlBusy] = useState(false)
  const [now, setNow] = useState(0)

  const updateSnapshot = useCallback((next: DashboardSnapshot) => {
    setSnapshot(next)
    setConnection('connected')
    setHasLoaded(true)
  }, [])

  const refresh = useCallback(async () => {
    try {
      updateSnapshot(await getDashboard())
    } catch {
      setConnection('offline')
      setHasLoaded(true)
    }
  }, [updateSnapshot])

  useEffect(() => {
    let disposed = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    const connect = () => {
      if (disposed) return
      try {
        socket = new WebSocket(getDashboardWebSocketUrl())
        socket.onopen = () => { if (!disposed) setConnection('connected') }
        socket.onmessage = event => {
          try { updateSnapshot(JSON.parse(String(event.data)) as DashboardSnapshot) } catch { /* ignore malformed frames */ }
        }
        socket.onerror = () => socket?.close()
        socket.onclose = () => {
          if (disposed) return
          setConnection(current => current === 'connected' ? 'offline' : current)
          reconnectTimer = window.setTimeout(connect, 2500)
        }
      } catch {
        setConnection('offline')
        reconnectTimer = window.setTimeout(connect, 2500)
      }
    }
    const initialRefresh = window.setTimeout(() => { void refresh() }, 0)
    connect()
    const poll = window.setInterval(() => { void refresh() }, 8000)
    const clock = window.setInterval(() => setNow(Date.now()), 1000)
    return () => {
      disposed = true
      window.clearInterval(poll)
      window.clearInterval(clock)
      window.clearTimeout(initialRefresh)
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [refresh, updateSnapshot])

  const session = snapshot?.session ?? null
  const sessionState: MonitoringStatus = session?.status ?? 'idle'
  const coins: Coin[] = snapshot?.coins?.length ? snapshot.coins : fallbackCoins
  const marketItems = snapshot?.market ?? coins.map(coin => ({ coin_name: coin.coin_name, symbol: coin.symbol }))

  async function act(action: 'pause' | 'resume' | 'stop') {
    if (controlBusy) return
    setControlBusy(true)
    setControlError('')
    try {
      await controlMonitoring(action)
      await refresh()
    } catch (error) {
      setControlError(error instanceof Error ? error.message : `Could not ${action} monitoring.`)
    } finally {
      setControlBusy(false)
    }
  }

  if (hasLoaded && !session && !fallbackCoins.length) return <Navigate to="/" replace />
  if (!hasLoaded && !fallbackCoins.length) return <div className="app-shell dashboard-loading"><div className="empty-title"><RefreshCw size={15} className="spin-icon" /> Connecting to CryptoGuardian API…</div></div>

  const apiAgentStatus = connection === 'connected' ? 'connected' : 'offline'
  return <DashboardLayout sessionState={sessionState} onPause={() => void act('pause')} onResume={() => void act('resume')} onStop={() => void act('stop')}>
    <main className="dash-main">
      <div className="dash-heading"><div><h1>Monitoring dashboard</h1><p>{coins.length} selected {coins.length === 1 ? 'asset' : 'assets'} <span className="meta-separator">·</span> Session duration {formatDuration(session?.started_at, now)}</p></div><div className="dashboard-status"><span className={`status-pill ${connection === 'connected' ? 'api-connected' : 'api-offline'}`}><span className={`status-dot ${connection === 'connected' ? 'green' : ''}`} />API {apiAgentStatus.toUpperCase()}</span><button className="btn control-btn" title="Refresh dashboard" onClick={() => void refresh()}><RefreshCw size={12} /></button>{controlBusy && <span className="last-update">Sending control…</span>}</div></div>
      {!session && <div className="error-box dashboard-error">No active backend session is available. Showing the last browser watchlist without live agent data.</div>}
      {session?.error && <div className="error-box dashboard-error" role="alert">{session.error}</div>}
      {controlError && <div className="error-box dashboard-error" role="alert">{controlError}</div>}
      <div className="dash-grid">
        <DecisionPanel coins={coins} results={snapshot?.patterns ?? []} agent={snapshot?.agents.pattern_decision} />
        <section className="column center-column"><MultiCoinChartGrid coins={coins} market={marketItems} refreshEnabled={sessionState === 'running'} /><div className="footer-note chart-source-note">Each chart has its own color, coin label, current price, and 24h change.</div></section>
        <section className="column right-column"><NewsPanel coins={coins} items={snapshot?.news.items ?? []} agent={snapshot?.agents.news_agent} /><div className="backend-note"><ExternalLink size={11} /> Headlines are read from the existing PostgreSQL news tables.</div></section>
      </div>
      <SessionHistory events={session?.events ?? []} />
      <MarketScanner items={marketItems} agent={snapshot?.agents.market_scanner} />
      <div className="dashboard-disclaimer">Agent statuses and results are reported by FastAPI; empty values mean the source has not published data.</div>
    </main>
  </DashboardLayout>
}
