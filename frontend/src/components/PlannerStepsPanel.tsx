import type { PlannerTaskStateResponse } from '../types'

interface Props {
  plannerState: PlannerTaskStateResponse | null
  selectedRunId: number | null
  selectedRunStatus: string | null
  isBusy: boolean
  onClear: () => void
}

const STATUS_DOT: Record<string, { color: string; label: string }> = {
  pending: { color: '#a08090', label: 'Pending' },
  in_progress: { color: '#b87d6d', label: 'Working' },
  done: { color: '#22c55e', label: 'Done' },
  blocked: { color: '#f59e0b', label: 'Blocked' },
  cancelled: { color: '#888', label: 'Cancelled' }
}

export function PlannerStepsPanel({ plannerState, selectedRunId, isBusy, onClear }: Props) {
  const steps = plannerState?.steps ?? []
  const hasSteps = steps.length > 0

  if (!selectedRunId) return null

  return (
    <div className="pm">
      <div className="pm-head">
        <span className="pm-title">Planner</span>
        {hasSteps && !isBusy && (
          <button className="pm-clear" onClick={onClear}>clear</button>
        )}
      </div>

      {!hasSteps ? (
        <div className="pm-empty">fresh run</div>
      ) : (
        <div className="pm-list">
          {steps.map((s) => {
            const st = STATUS_DOT[s.status] || STATUS_DOT.pending
            return (
              <div key={s.id} className="pm-row">
                <span className="pm-dot" style={{ background: st.color }} title={st.label} />
                <span className="pm-text">{s.title}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
