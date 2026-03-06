import type { RunDetailResponse, StepName, StepStatus } from '../types'

interface Props {
  runDetail: RunDetailResponse | null
}

const STEPS: StepName[] = ['planner', 'worker', 'reviewer']

const STEP_LABEL: Record<StepName, string> = {
  planner: 'Planner',
  worker: 'Worker',
  reviewer: 'Reviewer'
}

const STATUS_ICON: Record<StepStatus, string> = {
  pending: '○',
  running: '◐',
  paused: 'ǁ',
  passed: '●',
  failed: '✕',
  blocked: '⚠',
  cancelled: '∅'
}

export function PipelineStatus({ runDetail }: Props) {
  const stepStatus = runDetail?.step_status
  const run = runDetail?.run

  const getStatus = (step: StepName): StepStatus => {
    if (!stepStatus) return 'pending'
    return (stepStatus[step]?.status as StepStatus) || 'pending'
  }

  const getDuration = (step: StepName): string | null => {
    if (!stepStatus) return null
    return stepStatus[step]?.duration_formatted || null
  }

  const activeStep = STEPS.find((s) => {
    const st = getStatus(s)
    return st === 'running' || st === 'paused'
  })

  const runStatus = (run?.status || 'pending') as StepStatus

  return (
    <section className="pipeline-section">
      {/* Header */}
      <div className="pipeline-header">
        <div>
          <h2 className="pipeline-title">Pipeline</h2>
          <p className="panel-subtitle">Planner → Worker → Reviewer</p>
        </div>
        <div className={`pipeline-badge ${runStatus}`}>
          {run?.status ? run.status.toUpperCase() : 'NO RUN'}
        </div>
      </div>

      {/* Step cards */}
      <div className="pipeline-steps">
        {STEPS.map((step) => {
          const status = getStatus(step)
          const duration = getDuration(step)
          const isActive = activeStep === step

          return (
            <div
              key={step}
              className={`pipeline-step ${isActive ? 'active' : ''}`}
            >
              <div className="pipeline-step-header">
                <div className={`pipeline-step-icon ${status}`}>
                  {STATUS_ICON[status]}
                </div>
                <div>
                  <div className="pipeline-step-name">{STEP_LABEL[step]}</div>
                  <div className={`pipeline-step-status ${status}`}>
                    {status}
                  </div>
                </div>
              </div>
              <div className="pipeline-step-duration">
                {duration || '--:--'}
              </div>
            </div>
          )
        })}
      </div>

      {/* Meta info */}
      {runDetail && run && (
        <div className="pipeline-meta">
          <div className="pipeline-meta-item">
            <span className="pipeline-meta-label">Run ID</span>
            <span className="pipeline-meta-value">#{run.id}</span>
          </div>
          <div className="pipeline-meta-item">
            <span className="pipeline-meta-label">Engine</span>
            <span className="pipeline-meta-value">
              {runDetail.is_running ? 'Running' : 'Stopped'}
            </span>
          </div>
          <div className="pipeline-meta-item">
            <span className="pipeline-meta-label">Duration</span>
            <span className="pipeline-meta-value">
              {run.duration_formatted || '--:--'}
            </span>
          </div>
          <div className="pipeline-meta-item">
            <span className="pipeline-meta-label">Elapsed</span>
            <span className="pipeline-meta-value">
              {run.elapsed_formatted || '--:--'}
            </span>
          </div>
        </div>
      )}
    </section>
  )
}
