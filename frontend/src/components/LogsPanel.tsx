import type { RunEvent } from '../types'

interface Props {
  events: RunEvent[]
}

export function LogsPanel({ events }: Props) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Logs</h2>
        <span className="text-xs text-muted">{events.length} events</span>
      </div>
      <div className="logs-container">
        {events.length === 0 && (
          <div className="text-muted text-sm">No events yet.</div>
        )}
        {events.map((e) => (
          <div key={e.id} className="log-entry">
            <div className="log-header">
              <span className={`log-level ${e.level}`}>{e.level}</span>
              <span className="log-message">{e.message}</span>
              <span className="log-time">{e.created_at}</span>
            </div>
            {e.meta && <pre className="log-meta">{e.meta}</pre>}
          </div>
        ))}
      </div>
    </section>
  )
}
