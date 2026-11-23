import { useEffect, useState, type CSSProperties } from 'react'
import { ChartCandlestick, RefreshCw } from 'lucide-react'
import { getChartUrl, type Coin, type MarketResult } from '../services/api'

const knownAccents: Record<string, string> = {
  BTC: '#f7931a',
  ETH: '#9a8cff',
  SOL: '#59d3b0',
  BNB: '#f0b90b',
  XRP: '#55b8e8',
}

function accentFor(symbol: string): string {
  const base = symbol.trim().toUpperCase().split(/[\/-]/)[0].replace(/(?:USDT|USDC|USD)$/, '')
  if (knownAccents[base]) return knownAccents[base]
  const hue = [...base].reduce((value, letter) => (value * 31 + letter.charCodeAt(0)) % 360, 7)
  return `hsl(${hue} 68% 62%)`
}

function priceText(market?: MarketResult): string {
  if (typeof market?.current_price !== 'number' || !Number.isFinite(market.current_price)) return 'Price unavailable'
  const price = new Intl.NumberFormat(undefined, { maximumFractionDigits: 8 }).format(market.current_price)
  return `${price} ${market.quote_currency ?? ''}`.trim()
}

function changeText(value?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '24h —'
  return `24h ${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function ChartCard({ coin, market, refreshKey }: { coin: Coin; market?: MarketResult; refreshKey: number }) {
  const [failedForKey, setFailedForKey] = useState<number | null>(null)
  const failed = failedForKey === refreshKey
  const url = `${getChartUrl(coin.symbol)}?v=${refreshKey}`
  return <article className="chart-card" style={{ '--coin-accent': accentFor(coin.symbol) } as CSSProperties}><div className="chart-card-head"><div className="chart-identity"><span className="chart-accent-mark" /><div className="chart-identity-text"><strong>{coin.coin_name}</strong><span className="chart-symbol">{coin.symbol}</span></div></div><div className="chart-market-value"><strong>{priceText(market)}</strong><span className={typeof market?.change_24h_pct === 'number' && market.change_24h_pct >= 0 ? 'chart-change positive' : 'chart-change'}>{changeText(market?.change_24h_pct)}</span></div><span className="chart-time">15M · IST</span></div>{failed ? <div className="chart-unavailable"><div><ChartCandlestick size={21} /><div>{coin.coin_name} chart unavailable</div><div style={{ color: '#4f5d65', marginTop: 4 }}>Waiting for generated chart from backend</div></div></div> : <img className="chart-image" src={url} alt={`${coin.coin_name} (${coin.symbol}) generated market chart`} onError={() => setFailedForKey(refreshKey)} />}<div className="chart-note">{coin.symbol} · Existing Python chart · refreshes every 30 seconds</div></article>
}

export default function MultiCoinChartGrid({ coins, market, refreshEnabled }: { coins: Coin[]; market: MarketResult[]; refreshEnabled: boolean }) {
  const [refreshKey, setRefreshKey] = useState(() => Date.now())
  const marketBySymbol = new Map(market.map(item => [item.symbol, item]))
  useEffect(() => {
    if (!refreshEnabled) return
    const timer = window.setInterval(() => setRefreshKey(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [refreshEnabled])
  return <section className="panel dash-panel"><div className="panel-head"><div className="panel-title"><ChartCandlestick className="icon" size={15} /> Generated charts <span className="tag" style={{ padding: '3px 7px' }}>{coins.length}</span></div><div className="chart-toolbar"><RefreshCw size={11} className="refresh-indicator" /><span className="section-caption">15 MIN</span></div></div><div className="chart-grid">{coins.map(coin => <ChartCard key={coin.symbol} coin={coin} market={marketBySymbol.get(coin.symbol)} refreshKey={refreshKey} />)}</div></section>
}
