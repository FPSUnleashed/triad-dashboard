import type { RunEvent } from '../types'

interface Props {
  events: RunEvent[]
}

export function LogsPanel({ events }: Props) {
  return (
    <section className="panel">
      <h2>Logs</h2>
      <div className="logs">
        {events.length === 0 && <div className="muted">No events yet.</div>}
        {events.map((e) => (
          <div key={e.id} className={`log ${e.level}`}>
            <div>
              <strong>[{e.level.toUpperCase()}]</strong> {e.message}
            </div>
            <div className="small">{e.created_at}</div>
            {e.meta && <pre>{e.meta}</pre>}
          </div>
        ))}
      </div>
    </section>
  )
}
