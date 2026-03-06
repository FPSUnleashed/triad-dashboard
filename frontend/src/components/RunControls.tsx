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
    <section className="panel control-section">
      <div className="panel-header">
        <h2 className="panel-title">Run Control</h2>
      </div>

      <div className="control-group">
        <label className="control-label">Goal</label>
        <textarea
          className="control-textarea"
          value={props.goal}
          onChange={(e) => props.onGoalChange(e.target.value)}
          rows={2}
          placeholder="Define the objective for this run..."
        />
      </div>

      <div className="control-group">
        <label className="control-label">Global Context</label>
        <textarea
          className="control-textarea"
          value={props.globalContext}
          onChange={(e) => props.onGlobalContextChange(e.target.value)}
          rows={2}
          placeholder="Additional context available to all steps..."
        />
      </div>

      <div className="control-group">
        <label className="control-label">Last Done Thing</label>
        <textarea
          className="control-textarea"
          value={props.lastDoneThing}
          onChange={(e) => props.onLastDoneThingChange(e.target.value)}
          rows={2}
          placeholder="Review feedback or previous report..."
        />
      </div>

      <div className="control-actions">
        <button
          className="btn btn-primary"
          disabled={props.isBusy}
          onClick={props.onStartRun}
        >
          Start Run
        </button>
        <button
          className="btn btn-secondary"
          disabled={!props.selectedRunId || !canCancel}
          onClick={props.onStopRun}
        >
          Cancel
        </button>
      </div>

      <div className="auto-loop">
        <div className="auto-loop-info">
          <div className="auto-loop-title">Auto-Start Next Cycle</div>
          <div className="auto-loop-desc">
            {props.autoLoopEnabled
              ? 'Enabled — next cycle starts automatically after APPROVE'
              : 'Disabled — runs stop after current cycle'}
          </div>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            checked={props.autoLoopEnabled}
            onChange={(e) => (e.target.checked ? props.onResumeLoop() : props.onPauseLoop())}
          />
          <span className="slider" />
        </label>
      </div>

      <div className="control-actions">
        <button
          className="btn btn-ghost btn-sm"
          disabled={props.isBusy || !props.selectedRunId}
          onClick={() => props.onRetryStep('planner')}
        >
          Retry Planner
        </button>
        <button
          className="btn btn-ghost btn-sm"
          disabled={props.isBusy || !props.selectedRunId}
          onClick={() => props.onRetryStep('worker')}
        >
          Retry Worker
        </button>
        <button
          className="btn btn-ghost btn-sm"
          disabled={props.isBusy || !props.selectedRunId}
          onClick={props.onRerunReviewer}
        >
          Re-run Reviewer
        </button>
      </div>
    </section>
  )
}
