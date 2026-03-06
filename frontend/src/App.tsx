import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { LogsPanel } from './components/LogsPanel'
import { PayloadInspector } from './components/PayloadInspector'
import { PipelineStatus } from './components/PipelineStatus'
import { PromptEditor } from './components/PromptEditor'
import { RunControls } from './components/RunControls'
import { StatsPanel } from './components/StatsPanel'
import type { Profile, Run, RunDetailResponse, RunEvent, RunStep, StepName } from './types'
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

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const selectedProfile = useMemo(
    () => profiles.find((p) => p.id === selectedProfileId) || null,
    [profiles, selectedProfileId]
  )

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
    const [detail, st, ev] = await Promise.all([
      api.getRun(runId),
      api.getRunSteps(runId),
      api.getRunEvents(runId)
    ])
    setRunDetail(detail)
    setSteps(st)
    setEvents(ev)
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
      // Poll while run is active
      const interval = setInterval(async () => {
        try {
          await refreshRunData(selectedRunId)
          await refreshRuns()
        } catch { /* ignore */ }
      }, 3000)
      return () => clearInterval(interval)
    } else {
      setRunDetail(null)
      setSteps([])
      setEvents([])
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
      {/* Header */}
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-brand">
            <div className="app-logo">T</div>
            <div>
              <h1 className="app-title">Triad Dashboard</h1>
              <p className="app-subtitle">Planner → Worker → Reviewer</p>
            </div>
          </div>
          <nav className="app-nav">
            <StatsPanel />
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="app-main">
        {error && (
          <div className="error-banner">
            <span>{error}</span>
            <button className="error-banner-close" onClick={() => setError('')}>×</button>
          </div>
        )}

        <div className="app-grid">
          {/* Sidebar */}
          <aside className="app-sidebar">
            {/* Run Selector */}
            <section className="panel">
              <div className="panel-header">
                <h2 className="panel-title">Runs</h2>
                <button 
                  className="btn btn-ghost btn-sm" 
                  onClick={refreshRuns}
                  disabled={busy}
                >
                  Refresh
                </button>
              </div>
              <div className="run-selector">
                {runs.length === 0 && (
                  <div className="text-muted text-sm">No runs yet</div>
                )}
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

            {/* Run Controls */}
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
            />
          </aside>

          {/* Content */}
          <div className="app-content">
            {/* Pipeline Status */}
            <PipelineStatus runDetail={runDetail} />

            {/* Prompt Editor */}
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

            {/* Payload Inspector */}
            <PayloadInspector steps={steps} />

            {/* Logs */}
            <LogsPanel events={events} />
          </div>
        </div>
      </main>
    </div>
  )
}
