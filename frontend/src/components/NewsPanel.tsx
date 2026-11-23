import { ExternalLink, Newspaper } from 'lucide-react'
import type { AgentState, Coin, NewsItem, SourceState } from '../services/api'

function timeLabel(value?: string | null): string {
  if (!value) return 'Published time unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Published time unavailable' : date.toLocaleString()
}

function SourceStatus({ name, source }: { name: string; source?: SourceState }) {
  const status = source?.status ?? 'waiting'
  const label = status === 'connected' ? 'Connected' : status === 'running' ? 'Collecting' : status === 'error' ? `Error${source?.error_type ? ` · ${source.error_type}` : ''}` : status === 'scheduled' ? 'Scheduled' : status === 'starting' ? 'Starting' : 'Waiting'
  const updated = source?.updated_at ? new Date(source.updated_at).toLocaleTimeString() : undefined
  return <div className="collector-status"><span>{name}</span><span className={`source-state ${status}`}>{label}{updated && <small className="source-updated">Last check {updated}</small>}</span></div>
}

export default function NewsPanel({ items, coins, agent }: { items: NewsItem[]; coins: Coin[]; agent?: AgentState }) {
  const sources = agent?.sources ?? {}
  const counts = new Map(coins.map(coin => [coin.symbol, items.filter(item => item.symbol === coin.symbol).length]))
  const emptyCopy = agent?.data_status === 'error'
    ? 'The existing PostgreSQL news lookup is unavailable. Check API database connectivity.'
    : 'Headlines appear here after the News Agent stores articles for the selected coins.'
  return <div className="panel dash-panel"><div className="panel-head"><div className="panel-title"><Newspaper className="icon" size={15} /> News agent</div><span className={`tag agent-tag ${agent?.status ?? 'idle'}`}><span className={`status-dot ${agent?.status === 'running' ? 'green' : ''}`} />{agent?.status?.toUpperCase() ?? 'IDLE'}</span></div><SourceStatus name="RSS collection" source={sources.rss} /><SourceStatus name="TinyFish collection" source={sources.tinyfish} /><div className="news-coin-coverage">{coins.map(coin => <div className="news-coin-row" key={coin.symbol}><span>{coin.coin_name} · {coin.symbol}</span><span>{counts.get(coin.symbol) ?? 0} headlines</span></div>)}</div><div className="news-feed">{items.length ? items.map(item => <article className="news-item" key={`${item.id}-${item.symbol}`}><div className="news-source">{item.source || 'Source unavailable'} · {item.symbol}</div><a className="news-title news-link" href={item.url} target="_blank" rel="noreferrer">{item.headline}<ExternalLink size={10} /></a>{item.description && <div className="news-description">{item.description}</div>}<div className="news-time">{timeLabel(item.published_at ?? item.fetched_at)}</div></article>) : <div className="news-empty"><Newspaper size={18} /><div className="empty-title">No news received</div><div className="empty-copy">{emptyCopy}</div></div>}</div></div>
}
