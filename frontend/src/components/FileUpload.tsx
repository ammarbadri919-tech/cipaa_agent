import { useRef, useState } from 'react'
import { FileUp, UploadCloud } from 'lucide-react'
import type { CsvValidationResult } from '../services/csv'

interface FileUploadProps {
  onLoaded: (fileName: string, result: CsvValidationResult, file: File) => void
  onError: (message: string) => void
}

export default function FileUpload({ onLoaded, onError }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  async function handleFile(file?: File) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      onError('Choose a .csv file to continue.')
      return
    }
    try {
      const { parseCoinCsv } = await import('../services/csv')
      onLoaded(file.name, parseCoinCsv(await file.text()), file)
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Could not read this CSV file.')
    } finally {
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return <>
    <div className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); void handleFile(event.dataTransfer.files[0]) }}>
      <div><span className="upload-icon"><UploadCloud size={21} /></span><div className="drop-title">Drop your coin list here</div><div className="drop-sub">or choose a file from your device</div><button type="button" className="btn" style={{ marginTop: 17 }} onClick={() => inputRef.current?.click()}><FileUp size={13} style={{ verticalAlign: 'middle', marginRight: 7 }} />Browse CSV</button><input ref={inputRef} type="file" accept=".csv,text/csv" hidden onChange={event => void handleFile(event.target.files?.[0])} /></div>
    </div>
    <div className="format-row"><span>Required columns</span><code>coin_name, symbol</code></div>
  </>
}
