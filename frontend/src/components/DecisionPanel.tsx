import { Activity, BrainCircuit, Clock3 } from 'lucide-react'
import type { AgentState, Coin, PatternResult } from '../services/api'

function formatTime(value?: string | null): string {
  if (!value) return 'Timestamp unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Timestamp unavailable' : date.toLocaleString()
}

function confidenceText(value?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  const percentage = value <= 1 ? value * 100 : value
  return `${percentage.toFixed(1)}%`
}

function priceText(value?: number | null): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 8 }).format(value)
    : 'price unavailable'
}

export default function DecisionPanel({ coins, results, agent }: { coins: Coin[]; results: PatternResult[]; agent?: AgentState }) {
  const bySymbol = new Map(results.map(result => [result.symbol, result]))
  const history = results.flatMap(result => result.history.map(item => ({ ...item, symbol: result.symbol }))).sort((a, b) => (b.timestamp ?? '').localeCompare(a.timestamp ?? '')).slice(0, 8)
  return <section className="column"><div className="panel dash-panel"><div className="panel-head"><div className="panel-title"><BrainCircuit className="icon" size={15} /> Pattern decision agent</div><span className={`tag agent-tag ${agent?.status ?? 'idle'}`}><span className={`status-dot ${agent?.status === 'running' ? 'green' : ''}`} />{agent?.status?.toUpperCase() ?? 'IDLE'}</span></div><div className="decision-list">{coins.map(coin => {
    const result = bySymbol.get(coin.symbol)
    const decision = result?.decision?.toUpperCase()
    const patterns = result?.current_patterns ?? []
    return <article className="decision-card" key={coin.symbol}><div className="decision-top"><span>{coin.coin_name} · <span className="decision-symbol">{coin.symbol}</span></span><span className={`decision-badge ${decision?.toLowerCase() ?? 'waiting'}`}>{decision || 'WAITING'}</span></div>{result ? <><div className="decision-label">{decision && decision !== 'UNAVAILABLE' ? decision : 'Decision unavailable'}</div><div className="decision-meta"><span>Confidence <strong>{confidenceText(result.confidence)}</strong></span><span>{result.timeframe || 'Timeframe unavailable'}</span></div>{result.reason && <div className="reasoning">{result.reason}</div>}{patterns.length > 0 && <div className="detected-patterns"><span className="section-caption">CURRENT PATTERNS</span>{patterns.slice(0, 3).map((pattern, index) => <div className="detected-pattern" key={`${String(pattern.name ?? 'pattern')}-${index}`}><span>{String(pattern.name ?? 'Unnamed pattern')}</span><small>{String(pattern.formation_state ?? pattern.status ?? 'Status unavailable')}</small></div>)}</div>}{result.position && <div className="decision-time">Analysis position open · {result.position.direction} · Entry {priceText(result.position.entry_price)}</div>}{decision === 'EXIT' && <div className="decision-time">Exit recommendation · analysis position closed; no exchange order was placed</div>}<div className="decision-time">{result.is_current ? 'Current session result' : 'Stored report'} · {formatTime(result.timestamp)}</div></> : <div className="reasoning">No pattern report is available for this coin yet.</div>}</article>
  })}</div><div className="pattern-agent-note">ENTER opens a persisted analysis position; later scans may recommend EXIT and close that tracked position. These are recommendations only and never place exchange orders.</div></div><div className="panel dash-panel"><div className="panel-head"><div className="panel-title"><Activity className="icon" size={15} /> Decision history</div><span className="section-caption">RECENT REPORTS</span></div>{history.length ? <div className="decision-history">{history.map((item, index) => <div className="history-row" key={`${item.timestamp}-${item.symbol}-${index}`}><span><b>{item.symbol}</b> · {item.decision || 'Decision unavailable'} <small>{formatTime(item.timestamp)}</small></span><span className="history-confidence">{confidenceText(item.confidence)}</span></div>)}</div> : <div className="empty-state"><div><Clock3 className="empty-icon" size={18} /><div className="empty-title">No decision history yet</div><div className="empty-copy">Pattern reports and Gemini decisions appear after the existing 15-minute monitoring workflow writes a report.</div></div></div>}</div></section>
}
