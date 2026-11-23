import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Check, FileSpreadsheet, LockKeyhole, Radio, ShieldCheck, X } from 'lucide-react'
import Navbar from '../components/Navbar'
import FileUpload from '../components/FileUpload'
import { saveWatchlist, startMonitoring, type Coin } from '../services/api'
import type { CsvValidationResult } from '../services/csv'
import '../App.css'

export default function UploadPage() {
  const [coins, setCoins] = useState<Coin[]>([])
  const [fileName, setFileName] = useState('')
  const [duplicates, setDuplicates] = useState<string[]>([])
  const [skippedRows, setSkippedRows] = useState(0)
  const [error, setError] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [starting, setStarting] = useState(false)
  const navigate = useNavigate()

  function loaded(name: string, result: CsvValidationResult, file: File) {
    setFileName(name)
    setSelectedFile(file)
    setCoins(result.coins)
    setDuplicates(result.duplicateSymbols)
    setSkippedRows(result.skippedRows)
    setError('')
  }
  function clear() {
    sessionStorage.removeItem('cryptoguardian.watchlist')
    setFileName('')
    setSelectedFile(null)
    setCoins([])
    setDuplicates([])
    setSkippedRows(0)
    setError('')
  }
  async function start() {
    if (!coins.length || !selectedFile || starting) return
    setStarting(true)
    setError('')
    try {
      const response = await startMonitoring(selectedFile)
      saveWatchlist(response.coins)
      navigate('/dashboard')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not start the monitoring session.')
    } finally {
      setStarting(false)
    }
  }

  return <div className="app-shell"><Navbar /><main className="page-wrap">
      <div className="eyebrow">MARKET SURVEILLANCE / 01</div><h1 className="page-title">Configure your watchlist</h1><p className="subhead">Import the assets you want CryptoGuardian to monitor. After review, the API passes your watchlist to the existing agent workflow.</p>
    <div className="upload-layout"><section className="panel"><div className="panel-head"><div className="panel-title"><FileSpreadsheet size={15} color="#62cbb9" /> Watchlist source</div><span className="section-caption">CSV IMPORT</span></div><div className="panel-body">
      <FileUpload onLoaded={loaded} onError={message => { clear(); setError(message) }} />{error && <div className="error-box" role="alert">{error}</div>}
      {fileName && <div className="file-controls"><span>Loaded <strong>{fileName}</strong></span><button className="text-button" onClick={clear}><X size={12} /> Remove list</button></div>}
      {duplicates.length > 0 && <div className="warning-box" role="status">Duplicate symbols removed: {duplicates.join(', ')}</div>}
      {skippedRows > 0 && <div className="warning-box" role="status">{skippedRows} invalid {skippedRows === 1 ? 'row was' : 'rows were'} skipped. Add a coin name and valid symbol to include them.</div>}
      {coins.length > 0 && <><div className="preview-heading"><span className="panel-title">Selected assets</span><span className="tag"><Check size={11} /> {coins.length} VALID</span></div><div className="coin-preview"><table className="coin-table"><thead><tr><th>Asset</th><th>Symbol</th><th>State</th></tr></thead><tbody>{coins.map(coin => <tr key={coin.symbol}><td><span className="coin-name"><span className="coin-icon">{coin.symbol.slice(0, 2)}</span>{coin.coin_name}</span></td><td><span className="symbol-chip">{coin.symbol}</span></td><td className="valid-cell">Ready</td></tr>)}</tbody></table></div></>}
      <div className="upload-footer"><span className="help-line">{starting ? 'Starting existing agent services…' : `${coins.length} unique valid ${coins.length === 1 ? 'asset' : 'assets'}`}</span><button className="btn btn-primary" disabled={!coins.length || !selectedFile || starting} onClick={() => void start()}>{starting ? 'Starting…' : 'Start Monitoring'} <ArrowRight size={14} style={{ verticalAlign: 'middle', marginLeft: 8 }} /></button></div>
    </div></section>
    <aside className="right-stack"><section className="panel info-card"><div className="info-head"><ShieldCheck size={15} color="#63cdb9" /> Watchlist validation</div><div className="info-copy">Rows require a coin name and symbol. Duplicate symbols are reported and removed so each asset appears once in the dashboard.</div><div className="summary-row"><span className="summary-label">Valid assets</span><span className="summary-value">{coins.length}</span></div><div className="summary-row" style={{ marginTop: -1 }}><span className="summary-label">File status</span><span className="summary-value" style={{ color: coins.length ? '#70d5b4' : '#859098' }}>{coins.length ? 'Validated' : 'Awaiting file'}</span></div></section>
      <section className="panel info-card"><div className="info-head"><Radio size={15} color="#63cdb9" /> Monitoring workflow</div><div className="steps"><div className="step"><span className="step-num">01</span><div><strong>Import watchlist</strong><span>Use coin_name and symbol columns in your CSV.</span></div></div><div className="step"><span className="step-num">02</span><div><strong>Review assets</strong><span>Confirm the valid unique symbols in your list.</span></div></div><div className="step"><span className="step-num">03</span><div><strong>Open the terminal</strong><span>Backend results remain offline until the API is connected.</span></div></div></div></section>
      <div className="footer-note" style={{ display: 'flex', gap: 7, alignItems: 'center', padding: '0 4px' }}><LockKeyhole size={12} /> Watchlist stays in this browser session.</div>
    </aside></div>
  </main></div>
}
