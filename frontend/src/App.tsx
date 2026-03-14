import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { HumanVmPanel } from './components/HumanVmPanel'
import { LogsPanel } from './components/LogsPanel'
import { PayloadInspector } from './components/PayloadInspector'
import { PipelineStatus } from './components/PipelineStatus'
import { PlannerStepsPanel } from './components/PlannerStepsPanel'
import { PromptEditor } from './components/PromptEditor'
import { RunControls } from './components/RunControls'
import { SystemMetrics } from './components/SystemMetrics'
import type { HumanVmRequest, PlannerTaskStateResponse, Profile, Run, RunDetailResponse, RunEvent, RunStep, StepName } from './types'
import './styles.css'

export default function App() {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(() => {
    const saved = localStorage.getItem('triad_profileId')
    const parsed = saved ? Number.parseInt(saved, 10) : Number.NaN
    return Number.isFinite(parsed) ? parsed : null
  })
  const [selectedRunId, setSelectedRunId] = useState<number | null>(() => {
    const saved = localStorage.getItem('triad_runId')
    const parsed = saved ? Number.parseInt(saved, 10) : Number.NaN
    return Number.isFinite(parsed) ? parsed : null
  })

  const [profileName, setProfileName] = useState('default')
  const [plannerPrompt, setPlannerPrompt] = useState('')
  const [workerPrompt, setWorkerPrompt] = useState('')
  const [reviewerPrompt, setReviewerPrompt] = useState('')

  const [goal, setGoal] = useState(() => localStorage.getItem('triad_goal') || '')
  const [globalContext, setGlobalContext] = useState(() => localStorage.getItem('triad_globalContext') || '')
  const [lastDoneThing, setLastDoneThing] = useState(() => localStorage.getItem('triad_lastDoneThing') || '')
  const [autoLoopEnabled, setAutoLoopEnabled] = useState(false)

  const [runDetail, setRunDetail] = useState<RunDetailResponse | null>(null)
  const [steps, setSteps] = useState<RunStep[]>([])
  const [events, setEvents] = useState<RunEvent[]>([])
  const [plannerState, setPlannerState] = useState<PlannerTaskStateResponse | null>(null)
  const [humanVmActiveRequest, setHumanVmActiveRequest] = useState<HumanVmRequest | null>(null)
  const [humanVmHistory, setHumanVmHistory] = useState<HumanVmRequest[]>([])
  const [notifiedRequestId, setNotifiedRequestId] = useState<number | null>(null)

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const selectedRun = useMemo(
    () => runs.find((r) => r.id === selectedRunId) || runDetail?.run || null,
    [runs, selectedRunId, runDetail]
  )

  const refreshProfiles = async () => {
    const data = await api.listProfiles()
    setProfiles(data)
    if (data.length === 0) return

    const current = selectedProfileId ? data.find((p) => p.id === selectedProfileId) : null
    const chosen = current || data[0]
    setSelectedProfileId(chosen.id)
    setProfileName(chosen.name)
    setPlannerPrompt(chosen.planner_prompt)
    setWorkerPrompt(chosen.worker_inject_prompt)
    setReviewerPrompt(chosen.reviewer_inject_prompt)
  }

  const refreshRuns = async () => {
    const data = await api.listRuns(30)
    setRuns(data)
  }

  const refreshRunData = async (runId: number) => {
    const [detail, st, taskState, ev, humanVm] = await Promise.all([
      api.getRun(runId),
      api.getRunSteps(runId),
      api.getPlannerTaskSteps(runId),
      api.getRunEvents(runId),
      api.getHumanVmRequests(runId)
    ])
    setRunDetail(detail)
    setSteps(st)
    setPlannerState(taskState)
    setEvents(ev)
    setHumanVmActiveRequest(humanVm.active_request)
    setHumanVmHistory(humanVm.requests)
  }

  const refreshLoopState = async () => {
    const state = await api.getLoopState()
    setAutoLoopEnabled(state.auto_loop_enabled)
  }

  useEffect(() => {
    refreshProfiles()
    refreshRuns()
    refreshLoopState()
  }, [])

  useEffect(() => {
    if (selectedRunId) {
      refreshRunData(selectedRunId)
      const interval = setInterval(async () => {
        try {
          await refreshRunData(selectedRunId)
          await refreshRuns()
        } catch {}
      }, 3000)
      return () => clearInterval(interval)
    } else {
      setRunDetail(null)
      setSteps([])
      setEvents([])
      setPlannerState(null)
      setHumanVmActiveRequest(null)
      setHumanVmHistory([])
    }
  }, [selectedRunId])

  useEffect(() => {
    localStorage.setItem('triad_profileId', String(selectedProfileId))
  }, [selectedProfileId])

  useEffect(() => {
    if (selectedRunId !== null) {
      localStorage.setItem('triad_runId', String(selectedRunId))
    } else {
      localStorage.removeItem('triad_runId')
    }
  }, [selectedRunId])

  useEffect(() => {
    localStorage.setItem('triad_goal', goal)
  }, [goal])

  useEffect(() => {
    localStorage.setItem('triad_globalContext', globalContext)
  }, [globalContext])

  useEffect(() => {
    localStorage.setItem('triad_lastDoneThing', lastDoneThing)
  }, [lastDoneThing])

  useEffect(() => {
    if (!humanVmActiveRequest || !selectedRunId || humanVmActiveRequest.id === notifiedRequestId) return
    setNotifiedRequestId(humanVmActiveRequest.id)
    document.title = `🔔 Human VM needed · Run #${selectedRunId}`
    try {
      const AudioCtor = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (AudioCtor) {
        const ctx = new AudioCtor()
        const osc = ctx.createOscillator()
        const gain = ctx.createGain()
        osc.frequency.value = 880
        gain.gain.value = 0.04
        osc.connect(gain)
        gain.connect(ctx.destination)
        osc.start()
        osc.stop(ctx.currentTime + 0.25)
      }
    } catch {}
    if ('Notification' in window) {
      if (Notification.permission === 'default') Notification.requestPermission().catch(() => undefined)
      if (Notification.permission === 'granted') new Notification(`Human VM needed for run #${selectedRunId}`, { body: humanVmActiveRequest.title })
    }
  }, [humanVmActiveRequest, notifiedRequestId, selectedRunId])

  useEffect(() => {
    if (!humanVmActiveRequest) document.title = 'Triad Dashboard'
  }, [humanVmActiveRequest])

  const handleStartRun = async () => {
    if (!selectedProfileId) return
    setBusy(true)
    setError('')
    try {
      const { run } = await api.createRun({
        profile_id: selectedProfileId,
        goal,
        global_context: globalContext,
        last_done_thing: lastDoneThing
      })
      await refreshRuns()
      setSelectedRunId(run.id)
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleStopRun = async () => {
    if (!selectedRunId) return
    setBusy(true)
    try {
      await api.stopRun(selectedRunId)
      await refreshRuns()
      await refreshRunData(selectedRunId)
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handlePauseLoop = async () => {
    try {
      await api.pauseLoop()
      setAutoLoopEnabled(false)
    } catch (e: unknown) {
      setError(String(e))
    }
  }

  const handleResumeLoop = async () => {
    try {
      await api.resumeLoop()
      setAutoLoopEnabled(true)
    } catch (e: unknown) {
      setError(String(e))
    }
  }

  const handleRetryStep = async (step: StepName) => {
    if (!selectedRunId) return
    setBusy(true)
    try {
      await api.retryRunFromStep(selectedRunId, step)
      await refreshRuns()
      await refreshRunData(selectedRunId)
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleRerunReviewer = async () => {
    if (!selectedRunId) return
    setBusy(true)
    try {
      await api.rerunReviewer(selectedRunId)
      await refreshRuns()
      await refreshRunData(selectedRunId)
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleClearPlannerSteps = async () => {
    if (!selectedRunId) return
    setBusy(true)
    try {
      const state = await api.clearPlannerTaskSteps(selectedRunId)
      setPlannerState(state)
      await refreshRuns()
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }
  const handleCleanWorkerSpace = async () => {
    if (!selectedRunId) return
    setBusy(true)
    try {
      await api.cleanWorkerSpace(selectedRunId)
    } catch (e) {
      console.error('Failed to clean worker space', e)
    } finally {
      setBusy(false)
    }
  }


  const handleRespondHumanVm = async (requestId: number, response: 'completed' | 'failed' | 'could_not_complete' | 'not_now' | 'try_yourself', report: string) => {
    if (!selectedRunId) return
    setBusy(true)
    try {
      await api.respondHumanVmRequest(selectedRunId, requestId, { response_option: response, report })
      await refreshRuns()
      await refreshRunData(selectedRunId)
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleSaveProfile = async () => {
    if (!selectedProfileId) return
    setBusy(true)
    try {
      await api.upsertProfile({
        name: profileName,
        planner_prompt: plannerPrompt,
        worker_inject_prompt: workerPrompt,
        reviewer_inject_prompt: reviewerPrompt
      })
      await refreshProfiles()
    } catch (e: unknown) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleSelectProfile = (id: number) => {
    setSelectedProfileId(id)
    const profile = profiles.find((p) => p.id === id)
    if (profile) {
      setProfileName(profile.name)
      setPlannerPrompt(profile.planner_prompt)
      setWorkerPrompt(profile.worker_inject_prompt)
      setReviewerPrompt(profile.reviewer_inject_prompt)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-brand">
            <div className="app-logo">T</div>
            <div>
              <h1 className="app-title">Triad Dashboard</h1>
              <p className="app-subtitle">Planner → Worker → Reviewer</p>
            </div>
          </div>
          <SystemMetrics />
        </div>
      </header>

      <main className="app-main">
        {humanVmActiveRequest && selectedRunId && <div className="human-vm-banner">Human VM task pending for run #{selectedRunId}: {humanVmActiveRequest.title}</div>}

        {error && (
          <div className="error-banner">
            <span>{error}</span>
            <button className="error-banner-close" onClick={() => setError('')}>×</button>
          </div>
        )}

        <div className="app-grid">
          <aside className="app-sidebar">
            <section className="panel">
              <div className="panel-header">
                <h2 className="panel-title">Runs</h2>
                <button className="btn btn-ghost btn-sm" onClick={refreshRuns} disabled={busy}>
                  Refresh
                </button>
              </div>
              <div className="run-selector">
                {runs.length === 0 && <div className="text-muted text-sm">No runs yet</div>}
                {runs.map((run) => (
                  <div
                    key={run.id}
                    className={`run-item ${selectedRunId === run.id ? 'active' : ''}`}
                    onClick={() => setSelectedRunId(run.id)}
                  >
                    <span className="run-item-id">#{run.id}</span>
                    <span className={`run-item-status ${run.status}`}>{run.status}</span>
                  </div>
                ))}
              </div>
            </section>

            <RunControls
              goal={goal}
              globalContext={globalContext}
              lastDoneThing={lastDoneThing}
              isBusy={busy}
              selectedRunId={selectedRunId}
              selectedRunStatus={selectedRun?.status || null}
              autoLoopEnabled={autoLoopEnabled}
              onGoalChange={setGoal}
              onGlobalContextChange={setGlobalContext}
              onLastDoneThingChange={setLastDoneThing}
              onStartRun={handleStartRun}
              onStopRun={handleStopRun}
              onPauseLoop={handlePauseLoop}
              onResumeLoop={handleResumeLoop}
              onRetryStep={handleRetryStep}
              onRerunReviewer={handleRerunReviewer}
              onCleanWorkerSpace={handleCleanWorkerSpace}
            />
          </aside>

          <div className="app-content">
            <PipelineStatus runDetail={runDetail} />

            <HumanVmPanel runId={selectedRunId} request={humanVmActiveRequest} history={humanVmHistory} isBusy={busy} onRespond={handleRespondHumanVm} />

            <PlannerStepsPanel
              plannerState={plannerState}
              selectedRunId={selectedRunId}
              selectedRunStatus={selectedRun?.status || null}
              isBusy={busy}
              onClear={handleClearPlannerSteps}
            />

            <PromptEditor
              profiles={profiles}
              selectedProfileId={selectedProfileId}
              profileName={profileName}
              plannerPrompt={plannerPrompt}
              workerPrompt={workerPrompt}
              reviewerPrompt={reviewerPrompt}
              onSelectProfile={handleSelectProfile}
              onProfileNameChange={setProfileName}
              onPlannerChange={setPlannerPrompt}
              onWorkerChange={setWorkerPrompt}
              onReviewerChange={setReviewerPrompt}
              onSave={handleSaveProfile}
            />

            <PayloadInspector steps={steps} />
            <LogsPanel events={events} />
          </div>
        </div>
      </main>
    </div>
  )
}
