import type { StepName } from '../types'

interface Props {
  goal: string
  globalContext: string
  lastDoneThing: string
  isBusy: boolean
  selectedRunId: number | null
  selectedRunStatus: string | null
  autoLoopEnabled: boolean
  onGoalChange: (v: string) => void
  onGlobalContextChange: (v: string) => void
  onLastDoneThingChange: (v: string) => void
  onStartRun: () => void
  onStopRun: () => void
  onPauseLoop: () => void
  onResumeLoop: () => void
  onRetryStep: (s: StepName) => void
  onRerunReviewer: () => void
}

export function RunControls(props: Props) {
  const canCancel = props.selectedRunStatus === 'running' || props.selectedRunStatus === 'paused'

  return (
    <section className="panel">
      <h2>Run Control</h2>

      <label>Run Goal</label>
      <textarea value={props.goal} onChange={(e) => props.onGoalChange(e.target.value)} rows={3} />

      <label>Global Context</label>
      <textarea value={props.globalContext} onChange={(e) => props.onGlobalContextChange(e.target.value)} rows={3} />

      <label>Last Done Thing (review feedback / previous report)</label>
      <textarea value={props.lastDoneThing} onChange={(e) => props.onLastDoneThingChange(e.target.value)} rows={3} />

      <div className="button-row">
        <button disabled={props.isBusy} onClick={props.onStartRun}>
          Start Run
        </button>

        <button disabled={!props.selectedRunId || !canCancel} onClick={props.onStopRun}>
          Cancel Selected Run
        </button>
      </div>

      <div className="loop-toggle-row">
        <div>
          <label className="label" style={{ margin: 0 }}>Auto-Start Next Cycle</label>
          <p className="muted small" style={{ margin: '4px 0 0' }}>
            {props.autoLoopEnabled ? 'Enabled: next cycle starts automatically after APPROVE.' : 'Disabled: runs stop after current cycle.'}
          </p>
        </div>

        <label className="switch" aria-label="Toggle auto-start next cycle">
          <input
            type="checkbox"
            checked={props.autoLoopEnabled}
            onChange={(e) => (e.target.checked ? props.onResumeLoop() : props.onPauseLoop())}
          />
          <span className="slider" />
        </label>
      </div>

      <div className="button-row">
        <button
          disabled={props.isBusy || !props.selectedRunId}
          onClick={() => props.onRetryStep('planner')}
        >
          Retry Planner
        </button>

        <button
          disabled={props.isBusy || !props.selectedRunId}
          onClick={() => props.onRetryStep('worker')}
        >
          Retry Worker
        </button>

        <button
          disabled={props.isBusy || !props.selectedRunId}
          onClick={props.onRerunReviewer}
        >
          Re-run Reviewer
        </button>
      </div>
    </section>
  )
}
