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
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)

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
    setAutoLoopEnabled(Boolean(state.auto_loop_enabled))
  }

  useEffect(() => {
    ;(async () => {
      try {
        const profilesData = await api.listProfiles()
        setProfiles(profilesData)
        if (profilesData.length > 0) {
          const savedIdRaw = localStorage.getItem('triad_profileId')
          const savedId = savedIdRaw ? Number.parseInt(savedIdRaw, 10) : Number.NaN
          const savedProfile = Number.isFinite(savedId)
            ? profilesData.find((p) => p.id === savedId)
            : null
          const profile = savedProfile || profilesData[0]
          setSelectedProfileId(profile.id)
          setProfileName(profile.name)
          setPlannerPrompt(profile.planner_prompt)
          setWorkerPrompt(profile.worker_inject_prompt)
          setReviewerPrompt(profile.reviewer_inject_prompt)
        }

        const runsData = await api.listRuns(30)
        setRuns(runsData)
        const activeRun = runsData.find((r: Run) => r.status === 'running')
          || runsData.find((r: Run) => r.status === 'pending')
          || runsData[0]
        if (activeRun) setSelectedRunId(activeRun.id)

        await refreshLoopState()
      } catch (e) {
        setError(String(e))
      }
    })()
  }, [])

  useEffect(() => {
    if (!selectedProfile) return
    setProfileName(selectedProfile.name)
    setPlannerPrompt(selectedProfile.planner_prompt)
    setWorkerPrompt(selectedProfile.worker_inject_prompt)
    setReviewerPrompt(selectedProfile.reviewer_inject_prompt)
  }, [selectedProfile])

  useEffect(() => {
    if (!selectedRunId) return
    let alive = true

    const tick = async () => {
      if (!alive) return
      try {
        await refreshRunData(selectedRunId)
      } catch (e) {
        if (alive) setError(String(e))
      }
    }

    tick()
    const t = setInterval(tick, 2000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [selectedRunId])

  useEffect(() => {
    if (selectedProfileId === null || !Number.isFinite(selectedProfileId)) {
      localStorage.removeItem('triad_profileId')
      return
    }
    localStorage.setItem('triad_profileId', String(selectedProfileId))
  }, [selectedProfileId])

  useEffect(() => {
    localStorage.setItem('triad_goal', goal)
  }, [goal])

  useEffect(() => {
    localStorage.setItem('triad_globalContext', globalContext)
  }, [globalContext])

  useEffect(() => {
    localStorage.setItem('triad_lastDoneThing', lastDoneThing)
  }, [lastDoneThing])

  const saveProfile = async () => {
    setError('')
    if (!profileName.trim()) {
      setError('Profile name is required')
      return
    }
    try {
      setBusy(true)
      const p = await api.upsertProfile({
        name: profileName.trim(),
        planner_prompt: plannerPrompt,
        worker_inject_prompt: workerPrompt,
        reviewer_inject_prompt: reviewerPrompt
      })
      await refreshProfiles()
      setSelectedProfileId(p.id)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const startRun = async () => {
    setError('')
    if (!profileName.trim()) {
      setError('Profile name is required')
      return
    }
    if (!goal.trim()) {
      setError('Goal is required')
      return
    }

    try {
      setBusy(true)

      const savedProfile = await api.upsertProfile({
        name: profileName.trim(),
        planner_prompt: plannerPrompt,
        worker_inject_prompt: workerPrompt,
        reviewer_inject_prompt: reviewerPrompt
      })
      setSelectedProfileId(savedProfile.id)

      const created = await api.createRun({
        goal: goal.trim(),
        profile_id: savedProfile.id,
        global_context: globalContext,
        last_done_thing: lastDoneThing
      })
      setSelectedRunId(created.run.id)
      await refreshProfiles()
      await refreshRuns()
      await refreshRunData(created.run.id)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const stopRun = async () => {
    if (!selectedRunId) return
    setError('')
    try {
      await api.stopRun(selectedRunId)
      await refreshRuns()
      await refreshRunData(selectedRunId)
    } catch (e) {
      setError(String(e))
    }
  }

  const pauseLoop = async () => {
    setError('')
    try {
      const state = await api.pauseLoop()
      setAutoLoopEnabled(Boolean(state.auto_loop_enabled))
    } catch (e) {
      setError(String(e))
    }
  }

  const resumeLoop = async () => {
    setError('')
    try {
      const state = await api.resumeLoop()
      setAutoLoopEnabled(Boolean(state.auto_loop_enabled))
    } catch (e) {
      setError(String(e))
    }
  }

  const retryStep = async (step: StepName) => {
    if (!selectedRunId) return
    setError('')
    try {
      setBusy(true)
      await api.retryRunFromStep(selectedRunId, step)
      await refreshRunData(selectedRunId)
      await refreshRuns()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const rerunReviewer = async () => {
    if (!selectedRunId) return
    setError('')
    try {
      setBusy(true)
      await api.rerunReviewer(selectedRunId)
      await refreshRunData(selectedRunId)
      await refreshRuns()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="app">
      <header>
        <h1>Triad Dashboard</h1>
        <p>Simple Planner → Worker → Reviewer loop with full payload visibility.</p>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="grid two">
        <PromptEditor
          profiles={profiles}
          selectedProfileId={selectedProfileId}
          profileName={profileName}
          plannerPrompt={plannerPrompt}
          workerPrompt={workerPrompt}
          reviewerPrompt={reviewerPrompt}
          onSelectProfile={setSelectedProfileId}
          onProfileNameChange={setProfileName}
          onPlannerChange={setPlannerPrompt}
          onWorkerChange={setWorkerPrompt}
          onReviewerChange={setReviewerPrompt}
          onSave={saveProfile}
        />

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
          onStartRun={startRun}
          onStopRun={stopRun}

          onPauseLoop={pauseLoop}
          onResumeLoop={resumeLoop}
          onRetryStep={retryStep}
          onRerunReviewer={rerunReviewer}
        />
      </div>

      <PipelineStatus runDetail={runDetail} />

      <StatsPanel />

      <div className="grid two">
        <PayloadInspector steps={steps} />
        <LogsPanel events={events} />
      </div>

      <section className="panel">
        <h2>Runs</h2>
        <div className="run-list">
          {runs.map((r) => (
            <button
              key={r.id}
              className={`run-item ${selectedRunId === r.id ? 'active' : ''}`}
              onClick={() => setSelectedRunId(r.id)}
            >
              #{r.id} · {r.status} · profile: {r.profile_name || r.profile_id}
              <div className="small">{r.goal}</div>
            </button>
          ))}
          {runs.length === 0 && <div className="muted">No runs yet.</div>}
        </div>
      </section>
    </main>
  )
}
