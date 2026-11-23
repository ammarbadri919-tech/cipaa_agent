import { Clock3, History } from 'lucide-react'
import type { SessionEvent } from '../services/api'

const actionLabels: Record<SessionEvent['action'], string> = { started: 'Monitoring started', paused: 'Monitoring paused', resumed: 'Monitoring resumed', stopped: 'Monitoring stopped' }

export default function SessionHistory({ events }: { events: SessionEvent[] }) {
  return <section className="panel dash-panel session-history" id="session-history"><div className="panel-head"><div className="panel-title"><History className="icon" size={15} /> Session history</div><span className="section-caption">CURRENT API SESSION</span></div>{events.length ? <div className="session-event-list">{events.map((event, index) => <div className="session-event" key={`${event.timestamp}-${index}`}><span className="session-event-icon"><Clock3 size={12} /></span><span className="session-event-action">{actionLabels[event.action]}<small>{event.coin_count} selected {event.coin_count === 1 ? 'asset' : 'assets'}</small></span><time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleString()}</time></div>)}</div> : <div className="session-history-empty">No session actions have been recorded by this API process.</div>}</section>
}
