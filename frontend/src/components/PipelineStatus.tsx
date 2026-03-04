import { Fragment } from 'react'
import type { RunDetailResponse, StepName, StepStatus } from '../types'

interface Props {
  runDetail: RunDetailResponse | null
}

const labelMap: Record<StepName, string> = {
  planner: 'Planner',
  worker: 'Worker',
  reviewer: 'Reviewer'
}

function cls(status: StepStatus) {
  return `node ${status}`
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
    const stepData = stepStatus[step]
    if (stepData?.duration_formatted) {
      return stepData.duration_formatted
    }
    return null
  }

  return (
    <section className="panel">
      <h2>Pipeline Status</h2>
      <div className="pipeline">
        {(['planner', 'worker', 'reviewer'] as StepName[]).map((step, idx) => (
          <Fragment key={step}>
            <div className={cls(getStatus(step))}>
              <strong>{labelMap[step]}</strong>
              <span className="status-label">{getStatus(step)}</span>
              {getDuration(step) && (
                <span className="duration">⏱ {getDuration(step)}</span>
              )}
            </div>
            {idx < 2 && <div className="arrow">→</div>}
          </Fragment>
        ))}
        <div className="loopback">↺ feedback to Planner</div>
      </div>

      {runDetail && (
        <div className="meta">
          <div><strong>Run:</strong> #{run.id}</div>
          <div><strong>Status:</strong> {run.status}</div>
          <div><strong>Running:</strong> {runDetail.is_running ? 'yes' : 'no'}</div>
          {run.duration_formatted && (
            <div><strong>Duration:</strong> {run.duration_formatted}</div>
          )}
          {run.elapsed_formatted && runDetail.is_running && (
            <div><strong>Elapsed:</strong> {run.elapsed_formatted}</div>
          )}
        </div>
      )}
    </section>
  )
}
