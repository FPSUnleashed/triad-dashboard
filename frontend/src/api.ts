import type { HumanVmRequestsResponse, HumanVmResponseOption, LoopState, PlannerTaskStateResponse, Profile, Run, RunDetailResponse, RunEvent, RunStep, StepName, Stats, SystemMetrics } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {})
    },
    ...init
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  listProfiles: () => req<Profile[]>('/profiles'),
  upsertProfile: (payload: {
    name: string
    planner_prompt: string
    worker_inject_prompt: string
    reviewer_inject_prompt: string
  }) => req<Profile>('/profiles', { method: 'POST', body: JSON.stringify(payload) }),

  listRuns: (limit = 30) => req<Run[]>(`/runs?limit=${limit}`),

  createRun: (payload: {
    goal: string
    profile_id: number
    global_context: string
    last_done_thing: string
  }) => req<{ run: Run }>('/runs', { method: 'POST', body: JSON.stringify(payload) }),

  getRun: (runId: number) => req<RunDetailResponse>(`/runs/${runId}`),
  getRunSteps: (runId: number) => req<RunStep[]>(`/runs/${runId}/steps`),
  getPlannerTaskSteps: (runId: number) => req<PlannerTaskStateResponse>(`/runs/${runId}/task-steps`),
  clearPlannerTaskSteps: (runId: number) => req<PlannerTaskStateResponse & { ok: boolean }>(`/runs/${runId}/task-steps/clear`, { method: 'POST' }),
  getRunEvents: (runId: number) => req<RunEvent[]>(`/runs/${runId}/events`),
  getHumanVmRequests: (runId: number) => req<HumanVmRequestsResponse>(`/runs/${runId}/human-vm`),
  respondHumanVmRequest: (runId: number, requestId: number, payload: { response_option: HumanVmResponseOption; report: string }) => req<{ ok: boolean }>(`/runs/${runId}/human-vm/${requestId}/respond`, { method: 'POST', body: JSON.stringify(payload) }),

  stopRun: (runId: number) => req<{ ok: boolean; run_id: number; task_cancelled: boolean }>(`/runs/${runId}/stop`, {
    method: 'POST'
  }),

  pauseRun: (runId: number) => req<{ ok: boolean; run_id: number; task_cancelled: boolean }>(`/runs/${runId}/pause`, {
    method: 'POST'
  }),

  resumeRun: (runId: number) => req<{ ok: boolean; run_id: number; start_step: StepName }>(`/runs/${runId}/resume`, {
    method: 'POST'
  }),

  retryRunFromStep: (runId: number, step: StepName) => req<{ ok: boolean }>(`/runs/${runId}/retry`, {
    method: 'POST',
    body: JSON.stringify({ step })
  }),

  rerunReviewer: (runId: number) => req<{ ok: boolean }>(`/runs/${runId}/rerun-reviewer`, { method: 'POST' }),

  getLoopState: () => req<LoopState>('/loop/state'),
  pauseLoop: () => req<LoopState>('/loop/pause', { method: 'POST' }),
  resumeLoop: () => req<LoopState>('/loop/resume', { method: 'POST' }),

  cleanWorkerSpace: (runId: number) => req<{ ok: boolean; run_id: number; workspace_existed: boolean; workspace_cleaned: boolean; workspace_path: string }>(`/runs/${runId}/clean-worker-space`, { method: 'POST' }),

  getStats: () => req<Stats>('/stats'),

  getSystemMetrics: () => req<SystemMetrics>('/system/metrics')
}
