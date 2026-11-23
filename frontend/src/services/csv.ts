import type { Coin } from './api'

export interface CsvValidationResult {
  coins: Coin[]
  duplicateSymbols: string[]
  skippedRows: number
}

function parseRow(line: string): string[] {
  const values: string[] = []
  let value = ''
  let quoted = false
  for (let index = 0; index < line.length; index++) {
    const char = line[index]
    if (char === '"' && line[index + 1] === '"' && quoted) {
      value += '"'
      index++
    } else if (char === '"') {
      quoted = !quoted
    } else if (char === ',' && !quoted) {
      values.push(value.trim())
      value = ''
    } else {
      value += char
    }
  }
  if (quoted) throw new Error('A quoted value is missing its closing quote.')
  values.push(value.trim())
  return values
}

export function parseCoinCsv(text: string): CsvValidationResult {
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/).filter(line => line.trim())
  if (lines.length < 2) throw new Error('Add a header row and at least one coin to your CSV.')

  const headers = parseRow(lines[0]).map(header => header.toLowerCase())
  const nameIndex = headers.indexOf('coin_name')
  const symbolIndex = headers.indexOf('symbol')
  if (nameIndex < 0 || symbolIndex < 0) throw new Error('Required columns are coin_name and symbol.')

  const coins: Coin[] = []
  const seen = new Set<string>()
  const duplicateSymbols: string[] = []
  let skippedRows = 0

  for (const line of lines.slice(1)) {
    const row = parseRow(line)
    const coin_name = row[nameIndex]?.trim()
    const symbol = row[symbolIndex]?.trim().toUpperCase()
    if (!coin_name || !symbol || !/^[A-Z0-9][A-Z0-9._/-]{0,19}$/.test(symbol)) {
      skippedRows++
      continue
    }
    const key = symbol.replaceAll('/', '')
    if (seen.has(key)) {
      duplicateSymbols.push(symbol)
      continue
    }
    seen.add(key)
    coins.push({ coin_name, symbol })
  }

  if (!coins.length) throw new Error('No valid coin rows found. Add a coin name and a valid symbol for at least one coin.')
  return { coins, duplicateSymbols, skippedRows }
}
