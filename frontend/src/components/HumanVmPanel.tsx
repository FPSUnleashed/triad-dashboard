import { useMemo, useState } from 'react'
import type { HumanVmRequest } from '../types'

interface Props {
  runId: number | null
  request: HumanVmRequest | null
  history: HumanVmRequest[]
  isBusy: boolean
  onRespond: (requestId: number, response: 'completed' | 'failed' | 'could_not_complete' | 'not_now' | 'try_yourself', report: string) => Promise<void>
}

const ACTIONS = [
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'could_not_complete', label: 'Could not complete' },
  { value: 'not_now', label: 'Not now' },
  { value: 'try_yourself', label: 'Try yourself' }
] as const

export function HumanVmPanel({ runId, request, history, isBusy, onRespond }: Props) {
  const [report, setReport] = useState('')
  const activeContextEntries = useMemo(() => Object.entries(request?.context || {}), [request])

  return (
    <section className="panel human-vm-panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Human VM task</h2>
          <p className="panel-subtitle">Manual VM handoff queue for the selected run.</p>
        </div>
        {runId ? <span className="human-vm-run-badge">Run #{runId}</span> : null}
      </div>
      {!request ? (
        <div className="text-muted text-sm">No active Human VM request for this run.</div>
      ) : (
        <div className="human-vm-active">
          <div className="human-vm-meta">
            <span className="text-sm text-muted">{request.step_name}</span>
            <span className="text-sm text-muted">Request #{request.id}</span>
          </div>
          <h3 className="human-vm-title">{request.title}</h3>
          <ol className="human-vm-instructions">{request.instructions.map((item, idx) => <li key={`${request.id}-${idx}`}>{item}</li>)}</ol>
          {activeContextEntries.length > 0 && <div className="human-vm-context"><h4>Context</h4><dl>{activeContextEntries.map(([k,v]) => <div key={k} className="human-vm-context-row"><dt>{k}</dt><dd>{typeof v === 'string' ? v : JSON.stringify(v)}</dd></div>)}</dl></div>}
          <div className="form-group">
            <label htmlFor="human-vm-report">What happened?</label>
            <textarea id="human-vm-report" value={report} onChange={(e) => setReport(e.target.value)} rows={6} placeholder="Describe what you observed and what happened in the VM." />
          </div>
          <div className="human-vm-actions">
            {ACTIONS.map((action) => <button key={action.value} className={`btn ${action.value === 'completed' ? 'btn-primary' : action.value === 'not_now' || action.value === 'try_yourself' ? 'btn-ghost' : 'btn-secondary'}`} disabled={isBusy || (!report.trim() && action.value !== 'not_now' && action.value !== 'try_yourself')} onClick={() => onRespond(request.id, action.value, report)}>{action.label}</button>)}
          </div>
        </div>
      )}
      {history.length > 0 && <div className="human-vm-history"><h3>History</h3><div className="human-vm-history-list">{history.map((item) => <article key={item.id} className="human-vm-history-item"><div className="human-vm-meta"><strong>{item.title}</strong><span className="text-sm text-muted">{item.response_option || item.status}</span></div>{item.response_report ? <p>{item.response_report}</p> : null}</article>)}</div></div>}
    </section>
  )
}
