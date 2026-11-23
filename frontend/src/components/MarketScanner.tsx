import { ScanLine, TrendingUp } from 'lucide-react'
import type { AgentState, MarketResult } from '../services/api'

function numeric(value: number | null | undefined, maxDecimals = 8): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: maxDecimals }).format(value)
}

function signedPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function forecastText(item: MarketResult): string {
  const forecasts = item.forecasts ?? {}
  const horizon = ['15m', '30m', '1h', '12h', '24h'].find(key => forecasts[key]?.predicted_price != null)
  if (!horizon) return '—'
  const forecast = forecasts[horizon]
  return `${horizon}: ${numeric(forecast?.predicted_price)} ${item.quote_currency ?? ''} (${signedPercent(forecast?.predicted_pct)})`
}

export default function MarketScanner({ items, agent }: { items: MarketResult[]; agent?: AgentState }) {
  return <section className="panel dash-panel market-scanner"><div className="panel-head"><div className="panel-title"><ScanLine className="icon" size={15} /> Market scanner</div><span className={`tag agent-tag ${agent?.status ?? 'idle'}`}><span className={`status-dot ${agent?.status === 'running' ? 'green' : ''}`} />{agent?.status?.toUpperCase() ?? 'IDLE'}</span></div><div className="market-table-wrap"><table className="market-table"><thead><tr><th>#</th><th>Symbol</th><th>Price</th><th>24H Change</th><th>24H Volume</th><th>Market Trend</th><th><span className="forecast-label"><TrendingUp size={11} /> Kronos Forecast</span></th></tr></thead><tbody>{items.map((item, index) => <tr key={item.symbol}><td className="row-number">{index + 1}</td><td><span className="market-name">{item.symbol}</span></td><td>{item.current_price == null ? '—' : `${numeric(item.current_price)} ${item.quote_currency ?? ''}`}</td><td>{signedPercent(item.change_24h_pct)}</td><td>{item.volume_24h == null ? '—' : `${numeric(item.volume_24h, 2)} ${item.quote_currency ?? ''}`}</td><td><span className={item.market_trend ? 'trend-value' : 'unavailable-label'} title={item.change_1h_pct == null ? undefined : `1h change ${signedPercent(item.change_1h_pct)}`}>{item.market_trend ?? 'Unavailable'}</span></td><td><span className={item.forecasts && Object.keys(item.forecasts).length ? 'forecast-value' : 'unavailable-label'}>{forecastText(item)}</span></td></tr>)}</tbody></table>{!items.length && <div className="scanner-empty">Market scanner has not published a result for this session yet.</div>}</div><div className="scanner-footnote">Prices and forecasts come from the existing Kraken scanner and Kronos outputs. Missing values remain unavailable.</div></section>
}
