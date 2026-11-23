export interface Coin {
  coin_name: string
  symbol: string
}

export type MonitoringStatus = 'idle' | 'starting' | 'running' | 'paused' | 'stopping' | 'stopped' | 'error'
export type AgentProcessStatus = 'idle' | 'starting' | 'running' | 'paused' | 'stopped' | 'error'

export interface SessionEvent {
  timestamp: string
  action: 'started' | 'paused' | 'resumed' | 'stopped'
  coin_count: number
}

export interface AgentState {
  status: AgentProcessStatus
  detail?: string
  pid?: number | null
  last_update?: string | null
  has_current_result?: boolean
  data_status?: string
  sources?: Record<string, SourceState>
}

export interface SourceState {
  status: string
  updated_at?: string
  error_type?: string
}

export interface AnalysisPosition {
  symbol: string
  direction: string
  entry_price?: number | null
  timeframe?: string
  opened_at?: string
}

export interface MonitoringSession {
  id: string
  status: MonitoringStatus
  started_at: string
  updated_at: string
  error?: string | null
  coins: Coin[]
  agents: Record<string, AgentState>
  events: SessionEvent[]
}

export interface MarketResult {
  coin_name: string
  symbol: string
  source_symbol?: string
  current_price?: number | null
  quote_currency?: string | null
  change_5m_pct?: number | null
  change_1h_pct?: number | null
  change_24h_pct?: number | null
  volume_24h?: number | null
  market_trend?: string | null
  updated_at?: string | null
  forecasts?: Record<string, { predicted_price?: number | null; predicted_pct?: number | null } | null>
}

export interface NewsItem {
  id: number
  source?: string | null
  headline: string
  url: string
  published_at?: string | null
  fetched_at?: string | null
  description?: string | null
  coin_name: string
  symbol: string
}

export interface NewsResult {
  status: 'connected' | 'idle' | 'error'
  error_type?: string
  items: NewsItem[]
}

export interface PatternHistoryItem {
  timestamp?: string | null
  decision?: string | null
  confidence?: number | null
  reason?: string | null
}

export interface PatternResult {
  coin_name: string
  symbol: string
  timeframe?: string | null
  timestamp?: string | null
  is_current: boolean
  decision?: string | null
  confidence?: number | null
  reason?: string | null
  current_patterns: Array<Record<string, unknown>>
  tracked_patterns: Array<Record<string, unknown>>
  market_snapshot?: Record<string, unknown> | null
  position?: AnalysisPosition | null
  history: PatternHistoryItem[]
}

export interface DashboardSnapshot {
  session: MonitoringSession | null
  coins: Coin[]
  agents: Record<string, AgentState>
  market: MarketResult[]
  news: NewsResult
  patterns: PatternResult[]
  server_time: string
}

export interface StartMonitoringResponse {
  session: MonitoringSession
  coins: Coin[]
}

const apiBase = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, init)
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json() as { detail?: string }
      if (payload.detail) message = payload.detail
    } catch { /* keep HTTP status */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export function getChartUrl(symbol: string): string {
  const normalized = symbol.trim().toUpperCase()
  const base = normalized.includes('/') ? normalized.split('/')[0] : normalized.replace(/(?:USDT|USDC|USD)$/, '')
  const filename = `${base}_USDT`
  return `${apiBase}/charts/${encodeURIComponent(filename)}.png`
}

export function readWatchlist(): Coin[] {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem('cryptoguardian.watchlist') ?? '[]')
    if (!Array.isArray(value)) return []
    return value.filter((coin): coin is Coin => typeof coin?.coin_name === 'string' && typeof coin?.symbol === 'string')
  } catch {
    return []
  }
}

export function saveWatchlist(coins: Coin[]): void {
  sessionStorage.setItem('cryptoguardian.watchlist', JSON.stringify(coins))
}

export async function startMonitoring(file: File): Promise<StartMonitoringResponse> {
  const form = new FormData()
  form.set('file', file)
  return request<StartMonitoringResponse>('/api/monitoring/start', { method: 'POST', body: form })
}

export async function getDashboard(): Promise<DashboardSnapshot> {
  return request<DashboardSnapshot>('/api/dashboard')
}

export async function getMonitoringStatus(): Promise<{ session: MonitoringSession | null }> {
  return request('/api/monitoring/status')
}

export async function controlMonitoring(action: 'pause' | 'resume' | 'stop'): Promise<{ session: MonitoringSession | null }> {
  return request(`/api/monitoring/${action}`, { method: 'POST' })
}

export function getDashboardWebSocketUrl(): string {
  const url = new URL(`${apiBase}/api/ws`)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}
